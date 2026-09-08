/**
 * iMessage sidecar — Photon Spectrum ↔ Wednesday.
 *
 * Same shape as whatsapp-service/server-baileys.js: this process owns the
 * long-lived connection to the provider, POSTs inbound messages to the backend
 * webhook, and exposes a small HTTP API the backend calls to reply. The backend
 * stays Python and never learns gRPC.
 *
 * Spectrum holds a persistent gRPC stream to Photon, so there is no public URL
 * or inbound webhook to expose — only this container talks to the internet.
 */
import express from "express";
import { Spectrum, voice } from "spectrum-ts";
// iMessage voice notes must be M4A/AAC. ensureM4a transcodes whatever the
// backend's TTS produced (ogg/opus, for parity with WhatsApp) and measures the
// duration Messages needs to draw the waveform. It shells out to ffmpeg.
import { ensureM4a } from "@spectrum-ts/core/authoring";
// The docs say `spectrum-ts/providers/imessage`; that path resolves to a 50-byte
// `export * from "@spectrum-ts/imessage"` stub, so it only works by hoisting.
// Photon's own scaffold imports the real package directly — so do we.
import { imessage } from "@spectrum-ts/imessage";

const PORT = Number(process.env.PORT || 3100);
const HOOK_URL = process.env.IMESSAGE_HOOK_URL || "";
const API_TOKEN = process.env.API_TOKEN || "";
const PROJECT_ID = process.env.PHOTON_PROJECT_ID || "";
const PROJECT_SECRET = process.env.PHOTON_PROJECT_SECRET || "";

// Photos and voice notes ride inline as base64 in the webhook body. Anything
// larger than this is dropped rather than pushed through the JSON body — the
// text model can't use a 40MB video anyway.
const MAX_MEDIA_BYTES = 8 * 1024 * 1024;

const app = express();
app.use(express.json({ limit: "16mb" }));

let spectrum = null;
let im = null;
let ready = false;
let lastError = null;
let received = 0;
let sent = 0;

// Inbound spaces are cached so a reply can be routed back by id without a
// round-trip to Photon. `im.space.get()` is the fallback for a cold start.
const spaces = new Map();

const log = (...a) => console.log(new Date().toISOString(), "[imessage]", ...a);

/** Content bodies arrive as Blob / Buffer / Uint8Array depending on transport. */
async function toBuffer(data) {
  if (!data) return null;
  if (Buffer.isBuffer(data)) return data;
  if (data instanceof Uint8Array) return Buffer.from(data);
  if (data instanceof ArrayBuffer) return Buffer.from(new Uint8Array(data));
  if (typeof data.arrayBuffer === "function") return Buffer.from(await data.arrayBuffer());
  return null;
}

/**
 * `User.id` is the canonical address — E.164 phone or email, the same handle
 * format `space.create()` accepts — so it is what the backend's allowlist keys
 * on. `sender` is `User | undefined`: system events (member joins, renames)
 * carry no actor, and outbound sends often can't synthesize one.
 */
function senderHandle(message, space) {
  return String(message.sender?.id || space?.id || "unknown");
}

async function toPayload(space, message) {
  const base = {
    id: message.id,
    chatId: space.id,
    sender: senderHandle(message, space),
    platform: message.platform || "imessage",
    timestamp: message.timestamp instanceof Date
      ? message.timestamp.toISOString()
      : new Date().toISOString(),
  };

  const content = message.content || {};
  switch (content.type) {
    case "text":
      return { ...base, type: "text", text: content.text || "" };

    case "voice":
    case "attachment": {
      let buf = null;
      try {
        buf = await toBuffer(await content.read?.());
      } catch (err) {
        log("attachment read failed:", err?.message || err);
      }
      const mimetype = content.mimeType || (content.type === "voice" ? "audio/m4a" : "");
      const isVoice = content.type === "voice" || mimetype.startsWith("audio/");
      const isImage = mimetype.startsWith("image/");
      if (!buf || buf.length > MAX_MEDIA_BYTES || (!isVoice && !isImage)) {
        // Still worth telling the model something arrived.
        return {
          ...base, type: "text",
          text: `[The user sent ${content.name || "an attachment"} I can't read.]`,
        };
      }
      return {
        ...base,
        type: isVoice ? "voice" : "image",
        text: content.caption || "",
        mimetype: mimetype || (isVoice ? "audio/m4a" : "image/jpeg"),
        media_b64: buf.toString("base64"),
      };
    }

    default:
      // Reactions, edits, unsends and the rest: nothing for the agent to do.
      return null;
  }
}

async function forward(payload) {
  if (!HOOK_URL) return;
  try {
    const r = await fetch(HOOK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!r.ok) log("webhook returned", r.status);
  } catch (err) {
    log("webhook post failed:", err?.message || err);
  }
}

/**
 * Photon wants a prefixed guid — "any;-;+2782…" for a direct chat, "any;+;…"
 * for a group — and rejects a bare handle at send time with an error that names
 * the format. Inbound events already carry a well-formed `space.id`, so this
 * only bites callers that address someone by phone number or email: the
 * send-to-handle path, and any end-to-end test that synthesises a webhook.
 * Those failed with a 502 that looked like the sidecar being down.
 */
