from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    public_url: str = "http://localhost:8000"
    session_secret: str = "change-me-in-production"
    # Stable identity: web + owner's WhatsApp share this user's history/brain
    default_user: str = "wandile"
    # Bearer token for HTTP + WS; empty disables auth (trusted local dev only)
    api_token: str = ""
    # This WhatsApp sender is the owner and shares default_user's identity
    whatsapp_owner_jid: str = ""
    # Comma-separated JIDs allowed to talk to Wednesday; empty = anyone
    whatsapp_allowed_jids: str = ""
    # Ollama context window for the chat model. The fixed prompt (persona +
    # tool schemas) is ~2.6k tokens and history adds up to history_budget_tokens,
    # so the default 4096 over-subscribes and Ollama silently truncates the
    # prompt (dropping tool schemas / system prompt). 8192 leaves room for the
    # prompt plus the reply. Raise for longer memory, lower to save RAM/CPU.
    num_ctx: int = 8192
    # Prompt slice of the context window left for history (≈4 chars/token)
    history_budget_tokens: int = 2500
    # Offer only the tools this turn implicates (see toolrouter) instead of all
    # 26 every time: 47-78% off the schema block, and far better tool selection
    # on a small model, which is the whole point.
    #
    # The cost to weigh is that tool schemas live in the prompt *prefix*, so
    # changing the offered set changes the prefix and Ollama re-evaluates from
    # the first differing token. Whether that matters is entirely a question of
    # prefill speed, measured 2026-08-11 on the same prompt:
    #     ipex-llm SYCL on the Arc iGPU   71-86 tok/s   <- what we actually run
    #     stock ollama, CPU-only           6.2 tok/s    <- the fallback
    # At 71 tok/s a worst-case re-prefill of the whole ~5k-token prompt is about
    # a minute, well inside ollama_timeout, and routing pays for itself by
    # shrinking every cold prompt. So: on.
    #
    # If the SYCL backend ever fails to load, Ollama falls back to CPU silently
    # — note `ollama ps` reports "100% CPU" even when all 29 layers ARE on the
    # GPU, so that column cannot be used to tell. Check the server log for
    # "offloaded 29/29 layers to GPU" instead. On the CPU fallback the trade
    # inverts (a re-prefill becomes ~13 minutes against a 300s timeout) and this
    # should go back to False.
    route_tools: bool = True
    # Hard cap on one tool result once it is serialised into the prompt.
    # Individual tools truncate their own text, but web_search returns a *list*
    # of rows at 2000 chars each, and the JSON of five of them outgrew the whole
    # history budget — evicting the conversation the result was meant to inform.
    # Half the budget, so a result and the thread it belongs to always coexist.
    tool_result_chars: int = 4800
    # Read timeout for one interactive model round. Ample on the iGPU (71-86
    # tok/s prefill, so even a cold ~5k-token prompt lands in ~70s). Kept
    # generous because the CPU fallback is 6.2 tok/s, and because a turn with
    # two or three tool hops re-evaluates a growing prompt each time.
    ollama_timeout: float = 300.0
    # Proactive check-ins every N minutes; 0 = off (default until trusted)
    heartbeat_minutes: int = 0
    # No proactive pings between these hours (24h clock, "start-end", wraps midnight)
    heartbeat_quiet: str = "22-07"
    # Hard cap on proactive pings per calendar day
    heartbeat_daily_cap: int = 8
    # Sandboxed run_code tool (docker, no network); off until explicitly enabled
    enable_code_execution: bool = False
    # browse_web: browser-use driving a headless Chromium with the local model.
    # Off by default — it needs Chromium installed and a model strong enough to
    # not wander. Empty browser_model reuses ollama_model.
    enable_browser_use: bool = False
    browser_model: str = ""
    browser_timeout: float = 180.0
    # Model for background utility calls (summaries, fact extraction). Set this
    # to a *different* (smaller) model than ollama_model: sharing one model
    # makes each background call evict the interactive prompt's KV cache, so
    # the next reply re-evaluates the whole ~2.2k-token prefix from scratch.
    # A distinct utility model runs on its own Ollama runner and avoids that.
    # Empty = reuse ollama_model (simpler, but pays the re-eval cost).
    ollama_model_utility: str = ""
    # Tools that pause and ask before running (comma-separated)
    approval_required_tools: str = ("gmail_send,calendar_create_event,"
                                    "calendar_update_event,calendar_delete_event,"
                                    "run_code,browse_web")
    # MCP servers (Claude-Desktop-shaped JSON). Missing file = feature off.
    mcp_config: str = "mcp.json"
    # Every registered tool's schema rides in every prompt, so cap the total an
    # over-eager server can add before it crowds out history.
    mcp_max_tools: int = 24
    mcp_connect_timeout: float = 20.0
    # MCP tools are third-party code with side effects: gate them behind the
    # same approval prompt as run_code. "always" still applies per tool.
    mcp_require_approval: bool = True
    # Fallback for get_weather when the model doesn't pass a location — the
    # user's home city, so "what's the weather?" answers without asking. Set to
    # "" to force Wednesday to ask instead.
    default_location: str = "Cape Town"
    # Ambient listening: when hands-free is on and this is true, Wednesday only
    # answers utterances addressed to her by name (see backend/wakeword.py).
    wake_word: str = "wednesday"
    wake_word_required: bool = False
    # Vision: images sent on WhatsApp (and the see_image/look tools) are
    # described by a VLM, and the description enters the text conversation.
    enable_vision: bool = True
    # Empty = the hosted chat model when one is configured (most are
    # multimodal), else local moondream — see vision._model().
    vision_model: str = ""
    # Home Assistant: smart-home control. Off unless both are set.
    # HA_URL=http://homeassistant.local:8123, token from your HA profile page.
    ha_url: str = ""
    ha_token: str = ""
    # Folder of .md/.txt notes Wednesday can quote from (search_documents).
    documents_dir: str = "documents"
    # RSS/Atom feeds for news_digest, comma-separated.
    news_feeds: str = ("https://feeds.bbci.co.uk/news/world/rss.xml,"
                       "https://www.aljazeera.com/xml/rss/all.xml")
    # Email channel: polls IMAP, replies via SMTP. Off unless address+password set.
    email_address: str = ""
    email_password: str = ""          # app password, not your real one
    email_imap_host: str = "imap.gmail.com"
    email_smtp_host: str = "smtp.gmail.com"
    email_poll_seconds: int = 60
    # Only these senders are answered; the first one maps to default_user
    email_allowed_senders: str = ""
    # Wyoming server: makes Wednesday a Home Assistant voice assistant (STT +
    # conversation + TTS). The protocol has no auth, so this is trusted-LAN
    # only — keep the port off the internet.
    enable_wyoming: bool = False
    wyoming_uri: str = "tcp://0.0.0.0:10700"
    wyoming_language: str = "en"
    wyoming_user: str = ""               # empty = share default_user's brain
    # Hosted OpenAI-compatible chat backend (Groq, Cerebras, OpenRouter, vLLM…).
    # Set base_url + api_key to make replies fast; leave unset and everything
    # stays local on Ollama. Local is always the fallback — see backend/llm.py.
    # e.g. LLM_BASE_URL=https://api.groq.com/openai/v1
    #      LLM_MODEL=llama-3.3-70b-versatile
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.6
    llm_timeout: float = 120.0
    # Cap how many tool schemas are offered per request; 0 = all of them.
    # The full registry is ~3.6k tokens on every call, which exhausts a
    # rate-limited hosted tier in one turn (Groq free is 12k tokens/min) and
    # costs prefill time locally. Capping trades a little tool recall for a lot
    # of headroom — core tools are always offered, the rest ranked by relevance.
    # Applied after route_tools has already narrowed the set by intent: routing
    # picks *which* groups are relevant, this caps how many survive regardless.
    max_tools_per_request: int = 0
    ollama_host: str = "http://localhost:11434"
    # Matches the README and .env.example. A capable tool-caller is needed:
    # the fixed prompt (persona + tool schemas) is ~2.2k tokens, so a small
    # model both reasons poorly and crowds its own context window.
    ollama_model: str = "llama3.1:8b"
    whisper_model: str = "base"          # faster-whisper size: tiny/base/small/medium
    piper_voice: str = "en_GB-alba-medium"
    # Fish Audio hosted TTS — used when a key is set, otherwise Piper (local, free)
    fish_api_key: str = ""
    fish_voice_id: str = "bf6b1cbc1a394928adfb6927726d8b17"
    fish_tts_model: str = "s2.1-pro-free"
    fish_speed: float = 1.0
    # Kokoro: local 82M ONNX voice, far more natural than Piper. Opt-in
    # because the model is a ~310MB first-run download (pip install kokoro-onnx).
    enable_kokoro: bool = False
    kokoro_voice: str = "bf_emma"        # b=British f=female; af_heart, bm_george…
    kokoro_lang: str = "en-gb"
    kokoro_speed: float = 1.0
    # Force one engine ("fish"/"kokoro"/"piper"); empty picks automatically.
    # Piper stays the last-resort fallback either way.
    tts_engine: str = ""
    voice_cache_dir: str = "~/.cache/wednesday/voices"
    # Web search: a hosted provider is used when its key is set, otherwise the
    # free DuckDuckGo scrape (always the fallback). Tavily is LLM-tuned and can
    # return page content directly; Brave is a general web index.
    # SearXNG is preferred over both when set: self-hosted, keyless, no quota.
    # The shipped docker-compose brings one up at http://searxng:8080.
    searxng_url: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./wednesday.db"
    # Hybrid memory retrieval (FTS5 + sqlite-vec). The index is a sidecar
    # SQLite file — safe to delete, rebuilt from the memories table on demand —
    # so it works even when database_url points at Postgres.
    enable_memory_embeddings: bool = True
    embed_model: str = "nomic-embed-text"     # ollama pull nomic-embed-text
    vector_db_path: str = "./wednesday-vectors.db"
    waha_url: str = "http://whatsapp-service:3000"
    whatsapp_enabled: bool = True
    # iMessage via Photon Spectrum (imessage-service/). Off by default and
    # deliberately not self-starting: it is the only channel that routes your
    # conversations through a third-party hosted relay, so turning it on has to
    # be a decision. An empty allowlist blocks everyone — the free tier sends
    # from a shared number pool, so an open door is one stranger away.
    imessage_enabled: bool = False
    imessage_service_url: str = "http://imessage-service:3100"
    imessage_owner_handle: str = ""      # shares default_user's identity
    imessage_allowed_handles: str = ""   # comma-separated E.164 numbers / emails
    # auto = voice in, voice out (the WhatsApp contract) · always = speak every
    # reply · never = text only. Voice notes need ffmpeg in imessage-service to
    # transcode to the M4A that Messages accepts; without it this degrades to
    # text rather than failing the reply.
    imessage_voice_replies: str = "auto"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.modify "
        "https://www.googleapis.com/auth/calendar "
        "https://www.googleapis.com/auth/tasks"
    )
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_scopes: str = (
        "user-read-playback-state user-modify-playback-state "
        "user-read-currently-playing user-read-private streaming"
    )
    # Comma-separated allowed browser origins; "*" = any. Fine for local use —
    # set explicit origins (e.g. http://localhost:1420) before exposing the API
    # to a network. Auth is bearer-token, not cookies, so "*" isn't a credential
    # leak, but narrowing it is good hygiene.
    cors_allow_origins: str = "*"
    okf_dir: str = "okf"                 # OKF bundle: persona, style, routing
    # Fallback only — the live prompt is assembled from the OKF bundle above
    system_prompt: str = (
        "You are Wednesday, Wandile's personal AI — British, dry, darkly "
        "funny, effortlessly competent. Answer first, attitude second. One "
        "to three spoken-style sentences, no markdown, never read out URLs."
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()] or ["*"]

settings = Settings()