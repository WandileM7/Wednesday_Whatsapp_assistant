/**
 * Web Worker running MediaPipe GestureRecognizer inference off the main
 * thread, so the orb + webcam preview stay responsive on slow CPUs.
 * Returns hand landmarks (for pinch spin/zoom) plus classified static
 * gestures (Open_Palm, Pointing_Up, Thumb_Up, Thumb_Down, ...).
 *
 * Protocol:
 *   {type:"init"}       -> {type:"ready", delegate}
 *   {type:"reinit-cpu"} -> {type:"ready", delegate}   (recover from a degraded GPU delegate)
 *   {type:"frame", bitmap, ts} -> {type:"result", landmarks, labels, gestures}
 * Every frame message gets exactly one result message, even on error, so
 * the main thread's in-flight flag can never get stuck.
 */
import { FilesetResolver, GestureRecognizer } from "@mediapipe/tasks-vision";

const WASM_CDN =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task";

const MIN_GESTURE_SCORE = 0.5;

let recognizer: GestureRecognizer | null = null;

async function create(delegate: "GPU" | "CPU"): Promise<"GPU" | "CPU"> {
  recognizer?.close();
  recognizer = null;
  const fileset = await FilesetResolver.forVisionTasks(WASM_CDN);
  // The wasm loader is a UMD script (`var ModuleFactory = ...` + CJS/AMD
  // exports). In a module worker MediaPipe can't importScripts() it and falls
  // back to import(), which leaves ModuleFactory module-scoped — then
  // createFromOptions throws "ModuleFactory not set.". Run the script in
  // global scope ourselves so the factory lands on `self` first. MediaPipe
  // resets the global to undefined after each create, so check truthiness.
  if (!(self as { ModuleFactory?: unknown }).ModuleFactory) {
    const src = await (await fetch(fileset.wasmLoaderPath)).text();
    (0, eval)(src);
  }
  const options = {
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: "VIDEO" as const,
    numHands: 2,
    minHandDetectionConfidence: 0.6,
    minHandPresenceConfidence: 0.6,
    minTrackingConfidence: 0.6,
  };
  try {
    recognizer = await GestureRecognizer.createFromOptions(fileset, options);
    return delegate;
  } catch {
    // Some browsers/GPUs reject the GPU delegate — fall back to CPU
    recognizer = await GestureRecognizer.createFromOptions(fileset, {
      ...options,
      baseOptions: { ...options.baseOptions, delegate: "CPU" as const },
    });
    return "CPU";
  }
}

self.onmessage = async (e: MessageEvent) => {
  const msg = e.data;
  if (msg.type === "init") {
    self.postMessage({ type: "ready", delegate: await create("GPU") });
  } else if (msg.type === "reinit-cpu") {
    self.postMessage({ type: "ready", delegate: await create("CPU") });
  } else if (msg.type === "frame") {
    const bitmap: ImageBitmap = msg.bitmap;
    let landmarks: unknown[] = [];
    let labels: string[] = [];
    let gestures: string[] = [];
    if (recognizer) {
      try {
        const result = recognizer.recognizeForVideo(bitmap, msg.ts);
        landmarks = result.landmarks;
        labels = result.handedness.map((h) => h[0]?.categoryName ?? "?");
        gestures = result.gestures.map((g) => {
          const top = g[0];
          return top && top.score >= MIN_GESTURE_SCORE ? top.categoryName : "None";
        });
      } catch {
        // Drop the frame; the main thread's watchdog decides if we're degraded
      }
    }
    bitmap.close();
    self.postMessage({ type: "result", landmarks, labels, gestures });
  }
};
