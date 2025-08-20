# Wednesday WhatsApp Assistant

Wednesday WhatsApp Assistant is a Python Flask application that serves as an AI-powered WhatsApp bot. It integrates with Google Services (Gmail, Calendar, Gemini AI), Spotify, and uses ChromaDB for conversation storage. The application is containerized and deployed via Render cloud platform.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Bootstrap and Run the Application
- Install Python dependencies:
  - `pip3 install -r requirements.txt` -- takes 3 seconds NEVER CANCEL. Set timeout to 30+ seconds.
- Start the Flask application:
  - `python3 main.py` -- starts in 1-2 seconds. Runs on port 5000.
- The application starts successfully even without API keys (shows warnings but functions for testing).

### Environment Setup
- Create a `.env` file with these minimum variables for testing:
  ```bash
  # Minimum required for startup
  GEMINI_API_KEY=test_key_123
  SPOTIFY_CLIENT_ID=test_spotify_id
  SPOTIFY_SECRET=test_spotify_secret
  SPOTIFY_REDIRECT_URI=http://localhost:5000/spotify-callback
  PERSONALITY_PROMPT=You are a helpful assistant named Wednesday.
  FLASK_DEBUG=false
  USE_MEMORY_DB=true
  WAHA_URL=http://localhost:3000/api/sendText
  ```
- For production, real API keys are required for full functionality.

### Docker and Containerization
- Build the Docker image:
  - `docker build -t wednesday-assistant .` -- NEVER CANCEL. Set timeout to 30+ minutes.
  - NOTE: Docker build may fail due to SSL certificate issues in some environments. This is environment-specific and not a code issue.
- Run with docker-compose:
  - `docker compose up` -- starts both WhatsApp gateway (WAHA) and assistant services.
  - WAHA service runs on port 3000, assistant on port 5000.

### Testing and Validation
- NO automated test suite exists. Use manual validation endpoints instead.
- Health check: `curl http://localhost:5000/health`
- Services overview: `curl http://localhost:5000/services`
- Google services test: `curl http://localhost:5000/test-google-services`
- Webhook simulation: `curl http://localhost:5000/test-webhook-auth`

## Validation

### Manual Validation Requirements
ALWAYS perform these validation steps after making changes:

1. **Basic Application Startup**
   - Run `python3 main.py` and confirm it starts without errors
   - Test health endpoint: `curl http://localhost:5000/health`
   - Verify response shows `"status": "healthy"`

2. **Service Integration Tests**
   - Access setup page: `curl http://localhost:5000/quick-setup`
   - Test services overview: `curl http://localhost:5000/services`
   - Verify all service statuses are reported correctly

3. **API Integration Validation**
   - Test Google services: `curl http://localhost:5000/test-google-services`
   - Test webhook functionality: `curl http://localhost:5000/test-webhook-auth`
   - Test Spotify integration (if credentials available): `curl http://localhost:5000/test-spotify`

4. **Web Interface Verification**
   - Access main setup page: http://localhost:5000/quick-setup
   - Verify all links and buttons render correctly
   - Test Google authentication flow: http://localhost:5000/google-login

### Build and Deployment Testing
- ALWAYS test Docker build after changes affecting dependencies or configuration
- For Render deployment, ensure render.yaml configuration remains valid
- Test environment variable handling with missing/invalid keys

## Common Tasks

### Repository Structure
```
/home/runner/work/Wednesday_Whatsapp_assistant/Wednesday_Whatsapp_assistant/
├── main.py                    # Main Flask application entry point
├── config.py                  # Environment variable configuration
├── chromedb.py               # ChromaDB conversation storage
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container build instructions
├── docker-compose.yaml      # Multi-service setup with WAHA
├── render.yaml             # Cloud deployment configuration
├── .env                    # Environment variables (create for local dev)
├── .gitignore             # Excludes credentials, cache files
└── handlers/              # Feature-specific modules
    ├── gemini.py         # Google Gemini AI integration
    ├── gmail.py          # Gmail API functionality
    ├── calendar.py       # Google Calendar integration
    ├── spotify.py        # Spotify playback control
    ├── google_auth.py    # Google OAuth handling
    └── spotify_client.py # Spotify authentication
```

### Key Application Endpoints
- `/health` - System health and status
- `/services` - Service configuration overview
- `/quick-setup` - Interactive setup guide
- `/webhook` - WhatsApp message webhook
- `/google-login` - Google OAuth flow
- `/login` - Spotify authentication
- `/test-*` - Various testing endpoints

### Frequent Code Changes
- When modifying Google API integration, always test with `/test-google-services`
- When changing Spotify functionality, verify with `/test-spotify` 
- After updating Gemini/AI logic in `handlers/gemini.py`, test conversation flow
- When modifying authentication, test both session and webhook contexts

### Environment Variables Reference
```bash
# Core API Keys (required for full functionality)
GEMINI_API_KEY=your_gemini_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_SECRET=your_spotify_secret
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json

# Runtime Configuration
FLASK_DEBUG=false
USE_MEMORY_DB=true
WAHA_URL=http://localhost:3000/api/sendText
SPOTIFY_REDIRECT_URI=http://localhost:5000/spotify-callback
PERSONALITY_PROMPT=You are a helpful assistant named Wednesday.

# Production Authentication (after OAuth setup)
SPOTIFY_REFRESH_TOKEN=your_spotify_refresh_token
GOOGLE_REFRESH_TOKEN=your_google_refresh_token
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

### Known Issues and Workarounds
- ChromaDB import warning appears but doesn't affect functionality
- Docker build may fail with SSL certificate errors (environment-specific)
- Application requires manual OAuth setup for Google and Spotify services
- No automated linting or testing - use manual validation endpoints
- Missing `query_conversation_history` function in chromedb.py (has fallback handling)

### Time Expectations
- Dependency installation: 3 seconds (cached), 60+ seconds (fresh install)
- Application startup: 1-2 seconds
- Docker build: 15-30 minutes (environment dependent) -- NEVER CANCEL
- Manual validation: 2-3 minutes for complete test suite

### Deployment
- Local development: `python3 main.py`
- Docker: `docker compose up`
- Production: Deployed via Render using render.yaml configuration
- Requires manual setup of OAuth credentials for production use