import os
import logging
import tempfile
import requests
import json
import base64
from typing import Optional, Tuple
from pathlib import Path

# Try Google Cloud Speech (legacy fallback)
try:
    from google.cloud import speech, texttospeech
    from google.oauth2 import service_account
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_AVAILABLE = False
    speech = None
    texttospeech = None

# Try Bytez for AI-powered speech (primary)
try:
    from bytez import Bytez
    BYTEZ_AVAILABLE = True
except ImportError:
    BYTEZ_AVAILABLE = False
    Bytez = None

try:
    from handlers.google_auth import load_credentials
except ImportError:
    load_credentials = lambda: None

logger = logging.getLogger(__name__)

# Configuration - Best models for speech
BYTEZ_API_KEY = os.getenv("BYTEZ_API_KEY")
BYTEZ_TTS_MODEL = os.getenv("BYTEZ_TTS_MODEL", "suno/bark")  # Full bark for quality
BYTEZ_TTS_MODEL_FAST = os.getenv("BYTEZ_TTS_MODEL_FAST", "suno/bark-small")  # Fast alternative
BYTEZ_AUDIO_MODEL = os.getenv("BYTEZ_AUDIO_MODEL", "Qwen/Qwen2-Audio-7B-Instruct")  # Best STT

# Initialize Bytez client for speech
bytez_client = None
if BYTEZ_API_KEY and BYTEZ_AVAILABLE:
    try:
        bytez_client = Bytez(BYTEZ_API_KEY)
        logger.info(f"Bytez speech client ready - TTS: {BYTEZ_TTS_MODEL}, STT: {BYTEZ_AUDIO_MODEL}")
    except Exception as e:
        logger.warning(f"Bytez speech client unavailable: {e}")

# User voice preferences storage
VOICE_PREFS_FILE = Path("voice_preferences.json")

