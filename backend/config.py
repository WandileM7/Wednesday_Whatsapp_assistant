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
    # Model for background utility calls (summaries, fact extraction);
    # empty = use ollama_model
    ollama_model_utility: str = ""
    # Tools that pause and ask before running (comma-separated)
    approval_required_tools: str = "gmail_send,calendar_create_event,run_code"
    # Email channel: polls IMAP, replies via SMTP. Off unless address+password set.
    email_address: str = ""
    email_password: str = ""          # app password, not your real one
    email_imap_host: str = "imap.gmail.com"
    email_smtp_host: str = "smtp.gmail.com"
    email_poll_seconds: int = 60
    # Only these senders are answered; the first one maps to default_user
    email_allowed_senders: str = ""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    whisper_model: str = "base"          # faster-whisper size: tiny/base/small/medium
    piper_voice: str = "en_GB-alba-medium"
    # Fish Audio hosted TTS — used when a key is set, otherwise Piper (local, free)
    fish_api_key: str = ""
    fish_voice_id: str = "bf6b1cbc1a394928adfb6927726d8b17"
    fish_tts_model: str = "s2.1-pro-free"
    fish_speed: float = 1.0
    voice_cache_dir: str = "~/.cache/wednesday/voices"
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
    cors_origins: list[str] = ["*"]
    okf_dir: str = "okf"                 # OKF bundle: persona, style, routing
    # Fallback only — the live prompt is assembled from the OKF bundle above
    system_prompt: str = (
        "You are Wednesday, Wandile's personal AI — British, dry, darkly "
        "funny, effortlessly competent. Answer first, attitude second. One "
        "to three spoken-style sentences, no markdown, never read out URLs."
    )

settings = Settings()