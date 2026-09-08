// openWakeWord in the browser, via onnxruntime-web.
//
// Three models in series, exactly as openWakeWord runs them natively:
//
//   audio (16kHz mono) ──► melspectrogram ──► embedding ──► wake word ──► score
//        1280 samples          5 frames        1 x 96-dim      16 embeddings
//
// Each stage keeps a rolling buffer of the previous stage's output, so a
// detection costs one small inference per 80ms of audio rather than
// re-running the whole window. On a laptop that's well under 1% of a core.
//
// Models are served by our own backend (/voice/wakeword/*.onnx), which caches
// them on first use — the page never talks to GitHub itself.

const SAMPLE_RATE = 16000
const CHUNK = 1280          // 80ms — the mel model's natural step
const MAX_LAG = 8           // chunks (~640ms) of backlog before dropping
const MEL_FRAMES = 76       // frames the embedding model expects
const EMB_WINDOW = 16       // embeddings the wake word model expects
const EMB_DIM = 96

const modelUrl = name => {
  const token = import.meta.env.VITE_API_TOKEN
  const base = `/voice/wakeword/${name}.onnx`
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

// onnxruntime-web resolves its .wasm at runtime from a path it guesses, which
// the dev server answers with index.html — the wasm compile then fails on
// "expected magic word 00 61 73 6d, found ef bb bf 3c" (a BOM and a '<'). The
// ?url import makes Vite emit the real binary and hand us its hashed URL, so
// dev and build both point at the same file.
// Note the specifiers: the package's exports map publishes these at the root
// ("./ort-wasm-simd-threaded.wasm"), so a ./dist/ path fails to resolve. Both
// files are required — the .wasm alone loads but then dies on "K is not a
// function", because the .mjs is the glue that instantiates it.
import wasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.wasm?url"
import mjsUrl from "onnxruntime-web/ort-wasm-simd-threaded.mjs?url"
// The worklet module must be fetched from a URL. Importing the source as a
// string and wrapping it in a same-origin Blob URL loads identically in dev and
// in the production build. A plain ?url import inlines to a data: URI once the
// file is small enough, and addModule() rejects data: URIs under some browsers
// and CSPs — the same "fine in the build, dead for users" trap the wasm hit.
import processorSource from "./wakeWordProcessor.js?raw"

let ortPromise = null

async function loadOrt() {
  ortPromise ||= (async () => {
    const ort = await import("onnxruntime-web")
    ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: mjsUrl }
    // Threaded wasm needs SharedArrayBuffer, which needs COOP/COEP headers the
    // dev server doesn't send. One thread is ample: an 80ms hop through three
    // small models is well under a millisecond of compute.
    ort.env.wasm.numThreads = 1
    ort.env.wasm.simd = true
    return ort
  })()
  return ortPromise
}

async function session(ort, name) {
  const res = await fetch(modelUrl(name))
  if (!res.ok) throw new Error(`${name}.onnx unavailable (${res.status})`)
  return ort.InferenceSession.create(await res.arrayBuffer(), {
    executionProviders: ["wasm"], graphOptimizationLevel: "all",
  })
}

/**
 * Listen for a wake word on an existing microphone stream.
 *
 * @param stream  the same MediaStream the VAD is using — one mic, two readers
 * @param onWake  called (with the score) each time the word is heard
 * @returns {{stop: function}}
 */
