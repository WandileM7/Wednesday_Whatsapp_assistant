"""Native background wake-word listener — the "JARVIS, wake up" daemon.

Runs outside the browser so the wake word works even with no tab open. It
listens to the microphone continuously and, when it hears the wake word,
launches (or focuses) the browser at the app URL. The in-browser wake word in
`frontend/src/lib/wakeWord.js` still handles the actual conversation once the
tab is up; this daemon's only job is to get the tab up, hands-free, on command.

The audio → mel → embedding → wake pipeline is byte-for-byte the same three
openWakeWord ONNX models the browser uses, reading them from the same cache
(`~/.cache/wednesday/voices/wakeword`). Keeping the maths identical means a word
that trips the browser trips the daemon and vice versa — one thing to tune.

WSL note: WSLg exposes the Windows *default* microphone as a PulseAudio "RDP
Source", so this captures whatever Windows has set as the default input. If the
daemon hears silence, the Windows default recording device is the wrong/muted
one — fix it in Windows Sound settings, which also fixes the browser.

Config (environment variables):
    WAKE_MODEL          wake model name (default: hey_wednesday)
    WAKE_THRESHOLD      score 0..1 to fire (default: 0.5)
    WAKE_REFRACTORY_S   min seconds between launches (default: 8)
    WAKE_URL            URL to open (default: http://localhost:1420/?wake=1)
    WAKE_LAUNCH_CMD     launcher; {url} is substituted
                        (default on WSL: explorer.exe "{url}")
    VOICE_CACHE_DIR     model cache dir (default: ~/.cache/wednesday/voices)
"""
from __future__ import annotations
import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s wake_daemon: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wake_daemon")

SAMPLE_RATE = 16000
CHUNK = 1280          # 80 ms — the mel model's natural step
MEL_FRAMES = 76       # frames the embedding model expects
EMB_WINDOW = 16       # embeddings the wake word model expects
EMB_DIM = 96


def _cache_dir() -> Path:
    raw = os.environ.get("VOICE_CACHE_DIR", "~/.cache/wednesday/voices")
    return Path(raw).expanduser() / "wakeword"


def _default_launch_cmd() -> str:
    """On WSL, open the Windows default browser at a URL. `explorer.exe <url>`
    is unreliable (it often opens File Explorer instead), so drive it through
    PowerShell's Start-Process, which always routes a URL to the default
    browser."""
    is_wsl = "microsoft" in Path("/proc/version").read_text().lower() \
        if Path("/proc/version").exists() else False
    if is_wsl:
        return "powershell.exe -NoProfile -Command Start-Process '{url}'"
    # Linux desktop fallback.
    return 'xdg-open "{url}"'


def _session(cache: Path, name: str) -> ort.InferenceSession:
    path = cache / f"{name}.onnx"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Train it first (~/wednesday-wakeword-train) "
            f"or use a built-in model via WAKE_MODEL=hey_jarvis_v0.1.")
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = 1
    return ort.InferenceSession(str(path), sess_options=so,
                                providers=["CPUExecutionProvider"])


class Pipeline:
    """Streaming openWakeWord front end: audio chunks in, scores out."""

    def __init__(self, cache: Path, model: str):
        self.mel = _session(cache, "melspectrogram")
        self.emb = _session(cache, "embedding_model")
        self.wake = _session(cache, model)
        self._mel_in = self.mel.get_inputs()[0].name
        self._emb_in = self.emb.get_inputs()[0].name
        self._wake_in = self.wake.get_inputs()[0].name
        self._mel_buf: list[np.ndarray] = []   # rolling mel frames (32 bins)
        self._emb_buf: list[np.ndarray] = []    # rolling embeddings (96-dim)

    def push(self, samples: np.ndarray) -> float | None:
        """Feed one 1280-sample chunk (float32, ±1.0). Returns a score once the
        pipeline is primed, else None."""
        # 1. audio → mel frames. The model wants 16-bit PCM magnitude, so scale
        #    the browser-style ±1.0 float up first; then normalise as openWakeWord
        #    does (x/10 + 2). Same as frontend/src/lib/wakeWord.js.
        scaled = (samples.astype(np.float32) * 32767.0).reshape(1, -1)
        mel_out = self.mel.run(None, {self._mel_in: scaled})[0].reshape(-1, 32)
        for frame in mel_out:
            self._mel_buf.append(frame / 10.0 + 2.0)
        if len(self._mel_buf) > MEL_FRAMES * 2:
            self._mel_buf = self._mel_buf[-MEL_FRAMES * 2:]
        if len(self._mel_buf) < MEL_FRAMES:
            return None

        # 2. last 76 mel frames → one 96-dim embedding
        window = np.stack(self._mel_buf[-MEL_FRAMES:]).astype(np.float32)
        emb_in = window.reshape(1, MEL_FRAMES, 32, 1)
        emb_out = self.emb.run(None, {self._emb_in: emb_in})[0].reshape(-1)
        self._emb_buf.append(emb_out.astype(np.float32))
        if len(self._emb_buf) > EMB_WINDOW:
            self._emb_buf = self._emb_buf[-EMB_WINDOW:]
        if len(self._emb_buf) < EMB_WINDOW:
            return None

        # 3. last 16 embeddings → score
        feats = np.stack(self._emb_buf).reshape(1, EMB_WINDOW, EMB_DIM)
        out = self.wake.run(None, {self._wake_in: feats})[0]
        return float(np.asarray(out).reshape(-1)[0])

    def reset_window(self):
        """Drop the embedding history so we don't re-fire on one utterance."""
        self._emb_buf = []