def load_voice_preferences() -> dict:
    """Load user voice preferences from file"""
    try:
        if VOICE_PREFS_FILE.exists():
            with open(VOICE_PREFS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading voice preferences: {e}")
        return {}

def save_voice_preferences(preferences: dict):
    """Save user voice preferences to file"""
    try:
        with open(VOICE_PREFS_FILE, 'w') as f:
            json.dump(preferences, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving voice preferences: {e}")

def get_user_voice_preference(phone: str) -> bool:
    """Get user's voice response preference (default: True)"""
    if not phone:
        return True
    
    preferences = load_voice_preferences()
    return preferences.get(phone, True)  # Default to enabled

def set_user_voice_preference(phone: str, enabled: bool) -> str:
    """Set user's voice response preference"""
    if not phone:
        return "❌ Unable to save preference - no phone number provided"
    
    preferences = load_voice_preferences()
    preferences[phone] = enabled
    save_voice_preferences(preferences)
    
    status = "enabled" if enabled else "disabled"
    return f"✅ Voice responses {status} for your number"

def toggle_user_voice_preference(phone: str) -> str:
    """Toggle user's voice response preference"""
    current = get_user_voice_preference(phone)
    new_setting = not current
    return set_user_voice_preference(phone, new_setting)

logger = logging.getLogger(__name__)

# Initialize Google Cloud clients
def get_speech_client():
    """Get authenticated Google Cloud Speech client with improved error handling"""
    try:
        # Try using existing Google credentials from the project
        creds = load_credentials()
        if creds and hasattr(creds, 'token'):
            # For OAuth2 credentials, check if we have the required scopes
            required_scopes = ['https://www.googleapis.com/auth/cloud-platform']
            if hasattr(creds, 'scopes'):
                has_required_scope = any(scope in (creds.scopes or []) for scope in required_scopes)
                if has_required_scope:
                    try:
                        speech_client = speech.SpeechClient(credentials=creds)
                        logger.info("Speech client initialized successfully with OAuth credentials")
                        return speech_client
                    except Exception as test_e:
                        logger.warning(f"Speech client OAuth initialization failed: {test_e}")
                else:
                    logger.warning("OAuth credentials don't include required cloud-platform scope")
        
        # Fallback to environment credentials
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                speech_client = speech.SpeechClient()
                logger.info("Speech client initialized with service account credentials")
                return speech_client
            except Exception as e:
                logger.warning(f"Service account credentials failed: {e}")
        
        logger.warning("Speech API not configured - voice recognition disabled")
        return None
        
    except Exception as e:
        logger.error(f"Could not initialize Speech client: {e}")
        return None

def get_tts_client():
    """Get authenticated Google Cloud Text-to-Speech client with improved error handling"""
    try:
        # Try using existing Google credentials from the project
        creds = load_credentials()
        if creds and hasattr(creds, 'token'):
            # For OAuth2 credentials, check if we have the required scopes
            required_scopes = ['https://www.googleapis.com/auth/cloud-platform']
            if hasattr(creds, 'scopes'):
                has_required_scope = any(scope in (creds.scopes or []) for scope in required_scopes)
                if has_required_scope:
                    try:
                        tts_client = texttospeech.TextToSpeechClient(credentials=creds)
                        logger.info("TTS client initialized successfully with OAuth credentials")
                        return tts_client
                    except Exception as test_e:
                        logger.warning(f"TTS client OAuth initialization failed: {test_e}")
                else:
                    logger.warning("OAuth credentials don't include required cloud-platform scope")
        
        # Fallback to environment credentials
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                tts_client = texttospeech.TextToSpeechClient()
                logger.info("TTS client initialized with service account credentials")
                return tts_client
            except Exception as e:
                logger.warning(f"Service account credentials failed: {e}")
        
        logger.warning("TTS API not configured - voice synthesis disabled")
        return None
        
    except Exception as e:
        logger.error(f"Could not initialize TTS client: {e}")
        return None

def download_voice_message(voice_url: str, session: str) -> Optional[str]:
    """Download voice message from WAHA and return local file path"""
    try:
        # Add session to the download URL if needed
        headers = {}
        if session:
            headers['X-Session'] = session
        
        # Increased timeout for production environments
        response = requests.get(voice_url, headers=headers, timeout=60)
        response.raise_for_status()
        
        # Determine file extension based on content type or URL
        content_type = response.headers.get('content-type', '').lower()
        if 'mp3' in content_type or voice_url.lower().endswith('.mp3'):
            suffix = '.mp3'
        elif 'ogg' in content_type or voice_url.lower().endswith('.ogg'):
            suffix = '.ogg'
        elif 'opus' in content_type:
            suffix = '.ogg'  # OGG Opus format
        else:
            suffix = '.ogg'  # Default fallback for WhatsApp voice messages
        
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(response.content)
            logger.info(f"Downloaded voice message: {temp_file.name}, size: {len(response.content)} bytes")
            return temp_file.name
            
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout downloading voice message from {voice_url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error downloading voice message from {voice_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading voice message: {e}")
        return None

def speech_to_text(audio_file_path: str, audio_url: str = None) -> Optional[str]:
    """
    Convert audio file to text using Bytez Qwen2-Audio (primary) or Google Speech-to-Text (fallback).
    
    Args:
        audio_file_path: Local path to audio file
        audio_url: Optional URL to audio (preferred for Bytez)
    
    Returns:
        Transcribed text or None
    """
    # Try Bytez Qwen2-Audio first (best quality audio understanding)
    if bytez_client:
        result = speech_to_text_bytez(audio_file_path, audio_url)
        if result:
            return result
        logger.warning("Bytez STT failed, trying Google Cloud fallback")
    
    # Fallback to Google Cloud Speech-to-Text
    return speech_to_text_google(audio_file_path)


def speech_to_text_bytez(audio_file_path: str, audio_url: str = None) -> Optional[str]:
    """
    Convert audio to text using Bytez Qwen2-Audio-7B-Instruct.
    This model provides audio-text-to-text capabilities for contextual understanding.
    
    Args:
        audio_file_path: Local path to audio file
        audio_url: Optional URL to audio (preferred)
    
    Returns:
        Transcribed text or None
    """
    if not bytez_client:
        return None
    
    try:
        model = bytez_client.model(BYTEZ_AUDIO_MODEL)
        
        # Prefer URL if available, otherwise encode file as base64
        if audio_url:
            audio_input = {"type": "audio", "url": audio_url}
        else:
            # Read and encode audio file
            with open(audio_file_path, 'rb') as f:
                audio_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Determine MIME type
            if audio_file_path.lower().endswith('.mp3'):
                mime_type = "audio/mpeg"
            elif audio_file_path.lower().endswith('.ogg'):
                mime_type = "audio/ogg"
            elif audio_file_path.lower().endswith('.wav'):
                mime_type = "audio/wav"
            else:
                mime_type = "audio/ogg"  # Default for WhatsApp
            
            audio_input = {
                "type": "audio",
                "data": audio_data,
                "mime_type": mime_type
            }
        
        # Build multimodal input for audio-text-to-text
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe this audio message accurately. Capture exactly what is being said."
                    },
                    audio_input
                ]
            }
        ]
        
        result = model.run(input_content)
        
        if result.error:
            logger.error(f"Bytez audio transcription failed: {result.error}")
            return None
        
        # Extract transcription
        transcription = result.output
        if isinstance(transcription, dict):
            transcription = transcription.get("text", str(transcription))
        
        logger.info(f"Bytez Qwen2-Audio transcription: {transcription}")
        return str(transcription).strip()
        
    except Exception as e:
        logger.error(f"Bytez STT error: {e}")
        return None


