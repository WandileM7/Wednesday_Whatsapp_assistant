/**
 * Webcam hand-gesture tracker, adapted from ULTRON
 * https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds
 * MIT License, Copyright (c) 2026 Sagar Tamang.
 *
 * Continuous controls: one pinched hand spins the orb; two pinched hands
 * zoom by spreading apart or together (pinch uses hysteresis); an open
 * palm swats the orb around and pushes/pulls to zoom (hand size = depth);
 * a moving fist grabs and drags it.
 * Held gestures (~0.7s, stationary, not pinching): fist = hush (stop
 * speaking), victory = reset view, pointing up = mic, thumbs up/down =
 * voice on/off, ILoveYou = power flare.
 *
 * Inference runs in a Web Worker (handWorker.ts) with at most one frame
 * in flight, so a slow CPU degrades frame rate instead of building up
 * seconds of lag on the main thread.
 */
export type GestureMode = "idle" | "spin" | "zoom";

/** Actions fired by held static gestures. */
export type GestureAction = "reset" | "mic" | "voice_on" | "voice_off" | "hush" | "flare";

export interface TrackerStatus {
  hands: number;
  mode: GestureMode;
  /** Static gesture currently detected (before the hold completes), if any. */
  gesture: string | null;
  /** Rounded inference rate; 0 until measured. */
  fps: number;
}

export interface HandTrackerCallbacks {
  /** Called when a single pinched hand drags: deltas in mirrored normalized coords. */
  onRotate(deltaTheta: number, deltaPhi: number): void;
  /** Called when both hands pinch and spread/close: multiply camera distance by factor. */
  onZoom(factor: number): void;
  /** Called once per hold when a static gesture completes. */
  onGesture(action: GestureAction): void;
  onStatus(status: TrackerStatus): void;
}

interface Landmark {
  x: number;
  y: number;
}

// Landmark indices (MediaPipe hand model)
const WRIST = 0;
const THUMB_TIP = 4;
const INDEX_TIP = 8;
const MIDDLE_MCP = 9;

// Pinch hysteresis: thumb–index distance relative to hand size
const PINCH_ON = 0.32;
const PINCH_OFF = 0.45;

// How strongly hand movement rotates the orb (radians per normalized unit)
const ROTATE_SPEED = 5.0;
// Smoothing factor for grab-point tracking (0..1, higher = snappier)
const SMOOTHING = 0.4;

// A static gesture must be held this long to fire its action
const GESTURE_HOLD_MS = 700;

// Cap inference rate; leaves headroom for the orb's render loop
const MIN_FRAME_INTERVAL_MS = 66;
// If a frame gets no result for this long, assume it was lost and move on
const WATCHDOG_MS = 3000;
// Average round-trip above this on the GPU delegate = degraded (leaking GPU
// contexts show exactly this "starts fine, gets slower" pattern) -> go CPU
const DEGRADED_RTT_MS = 400;
const RTT_SAMPLES = 8;
const HOLD_ACTIONS: Record<string, GestureAction> = {
  Closed_Fist: "hush",
  Victory: "reset",
  Pointing_Up: "mic",
  Thumb_Up: "voice_on",
  Thumb_Down: "voice_off",
  ILoveYou: "flare",
};

// Open palm / fist hologram controls
const PALM_ROTATE_SPEED = 4.0;
// Movement below this (normalized units/frame) counts as holding still
const MOVE_EPS = 0.008;
// Hand-size change needed before palm push/pull zooms (filters jitter)
const DEPTH_DEADZONE = 0.015;

interface Point {
  x: number;
  y: number;
}

interface HandState {
  pinching: boolean;
  grab: Point; // smoothed pinch midpoint, mirrored
}

export class HandTracker {
  private video: HTMLVideoElement;
  private overlay: HTMLCanvasElement;
  private callbacks: HandTrackerCallbacks;
  private worker: Worker | null = null;
  private stream: MediaStream | null = null;
  private rafId = 0;
  private running = false;
  private ready = false;
  private busy = false;
  private lastVideoTime = -1;