def _app_is_open(telemetry_url: str) -> bool:
    """True when a Wednesday tab is already connected (WebSocket client present).
    Lets us skip opening a new browser tab on every wake — the open tab's own
    in-browser wake word handles it, so we don't stack duplicate tabs."""
    try:
        import json
        import urllib.request
        with urllib.request.urlopen(telemetry_url, timeout=1.5) as resp:
            data = json.load(resp)
        return int(data.get("clients", 0)) > 0
    except Exception:  # noqa: BLE001 — network/parse errors mean "assume closed"
        return False


def _launch(cmd_template: str, url: str):
    cmd = cmd_template.replace("{url}", url)
    log.info("wake! launching: %s", cmd)
    try:
        subprocess.Popen(shlex.split(cmd),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        log.error("launch failed (%s): %s", cmd, exc)


def main() -> int:
    if not os.environ.get("PULSE_SERVER") and Path("/mnt/wslg/PulseServer").exists():
        os.environ["PULSE_SERVER"] = "unix:/mnt/wslg/PulseServer"

    model = os.environ.get("WAKE_MODEL", "hey_wednesday")
    threshold = float(os.environ.get("WAKE_THRESHOLD", "0.5"))
    refractory = float(os.environ.get("WAKE_REFRACTORY_S", "8"))
    # Reject detections when the mic is basically silent: a weak model can score
    # high on near-silence, so require recent audio at speech level before we
    # believe a wake. 0 disables the gate.
    min_level = float(os.environ.get("WAKE_MIN_LEVEL", "0.05"))
    url = os.environ.get("WAKE_URL", "http://localhost:1420/?wake=1")
    telemetry_url = os.environ.get("WAKE_TELEMETRY_URL", "http://localhost:8000/telemetry")
    launch_cmd = os.environ.get("WAKE_LAUNCH_CMD") or _default_launch_cmd()
    cache = _cache_dir()

    log.info("model=%s threshold=%.2f refractory=%.0fs cache=%s",
             model, threshold, refractory, cache)
    log.info("on wake → %s", launch_cmd.replace("{url}", url))

    try:
        pipe = Pipeline(cache, model)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2

    import soundcard as sc  # imported late so a missing default mic is a clean error
    try:
        mic = sc.default_microphone()
    except Exception as exc:  # noqa: BLE001
        log.error("no default microphone (%s). Check WSLg / Windows audio.", exc)
        return 3
    log.info("listening on '%s' — say \"%s\"…", mic.name,
             model.replace("_", " ").split(" v")[0])

    last_fire = 0.0
    primed_at = 0.0
    loud_seen = False
    mic_warned = False
    debug = os.environ.get("WAKE_DEBUG", "").strip() not in ("", "0", "false")
    last_hb = 0.0
    hb_peak = 0.0
    hb_score = 0.0
    recent_peak = 0.0        # decaying peak over the last ~1s, for the level gate
    with mic.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=CHUNK) as rec:
        while True:
            block = rec.record(numframes=CHUNK)          # (CHUNK, 1) float32 ±1
            samples = np.asarray(block, dtype=np.float32).reshape(-1)[:CHUNK]
            if samples.shape[0] < CHUNK:
                samples = np.pad(samples, (0, CHUNK - samples.shape[0]))
            peak = float(np.abs(samples).max())
            recent_peak = max(peak, recent_peak * 0.9)   # ~1s decay at 80ms/step
            if peak > 0.02:
                loud_seen = True
            score = pipe.push(samples)
            if score is None:
                continue
            if primed_at == 0.0:
                primed_at = time.monotonic()
            # Live heartbeat so you can SEE the mic level and the running score
            # rise as you speak. Enable with WAKE_DEBUG=1.
            if debug:
                hb_peak = max(hb_peak, peak)
                hb_score = max(hb_score, score)
                if time.monotonic() - last_hb > 2:
                    last_hb = time.monotonic()
                    bar = "#" * min(20, int(hb_peak * 40))
                    log.info("mic peak=%.3f |%-20s| top_score=%.3f", hb_peak, bar, hb_score)
                    hb_peak = 0.0
                    hb_score = 0.0
            # If the mic never carries real signal, the Windows default input is
            # the wrong/muted device (the WSLg trap). Say so once, loudly.
            if (not mic_warned and not loud_seen
                    and time.monotonic() - primed_at > 12):
                mic_warned = True
                log.warning(
                    "mic '%s' has been at the noise floor for 12s — the Windows "
                    "DEFAULT input device is probably wrong/muted. Set your "
                    "working mic as the Windows default (Sound settings), which "
                    "also fixes the browser.", mic.name)
            now = time.monotonic()
            if score >= threshold and now - last_fire > refractory:
                if recent_peak < min_level:
                    # High score with no real sound — a weak-model false positive.
                    log.info("ignoring wake (score=%.3f) — no speech-level audio "
                             "(peak=%.3f < %.3f)", score, recent_peak, min_level)
                    continue
                last_fire = now
                pipe.reset_window()
                if _app_is_open(telemetry_url):
                    # A tab is already listening — its in-browser wake word owns
                    # this. Don't stack another tab.
                    log.info("WAKE detected (score=%.3f, peak=%.3f) — app already "
                             "open, letting the tab handle it", score, recent_peak)
                    continue
                log.info("WAKE detected (score=%.3f, peak=%.3f)", score, recent_peak)
                _launch(launch_cmd, url)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.info("stopped")
