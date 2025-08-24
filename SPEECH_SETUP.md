# Speech Configuration

The WhatsApp assistant now supports Text-to-Speech (TTS) and Speech-to-Text (STT) functionality with improved MP3 support for better compatibility.

## Required Environment Variables

Add these to your `.env` file:

```bash
# Voice Response Settings
ENABLE_VOICE_RESPONSES=true          # Enable/disable voice responses (default: true)
MAX_VOICE_RESPONSE_LENGTH=200        # Max text length for voice responses (default: 200)

# Google Cloud Speech API (if not using existing Google auth)
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

## Google Cloud Setup

### Option 1: Use Existing Google Auth (Recommended)
If you already have Google services (Gmail, Calendar) configured, the speech features will use the same credentials automatically.

### Option 2: Separate Google Cloud Project
1. Create a Google Cloud project
2. Enable Speech-to-Text and Text-to-Speech APIs
3. Create a service account and download the JSON key
4. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable

## Features

### Speech-to-Text (STT)
- Automatically detects voice messages from WhatsApp
- Converts voice to text using Google Speech-to-Text
- Supports multiple languages (English, Spanish, French)
- Handles both OGG and MP3 audio formats
- Processes transcribed text normally through Gemini

### Text-to-Speech (TTS)
- Converts text responses to voice messages in MP3 format for better WhatsApp compatibility
- Responds with voice when:
  - User sent a voice message, OR
  - Response text is short (under MAX_VOICE_RESPONSE_LENGTH)
- Multiple fallback options:
  1. First tries to send as WhatsApp voice message
  2. If voice message fails, tries to send as MP3 file attachment
  3. If both fail, falls back to text message
- Uses pleasant female voice in multiple languages

## WhatsApp Integration Improvements

The system now provides better compatibility with WhatsApp:
- **MP3 Format**: Generated audio files use MP3 format instead of OGG for better playability
- **Fallback Options**: If voice messages don't work, the system will try to send MP3 files as attachments
- **Better Logging**: Enhanced logging to help debug voice message issues

## WAHA Integration

The system expects WAHA to support:
- `sendVoice` endpoint for sending voice messages
- `sendMedia` endpoint for sending MP3 file attachments (fallback)
- Voice message webhooks with `type: "voice"` and media URL
- File upload capability for voice messages

## Testing

Run the speech tests:
```bash
curl http://localhost:5000/test-speech
```

Note: TTS tests will fail without proper Google Cloud credentials, but the voice logic tests should pass.