function normaliseChatId(chatId) {
  return /^[a-z]+;[-+];/i.test(chatId) ? chatId : `any;-;${chatId}`;
}

async function resolveSpace(chatId) {
  if (spaces.has(chatId)) return spaces.get(chatId);
  if (!im) return null;
  const guid = normaliseChatId(chatId);
  try {
    const space = await im.space.get(guid);
    // Cache under the caller's spelling too, so a bare handle is one lookup
    // next time rather than a round trip that re-derives the same guid.
    if (space) { spaces.set(chatId, space); spaces.set(guid, space); }
    return space;
  } catch {
    return null;
  }
}

/** Reply into an existing conversation. The backend's normal path. */
app.post("/api/sendText", async (req, res) => {
  const { chatId, text } = req.body || {};
  if (!chatId || !text) return res.status(400).json({ error: "chatId and text required" });
  const space = await resolveSpace(chatId);
  if (!space) return res.status(404).json({ error: `unknown space ${chatId}` });
  try {
    await space.responding(async () => { await space.send(text); });
    sent++;
    res.json({ status: "ok" });
  } catch (err) {
    log("send failed:", err?.message || err);
    res.status(502).json({ error: String(err?.message || err) });
  }
});

/**
 * Reply as a voice note. The backend sends whatever its TTS chain produced —
 * ogg/opus, same as the WhatsApp path — and the transcode to M4A happens here,
 * because ensureM4a ships with the SDK and knows the duration Messages wants.
 */
app.post("/api/sendVoice", async (req, res) => {
  const { chatId, audio_b64, mimeType } = req.body || {};
  if (!chatId || !audio_b64) return res.status(400).json({ error: "chatId and audio_b64 required" });
  const space = await resolveSpace(chatId);
  if (!space) return res.status(404).json({ error: `unknown space ${chatId}` });
  try {
    const raw = Buffer.from(audio_b64, "base64");
    const { buffer, duration } = await ensureM4a(raw, mimeType || "audio/ogg");
    await space.responding(async () => {
      await space.send(voice(buffer, {
        mimeType: "audio/mp4", name: "reply.m4a",
        ...(duration ? { duration } : {}),
      }));
    });
    sent++;
    res.json({ status: "ok", duration: duration ?? null });
  } catch (err) {
    // The backend falls back to text on a non-2xx, so a missing ffmpeg costs a
    // waveform, never the answer.
    log("voice send failed:", err?.message || err);
    res.status(502).json({ error: String(err?.message || err) });
  }
});

/**
 * Open a conversation with a handle we've never heard from. This is what the
 * scheduler needs for reminders and the proactive heartbeat — without it
 * Wednesday can only ever answer, never start.
 */
app.post("/api/sendToHandle", async (req, res) => {
  const { handle, text } = req.body || {};
  if (!handle || !text) return res.status(400).json({ error: "handle and text required" });
  if (!im) return res.status(503).json({ error: "spectrum not connected" });
  try {
    const user = await im.user(handle);
    const dm = await im.space.create(user);
    spaces.set(dm.id, dm);
    await dm.send(text);
    sent++;
    res.json({ status: "ok", chatId: dm.id });
  } catch (err) {
    log("proactive send failed:", err?.message || err);
    res.status(502).json({ error: String(err?.message || err) });
  }
});

app.get("/health", (_req, res) => {
  res.status(ready ? 200 : 503).json({
    status: ready ? "ok" : "connecting",
    ready,
    configured: Boolean(PROJECT_ID && PROJECT_SECRET),
    webhook: HOOK_URL ? "configured" : "missing",
    spaces: spaces.size,
    received,
    sent,
    error: lastError,
  });
});

async function connect() {
  if (!PROJECT_ID || !PROJECT_SECRET) {
    lastError = "PHOTON_PROJECT_ID / PHOTON_PROJECT_SECRET not set";
    log(lastError, "— idling; the backend will report this via /doctor");
    return;
  }
  spectrum = await Spectrum({
    projectId: PROJECT_ID,
    projectSecret: PROJECT_SECRET,
    providers: [imessage.config()],
  });
  im = imessage(spectrum);
  ready = true;
  lastError = null;
  log("connected to Photon Spectrum");

  for await (const [space, message] of spectrum.messages) {
    // Our own replies come back down the same stream.
    if (message.direction === "outbound") continue;
    spaces.set(space.id, space);
    received++;
    const payload = await toPayload(space, message);
    if (payload) void forward(payload);
  }
}

/** The stream can drop; back off and re-establish rather than dying silently. */
async function run() {
  let attempt = 0;
  for (;;) {
    try {
      await connect();
      if (!PROJECT_ID || !PROJECT_SECRET) return;  // nothing to retry into
      log("message stream ended, reconnecting");
      attempt = 0;
    } catch (err) {
      lastError = String(err?.message || err);
      log("connection failed:", lastError);
    }
    ready = false;
    const delay = Math.min(30000, 1000 * 2 ** attempt++);
    await new Promise(r => setTimeout(r, delay));
  }
}

app.listen(PORT, () => log(`sidecar listening on :${PORT}`));
run();
