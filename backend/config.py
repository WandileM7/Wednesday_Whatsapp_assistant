from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    public_url: str = "http://localhost:8000"
    session_secret: str = "change-me-in-production"
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