# imessage-service

iMessage sidecar for Wednesday, on top of [Photon Spectrum](https://photon.codes).

Same job as `whatsapp-service/`: own the long-lived connection to the provider,
POST inbound messages to the backend webhook, expose a small HTTP API the
backend calls to reply. The backend stays Python and never learns gRPC.

```
iMessage ──► Photon ──gRPC──► imessage-service ──POST──► backend /imessage/webhook
                     (stream)      (:3100)      ◄─POST── /api/sendText
```

Spectrum dials **out** over gRPC, so there is no public URL, no tunnel and no
inbound webhook to expose. The container publishes no port; only the backend
reaches it on the compose network.

## Why this and not the chat.db route

The other way to bridge iMessage is reading `~/Library/Messages/chat.db` and
sending through AppleScript — that's what `@photon-ai/imessage-kit`, BlueBubbles
and the Claude Code `imessage` plugin all do. It's free and fully local, but it
**requires a Mac** running the whole time. Photon's hosted relay is the only
option that works from Linux.

That trade is real: this is the only Wednesday channel where your messages pass
through someone else's infrastructure. It's off by default for that reason.

## Setup

1. Sign up at [photon.codes](https://photon.codes/pricing) and create a project.
   The free tier covers up to 10 users on a shared number pool.
2. Put the credentials in the repo's `.env`:

   ```bash
   IMESSAGE_ENABLED=true
   PHOTON_PROJECT_ID=...
   PHOTON_PROJECT_SECRET=...
   IMESSAGE_OWNER_HANDLE=+15551234567
   IMESSAGE_ALLOWED_HANDLES=+15551234567,+15559876543
   ```

3. Bring it up — it sits behind a compose profile so a normal `up` ignores it:

   ```bash
   docker compose --profile imessage up -d imessage-service
   ```

4. Check `GET /doctor` on the backend, or `curl localhost:3100/health` inside
   the network.

**`IMESSAGE_ALLOWED_HANDLES` empty means nobody gets through.** That's deliberate
and the opposite of the WhatsApp default: on a shared number pool anyone who
messages the line would otherwise reach your assistant. `/doctor` flags it.

Handles are compared on the bare identifier, so `+15551234567` matches whether
Photon reports it plain or as a chat GUID (`any;-;+15551234567`).

## Identity

`IMESSAGE_OWNER_HANDLE` shares `DEFAULT_USER`'s memory — same brain as the web
UI and your WhatsApp. Everyone else gets `im:<handle>`, their own history and
their own memories, so the other three people can't read yours.

## HTTP API

| Route | Purpose |
|---|---|
| `POST /api/sendText` `{chatId, text}` | reply into a known conversation |
| `POST /api/sendToHandle` `{handle, text}` | open a new one — reminders, heartbeat |
| `GET /health` | `{ready, configured, spaces, received, sent, error}` |

## Notes from verifying against the real SDK

Photon's published docs disagree with what `create-spectrum-project@0.9.0`
actually generates. Checked against `spectrum-ts@12.7.0`:

- **Import path.** The docs say `spectrum-ts/providers/imessage`. That subpath
  resolves to a 50-byte `export * from "@spectrum-ts/imessage"` stub, so it only
  works via hoisting. We import `@spectrum-ts/imessage` directly and declare it
  as a dependency, which is what Photon's own scaffold does.
- **Sender handle.** `User` is `{ __platform, id, kind? }` — `id` is the
  canonical address (E.164 or email, the same format `space.create()` accepts).
  `Message.sender` is `User | undefined`: system events like member joins and
  renames carry no actor.
- **Env var names.** The scaffold uses bare `PROJECT_ID` / `PROJECT_SECRET`.
  We pass ours in explicitly as `PHOTON_PROJECT_ID` / `PHOTON_PROJECT_SECRET`
  so they don't collide with anything else in the compose environment.

## Known rough edges

- Outbound is text only. Inbound handles text, voice notes (transcribed by
  `voice.transcribe`) and images (described by `vision.describe`); voice-note
  replies work on WhatsApp but aren't wired here yet.
- `npm install` reports moderate-severity advisories in the transitive tree.
  If your machine has an `allow-scripts` npm config it will also skip
  `protobufjs`'s postinstall, which the gRPC client needs; the container has no
  such config so it runs normally there. That's part of why this lives in its
  own image, as a non-root user, rather than in the backend.