def speech_to_text_google(audio_file_path: str) -> Optional[str]:
    """Convert audio file to text using Google Speech-to-Text (fallback)"""
    client = get_speech_client()
    if not client:
        logger.error("Google Speech client not available")
        return None
    
    try:
        # Read audio file
        with open(audio_file_path, 'rb') as audio_file:
            content = audio_file.read()
        
        # Determine encoding based on file extension
        if audio_file_path.lower().endswith('.mp3'):
            encoding = speech.RecognitionConfig.AudioEncoding.MP3
        elif audio_file_path.lower().endswith('.ogg'):
            encoding = speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        else:
            # Default to OGG_OPUS for WhatsApp voice messages
            encoding = speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        
        # Configure recognition
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=16000,  # WhatsApp voice messages are typically 16kHz
            language_code="en-US",
            alternative_language_codes=["en-GB", "es-ES", "fr-FR"],  # Multi-language support
            enable_automatic_punctuation=True,
            enable_word_time_offsets=False,
        )
        
        # Perform speech recognition
        response = client.recognize(config=config, audio=audio)
        
        # Extract transcription
        if response.results:
            transcript = response.results[0].alternatives[0].transcript
            logger.info(f"Speech-to-text transcription: {transcript}")
            return transcript.strip()
        else:
            logger.warning("No speech recognized in audio")
            return None
            
    except Exception as e:
        logger.error(f"Error in speech-to-text conversion: {e}")
        return None
    finally:
        # Clean up temporary file
        try:
            os.unlink(audio_file_path)
        except:
            pass

def text_to_speech(text: str, language_code: str = "en-US") -> Optional[str]:
    """Convert text to speech using Bytez (primary) or Google Cloud TTS (fallback)"""
    # Try Bytez first (it has amazing models like suno/bark)
    if bytez_client:
        result = text_to_speech_bytez(text)
        if result:
            return result
        logger.warning("Bytez TTS failed, trying Google Cloud fallback")
    
    # Fallback to Google Cloud TTS
    return text_to_speech_google(text, language_code)


def text_to_speech_bytez(text: str) -> Optional[str]:
    """Convert text to speech using Bytez TTS models (suno/bark-small)"""
    if not bytez_client:
        return None
    
    try:
        model = bytez_client.model(BYTEZ_TTS_MODEL)
        result = model.run(text)
        
        if result.error:
            logger.error(f"Bytez TTS error: {result.error}")
            return None
        
        # Bytez returns a URL to the audio file
        audio_url = result.output
        
        if not audio_url:
            logger.error("Bytez TTS returned empty output")
            return None
        
        # If it's a URL, download and save to temp file
        if isinstance(audio_url, str) and audio_url.startswith('http'):
            try:
                response = requests.get(audio_url, timeout=60)
                response.raise_for_status()
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                    temp_file.write(response.content)
                    logger.info(f"Bytez TTS audio saved: {temp_file.name}")
                    return temp_file.name
            except Exception as e:
                logger.error(f"Error downloading Bytez audio: {e}")
                return None
        else:
            # If it's raw audio data
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                if isinstance(audio_url, bytes):
                    temp_file.write(audio_url)
                else:
                    temp_file.write(str(audio_url).encode())
                logger.info(f"Bytez TTS audio saved: {temp_file.name}")
                return temp_file.name
        
    except Exception as e:
        logger.error(f"Bytez TTS error: {e}")
        return None


