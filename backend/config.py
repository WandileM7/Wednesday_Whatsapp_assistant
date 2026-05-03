from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    public_url: str = "http://localhost:8000"
    session_secret: str = "change-me-in-production"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    openai_api_key: str = ""
    tts_voice: str = "nova"
    tts_model: str = "tts-1"
    stt_model: str = "whisper-1"
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
    system_prompt: str = (
        "You are Wednesday, a personal assistant for Wandile. "
        "Be concise, warm, direct. Reply in 1-3 sentences unless detail is "
        "requested. Use tools when they help. Don't ask for confirmation on "
        "read-only tools; do confirm before destructive actions."
    )

settings = Settings()