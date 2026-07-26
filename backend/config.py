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
    # Proactive check-ins every N minutes; 0 = off (default until trusted)
    heartbeat_minutes: int = 0
    # No proactive pings between these hours (24h clock, "start-end", wraps midnight)
    heartbeat_quiet: str = "22-07"
    # Hard cap on proactive pings per calendar day
    heartbeat_daily_cap: int = 8
    # Sandboxed run_code tool (docker, no network); off until explicitly enabled
    enable_code_execution: bool = False
    # Model for background utility calls (summaries, fact extraction). Set this
    # to a *different* (smaller) model than ollama_model: sharing one model
    # makes each background call evict the interactive prompt's KV cache, so
    # the next reply re-evaluates the whole ~2.2k-token prefix from scratch.
    # A distinct utility model runs on its own Ollama runner and avoids that.
    # Empty = reuse ollama_model (simpler, but pays the re-eval cost).
    ollama_model_utility: str = ""
    # Tools that pause and ask before running (comma-separated)
    approval_required_tools: str = ("gmail_send,calendar_create_event,"
                                    "calendar_update_event,calendar_delete_event,run_code")
    # Fallback for get_weather when the model doesn't pass a location — the
    # user's home city, so "what's the weather?" answers without asking. Set to
    # "" to force Wednesday to ask instead.
    default_location: str = "Cape Town"
    # Ambient listening: when hands-free is on and this is true, Wednesday only
    # answers utterances addressed to her by name (see backend/wakeword.py).
    wake_word: str = "wednesday"
    wake_word_required: bool = False
    # Vision model for the `look` tool. Empty = the hosted chat model when one
    # is configured (most are multimodal), else local llava:7b — which is
    # correct but takes minutes per image on CPU.
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
    voice_cache_dir: str = "~/.cache/wednesday/voices"
    # Web search: a hosted provider is used when its key is set, otherwise the
    # free DuckDuckGo scrape (always the fallback). Tavily is LLM-tuned and can
    # return page content directly; Brave is a general web index.
    tavily_api_key: str = ""
    brave_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./wednesday.db"
    waha_url: str = "http://whatsapp-service:3000"
    whatsapp_enabled: bool = True
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