  // keyed by handedness label so state survives re-ordering between frames
  private handStates = new Map<string, HandState>();
  private prevMode: GestureMode = "idle";
  private prevSpinGrab: Point | null = null;
  private prevZoomDist: number | null = null;
  private lastStatus: TrackerStatus = { hands: 0, mode: "idle", gesture: null, fps: 0 };
  private holdName: string | null = null;
  private holdSince = 0;
  private holdArmed = true;
  // open-palm / fist control hand: smoothed position + apparent size (depth)
  private ctl: { gesture: string; pos: Point; scale: number } | null = null;
  private delegate: "GPU" | "CPU" = "GPU";
  private sendTs = 0;
  private rtts: number[] = [];
  private fps = 0;

  constructor(
    video: HTMLVideoElement,
    overlay: HTMLCanvasElement,
    callbacks: HandTrackerCallbacks,
  ) {
    this.video = video;
    this.overlay = overlay;
    this.callbacks = callbacks;
  }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: "user" },
      audio: false,
    });
    this.video.srcObject = this.stream;
    await this.video.play();

    this.worker = new Worker(new URL("./handWorker.ts", import.meta.url), {
      type: "module",
    });
    this.worker.onmessage = (e: MessageEvent) => {
      const msg = e.data;
      if (msg.type === "ready") {
        this.delegate = msg.delegate;
        this.rtts = [];
        this.ready = true;
      } else if (msg.type === "result") {
        this.busy = false;
        if (!this.running) return;
        this.trackRtt(performance.now() - this.sendTs);
        this.processHands(msg.landmarks, msg.labels, msg.gestures);
        this.drawOverlay(msg.landmarks);
      }
    };
    // A crashed worker must not leave the frame loop stuck waiting
    this.worker.onerror = () => { this.busy = false; };
    this.worker.postMessage({ type: "init" });

    this.running = true;
    this.loop();
  }

  stop(): void {
    this.running = false;
    this.ready = false;
    this.busy = false;
    cancelAnimationFrame(this.rafId);
    this.worker?.terminate();
    this.worker = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.video.srcObject = null;
    this.handStates.clear();
    this.prevMode = "idle";
    this.prevSpinGrab = null;
    this.prevZoomDist = null;
    this.holdName = null;
    this.holdArmed = true;
    this.ctl = null;
    this.rtts = [];
    this.fps = 0;
    const ctx = this.overlay.getContext("2d");
    ctx?.clearRect(0, 0, this.overlay.width, this.overlay.height);
    this.emitStatus({ hands: 0, mode: "idle", gesture: null, fps: 0 });
  }

  private loop = () => {
    if (!this.running) return;
    this.rafId = requestAnimationFrame(this.loop);

    const now = performance.now();
    // Watchdog: a frame whose result never came back must not block forever
    if (this.busy && now - this.sendTs > WATCHDOG_MS) this.busy = false;

    if (!this.ready || this.busy || !this.worker || this.video.readyState < 2) return;
    if (now - this.sendTs < MIN_FRAME_INTERVAL_MS) return;
    if (this.video.currentTime === this.lastVideoTime) return;
    this.lastVideoTime = this.video.currentTime;

    // One frame in flight at a time: a slow inference drops frames
    // instead of queueing them up behind the main thread.
    this.busy = true;
    this.sendTs = now;
    createImageBitmap(this.video).then(
      (bitmap) => {
        if (!this.running || !this.worker) {
          bitmap.close();
          this.busy = false;
          return;
        }
        this.worker.postMessage({ type: "frame", bitmap, ts: performance.now() }, [bitmap]);
      },
      () => { this.busy = false; },
    );
  };

  private trackRtt(rtt: number): void {
    this.rtts.push(rtt);
    if (this.rtts.length > RTT_SAMPLES) this.rtts.shift();
    const avg = this.rtts.reduce((a, b) => a + b, 0) / this.rtts.length;
    this.fps = Math.round(1000 / Math.max(avg, MIN_FRAME_INTERVAL_MS));
    // GPU delegate degrading over time (leaks on some drivers): rebuild on CPU,
    // which is slower per frame but stays flat.
    if (this.delegate === "GPU" && this.rtts.length >= RTT_SAMPLES && avg > DEGRADED_RTT_MS) {
      this.ready = false;
      this.rtts = [];
      this.delegate = "CPU";
      this.worker?.postMessage({ type: "reinit-cpu" });
    }
  }

  private processHands(landmarks: Landmark[][], labels: string[], gestures: string[]): void {
    const pinchedGrabs: Point[] = [];
    const seen = new Set<string>();

    landmarks.forEach((lm, i) => {
      const label = labels[i];
      seen.add(label);

      const handScale = dist2d(lm[WRIST], lm[MIDDLE_MCP]);
      if (handScale < 1e-6) return;
      const pinchRatio = dist2d(lm[THUMB_TIP], lm[INDEX_TIP]) / handScale;

      // Mirrored so hand-right = screen-right from the user's perspective
      const raw: Point = {
        x: 1 - (lm[THUMB_TIP].x + lm[INDEX_TIP].x) / 2,
        y: (lm[THUMB_TIP].y + lm[INDEX_TIP].y) / 2,
      };

      let state = this.handStates.get(label);
      if (!state) {
        state = { pinching: false, grab: raw };
        this.handStates.set(label, state);
      }

      // Hysteresis so the pinch doesn't flicker on/off at the threshold
      if (state.pinching && pinchRatio > PINCH_OFF) state.pinching = false;
      else if (!state.pinching && pinchRatio < PINCH_ON) state.pinching = true;

      state.grab = {
        x: state.grab.x + (raw.x - state.grab.x) * SMOOTHING,
        y: state.grab.y + (raw.y - state.grab.y) * SMOOTHING,
      };

      if (state.pinching) pinchedGrabs.push(state.grab);
    });

    // Drop state for hands that left the frame
    for (const key of this.handStates.keys()) {
      if (!seen.has(key)) this.handStates.delete(key);
    }

    const mode: GestureMode =
      pinchedGrabs.length >= 2 ? "zoom" : pinchedGrabs.length === 1 ? "spin" : "idle";

    // Reset reference points on any mode change to avoid jumps
    if (mode !== this.prevMode) {
      this.prevSpinGrab = null;
      this.prevZoomDist = null;
      this.prevMode = mode;
    }

    if (mode === "spin") {
      const grab = pinchedGrabs[0];
      if (this.prevSpinGrab) {
        const dx = grab.x - this.prevSpinGrab.x;
        const dy = grab.y - this.prevSpinGrab.y;
        if (Math.abs(dx) > 1e-4 || Math.abs(dy) > 1e-4) {
          this.callbacks.onRotate(dx * ROTATE_SPEED, dy * ROTATE_SPEED);
        }
      }
      this.prevSpinGrab = grab;
    } else if (mode === "zoom") {
      const d = Math.hypot(
        pinchedGrabs[0].x - pinchedGrabs[1].x,
        pinchedGrabs[0].y - pinchedGrabs[1].y,
      );
      if (this.prevZoomDist && d > 1e-4) {
        // Spread hands apart -> factor < 1 -> camera moves closer
        const factor = Math.min(1.18, Math.max(0.85, this.prevZoomDist / d));
        this.callbacks.onZoom(factor);
      }
      this.prevZoomDist = d;
    }

    // Static/hologram gestures only count while no hand is pinch-interacting
    let active: string | null = null;
    let handIdx = -1;
    if (mode === "idle") {
      for (let i = 0; i < landmarks.length; i++) {
        const g = gestures[i];
        if (g && g !== "None" && (g in HOLD_ACTIONS || g === "Open_Palm")) {
          active = g; handIdx = i; break;
        }
      }
    }

    // Open palm swats the orb around and pushes/pulls to zoom; a moving
    // fist drags it. Any real movement also cancels the hold timer below.
    let moved = false;
    if (active === "Open_Palm" || active === "Closed_Fist") {
      const lm = landmarks[handIdx];
      const raw: Point = { x: 1 - lm[MIDDLE_MCP].x, y: lm[MIDDLE_MCP].y };
      const scale = dist2d(lm[WRIST], lm[MIDDLE_MCP]);
      if (this.ctl && this.ctl.gesture === active) {
        const pos = {
          x: this.ctl.pos.x + (raw.x - this.ctl.pos.x) * SMOOTHING,
          y: this.ctl.pos.y + (raw.y - this.ctl.pos.y) * SMOOTHING,
        };
        const dx = pos.x - this.ctl.pos.x;
        const dy = pos.y - this.ctl.pos.y;
        if (Math.hypot(dx, dy) > MOVE_EPS) {
          moved = true;
          this.callbacks.onRotate(dx * PALM_ROTATE_SPEED, dy * PALM_ROTATE_SPEED);
        }
        const smScale = this.ctl.scale + (scale - this.ctl.scale) * SMOOTHING;
        if (active === "Open_Palm" && smScale > 1e-6) {
          // Hand growing in frame = pushing toward the camera = zoom in
          const ratio = this.ctl.scale / smScale;
          if (Math.abs(ratio - 1) > DEPTH_DEADZONE) {
            moved = true;
            this.callbacks.onZoom(Math.min(1.12, Math.max(0.89, ratio)));
          }
        }
        this.ctl.pos = pos;
        this.ctl.scale = smScale;
      } else {
        this.ctl = { gesture: active, pos: raw, scale };
      }
    } else {
      this.ctl = null;
    }

    // Hold-to-fire, stationary hands only (a dragging fist is a grab, not a hush)
    const holdable = active && active in HOLD_ACTIONS ? active : null;
    if (!holdable) {
      this.holdName = null;
      this.holdArmed = true;
    } else if (holdable !== this.holdName) {
      this.holdName = holdable;
      this.holdSince = performance.now();
      this.holdArmed = true;
    } else if (moved) {
      this.holdSince = performance.now();
    } else if (this.holdArmed && performance.now() - this.holdSince >= GESTURE_HOLD_MS) {
      this.holdArmed = false; // fire once, re-arm when the gesture releases
      this.callbacks.onGesture(HOLD_ACTIONS[holdable]);
    }

    this.emitStatus({ hands: landmarks.length, mode, gesture: active, fps: this.fps });
  }

  private emitStatus(status: TrackerStatus): void {
    if (
      status.hands !== this.lastStatus.hands ||
      status.mode !== this.lastStatus.mode ||
      status.gesture !== this.lastStatus.gesture ||
      Math.abs(status.fps - this.lastStatus.fps) >= 3
    ) {
      this.lastStatus = status;
      this.callbacks.onStatus(status);
    }
  }

  private drawOverlay(landmarks: Landmark[][]): void {
    const ctx = this.overlay.getContext("2d");
    if (!ctx) return;
    const { width, height } = this.overlay;
    ctx.clearRect(0, 0, width, height);

    for (const lm of landmarks) {
      const thumb = lm[THUMB_TIP];
      const index = lm[INDEX_TIP];
      // Overlay canvas sits on the mirrored video preview, so mirror x here too
      const tx = (1 - thumb.x) * width;
      const ty = thumb.y * height;
      const ix = (1 - index.x) * width;
      const iy = index.y * height;

      const handScale = dist2d(lm[WRIST], lm[MIDDLE_MCP]);
      const pinched =
        handScale > 1e-6 && dist2d(thumb, index) / handScale < PINCH_ON;

      ctx.strokeStyle = pinched ? "#ffcc66" : "rgba(255,170,48,0.5)";
      ctx.lineWidth = pinched ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(ix, iy);
      ctx.stroke();

      ctx.fillStyle = pinched ? "#ffcc66" : "rgba(255,170,48,0.7)";
      for (const [x, y] of [
        [tx, ty],
        [ix, iy],
      ]) {
        ctx.beginPath();
        ctx.arc(x, y, pinched ? 5 : 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
}

function dist2d(a: Landmark, b: Landmark): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}