def text_to_speech_google(text: str, language_code: str = "en-US") -> Optional[str]:
    """Fallback to Google Cloud text-to-speech synthesis"""
    client = get_tts_client()
    if not client:
        return None
    
    # Prepare text for TTS by removing emojis and problematic characters
    try:
        from helpers.text_utils import prepare_text_for_tts
        processed_text = prepare_text_for_tts(text)
        logger.debug(f"TTS text processing: '{text[:50]}...' -> '{processed_text[:50]}...'")
    except ImportError:
        logger.warning("Text utils not available for TTS, using original text")
        processed_text = text
    except Exception as e:
        logger.warning(f"Error processing text for TTS: {e}, using original text")
        processed_text = text
    
    return text_to_speech_fallback(processed_text, language_code)


def text_to_speech_fallback(text: str, language_code: str = "en-US") -> Optional[str]:
    """Fallback to regular text-to-speech synthesis with Chirp3-HD voices (Google Cloud)"""
    client = get_tts_client()
    if not client:
        return None
    
    if not GOOGLE_CLOUD_AVAILABLE:
        logger.warning("Google Cloud TTS not available")
        return None
    
    # Prepare text for TTS by removing emojis and problematic characters
    try:
        from helpers.text_utils import prepare_text_for_tts
        processed_text = prepare_text_for_tts(text)
        logger.debug(f"TTS fallback text processing: '{text[:50]}...' -> '{processed_text[:50]}...'")
    except ImportError:
        logger.warning("Text utils not available for fallback TTS, using original text")
        processed_text = text
    except Exception as e:
        logger.warning(f"Error processing text for fallback TTS: {e}, using original text")
        processed_text = text
    
    try:
        # Configure regular synthesis with Chirp3-HD Sulafat voice
        synthesis_input = texttospeech.SynthesisInput(text=processed_text)
        
        # Try Chirp3-HD Sulafat first, then fallback to other Chirp3-HD voices
        chirp3_voices = [
            "en-US-Chirp3-HD-Sulafat",  # Primary choice - Sulafat
            "en-US-Chirp3-HD-Aliya",    # Fallback 1 - Aliya
            "en-US-Chirp3-HD-Arya",     # Fallback 2 - Arya
            "en-US-Chirp3-HD-Clara",    # Fallback 3 - Clara
        ]
        
        for voice_name in chirp3_voices:
            try:
                voice = texttospeech.VoiceSelectionParams(
                    name=voice_name,
                    language_code=language_code,
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
                    speaking_rate=1.0,
                    pitch=0.0,
                    volume_gain_db=0.0
                )
                
                # Perform synthesis
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
                
                # Save audio to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
                    temp_file.write(response.audio_content)
                    logger.info(f"Generated fallback speech audio with {voice_name}: {temp_file.name}")
                    return temp_file.name
                    
            except Exception as voice_e:
                logger.warning(f"Voice {voice_name} failed: {voice_e}")
                continue
        
        # If all Chirp3-HD voices fail, try standard Neural2 voices
        logger.info("All Chirp3-HD voices failed, trying Neural2 fallback")
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name="en-US-Neural2-F",  # Neural2 Female voice as final fallback
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS
        )
        
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            temp_file.write(response.audio_content)
            logger.info(f"Generated Neural2 fallback speech audio: {temp_file.name}")
            return temp_file.name
            
    except Exception as e:
        logger.error(f"Error in fallback text-to-speech conversion: {e}")
        return None

def should_respond_with_voice(user_sent_voice: bool, text_length: int = 0, phone: str = "") -> bool:
    """Determine if response should be voice based on context and user preferences"""
    # Check if voice responses are globally enabled
    global_voice_enabled = os.getenv("ENABLE_VOICE_RESPONSES", "true").lower() == "true"
    if not global_voice_enabled:
        return False
    
    # Check user-specific voice preference (default is True now)
    user_voice_enabled = get_user_voice_preference(phone)
    if not user_voice_enabled:
        return False
    
    # If user sent voice, always respond with voice (respecting user preference)
    if user_sent_voice:
        return True
    
    # If user has voice enabled, respond with voice regardless of length
    # (user requested this behavior change)
    return True

def cleanup_temp_file(file_path: str):
    """Clean up temporary audio file"""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logger.warning(f"Could not clean up temp file {file_path}: {e}")