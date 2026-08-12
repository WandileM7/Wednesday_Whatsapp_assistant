// AudioWorkletProcessor: slices the mic into the 1280-sample (80ms) chunks the
// wake-word pipeline steps on, and posts them to the main thread.
//
// This runs on the audio render thread, which is why it exists. The previous
// ScriptProcessorNode ran on the main thread and, asked for a non-native 16kHz
// while the browser resampled 48k, delivered roughly every 1.5s instead of
// every 128ms — the pipeline saw about 4% of the audio and missed half of what
// was said. A worklet is called for every 128-frame render quantum regardless
// of what the page is doing.
//
// Deliberately does no inference: ONNX has no business on the audio thread,
// where overrunning the quantum budget causes dropouts.

const CHUNK = 1280

class WakeWordChunker extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buf = new Float32Array(CHUNK)
    this._filled = 0
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0]
    // No input connected yet (or a silent render quantum): stay alive.
    if (!input) return true

    let read = 0
    while (read < input.length) {
      const take = Math.min(CHUNK - this._filled, input.length - read)
      this._buf.set(input.subarray(read, read + take), this._filled)
      this._filled += take
      read += take
      if (this._filled === CHUNK) {
        // Transfer rather than copy: the buffer crosses threads with no clone.
        const out = this._buf.slice()
        this.port.postMessage(out, [out.buffer])
        this._filled = 0
      }
    }
    return true
  }
}

registerProcessor("wake-word-chunker", WakeWordChunker)