export async function attachWakeWord(stream, { onWake, model = "hey_jarvis_v0.1",
                                               threshold = 0.5, refractoryMs = 2000 } = {}) {
  const ort = await loadOrt()
  const [mel, emb, wake] = await Promise.all(
    [session(ort, "melspectrogram"), session(ort, "embedding_model"), session(ort, model)])

  // Asking for 16kHz directly lets the browser do the resampling properly;
  // decimating 48kHz by hand would alias straight into the mel bands.
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source = ctx.createMediaStreamSource(stream)
  const processorUrl = URL.createObjectURL(
    new Blob([processorSource], { type: "text/javascript" }))
  try { await ctx.audioWorklet.addModule(processorUrl) }
  finally { URL.revokeObjectURL(processorUrl) }
  const node = new AudioWorkletNode(ctx, "wake-word-chunker",
                                    { numberOfInputs: 1, numberOfOutputs: 1,
                                      outputChannelCount: [1] })

  let melBuf = []                     // rolling mel frames (32 bins each)
  let embBuf = []                     // rolling embeddings (96-dim each)
  let queue = []                      // chunks from the audio thread
  let lastFire = 0, busy = false, stopped = false, dropped = 0, received = 0, inferred = 0, inferMs = 0

  const run = async samples => {
    // 1. audio → mel frames. openWakeWord's melspectrogram model is trained on
    //    16-bit PCM magnitude (±32768), not the browser's ±1.0 float range, so
    //    the samples must be scaled up first — otherwise the mel output is ~32k×
    //    too small, the /10+2 transform flattens it to a constant, and every
    //    score sits near zero. Then normalise the raw mel exactly as openWakeWord
    //    does; without it scores sit near zero as well.
    const scaled = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i++) scaled[i] = samples[i] * 32767
    const melOut = await mel.run({
      [mel.inputNames[0]]: new ort.Tensor("float32", scaled, [1, scaled.length]) })
    const melData = melOut[mel.outputNames[0]].data
    for (let i = 0; i < melData.length; i += 32)
      melBuf.push(Float32Array.from(melData.subarray(i, i + 32), v => v / 10 + 2))
    if (melBuf.length > MEL_FRAMES * 2) melBuf = melBuf.slice(-MEL_FRAMES * 2)
    if (melBuf.length < MEL_FRAMES) return

    // 2. last 76 mel frames → one 96-dim embedding
    const window = melBuf.slice(-MEL_FRAMES)
    const flat = new Float32Array(MEL_FRAMES * 32)
    window.forEach((frame, i) => flat.set(frame, i * 32))
    const embOut = await emb.run({
      [emb.inputNames[0]]: new ort.Tensor("float32", flat, [1, MEL_FRAMES, 32, 1]) })
    embBuf.push(Float32Array.from(embOut[emb.outputNames[0]].data))
    if (embBuf.length > EMB_WINDOW) embBuf = embBuf.slice(-EMB_WINDOW)
    if (embBuf.length < EMB_WINDOW) return

    // 3. last 16 embeddings → score
    const feats = new Float32Array(EMB_WINDOW * EMB_DIM)
    embBuf.forEach((e, i) => feats.set(e, i * EMB_DIM))
    const out = await wake.run({
      [wake.inputNames[0]]: new ort.Tensor("float32", feats, [1, EMB_WINDOW, EMB_DIM]) })
    const score = out[wake.outputNames[0]].data[0]
    const now = performance.now()
    if (score >= threshold && now - lastFire > refractoryMs) {
      lastFire = now
      embBuf = []                     // don't re-trigger on the same utterance
      onWake?.(score)
    }
  }

  // Drain the queue one inference at a time. A full step costs ~57ms against
  // the 80ms a chunk represents, so this keeps up; MAX_LAG bounds the damage if
  // the tab is briefly starved, keeping us near the live edge of the audio
  // rather than working through a growing backlog of stale sound.
  const pump = async () => {
    if (busy) return
    busy = true
    try {
      while (queue.length && !stopped) {
        if (queue.length > MAX_LAG) {
          // Discontinuity in the mel history is the lesser evil against
          // answering a wake word several seconds after it was spoken.
          dropped += queue.length - MAX_LAG
          queue = queue.slice(-MAX_LAG)
        }
        const t = performance.now()
        await run(queue.shift())
        inferMs += performance.now() - t
        inferred++
      }
    } catch (err) {
      console.warn("wake word inference failed", err)
    } finally {
      busy = false
    }
  }

  node.port.onmessage = event => {
    if (stopped) return
    received++
    queue.push(new Float32Array(event.data))
    pump()
  }

  source.connect(node)
  // A zero gain keeps the mic from being echoed back out of the speakers while
  // still giving the node a path to the destination, so it gets rendered.
  const mute = ctx.createGain(); mute.gain.value = 0
  node.connect(mute); mute.connect(ctx.destination)
  // An AudioContext built without a preceding user gesture starts suspended,
  // and a suspended context never renders — so the wake word would sit there
  // hearing nothing at all.
  if (ctx.state === "suspended") await ctx.resume().catch(() => {})

  return {
    /** Chunks discarded to stay current — 0 means it kept up with the mic. */
    get dropped() { return dropped },
    /** Chunks delivered by the audio worklet. */
    get received() { return received },
    /** Chunks actually run through the pipeline. */
    get inferred() { return inferred },
    /** Mean inference time per chunk, in ms. */
    get avgInferMs() { return inferred ? inferMs / inferred : 0 },
    stop() {
      stopped = true
      node.port.onmessage = null
      try { source.disconnect(); node.disconnect(); mute.disconnect() } catch {}
      ctx.close()
    },
  }
}
