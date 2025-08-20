import os
import logging
import tempfile
import requests
from typing import Optional, Tuple
from google.cloud import speech, texttospeech
from google.oauth2 import service_account
from handlers.google_auth import load_credentials

logger = logging.getLogger(__name__)

# Initialize Google Cloud clients
def get_speech_client():
    """Get authenticated Google Cloud Speech client"""
    try:
        # Try using existing Google credentials from the project
        creds = load_credentials()
        if creds:
            speech_client = speech.SpeechClient(credentials=creds)
            return speech_client
    except Exception as e:
        logger.warning(f"Could not use existing Google credentials for Speech API: {e}")
    
    # Fallback to environment credentials
    try:
        speech_client = speech.SpeechClient()
        return speech_client
    except Exception as e:
        logger.error(f"Could not initialize Speech client: {e}")
        return None

def get_tts_client():
    """Get authenticated Google Cloud Text-to-Speech client"""
    try:
        # Try using existing Google credentials from the project
        creds = load_credentials()
        if creds:
            tts_client = texttospeech.TextToSpeechClient(credentials=creds)
            return tts_client
    except Exception as e:
        logger.warning(f"Could not use existing Google credentials for TTS API: {e}")
    
    # Fallback to environment credentials
    try:
        tts_client = texttospeech.TextToSpeechClient()
        return tts_client
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
        
        response = requests.get(voice_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            temp_file.write(response.content)
            return temp_file.name
            
    except Exception as e:
        logger.error(f"Error downloading voice message: {e}")
        return None

def speech_to_text(audio_file_path: str) -> Optional[str]:
    """Convert audio file to text using Google Speech-to-Text"""
    client = get_speech_client()
    if not client:
        logger.error("Speech client not available")
        return None
    
    try:
        # Read audio file
        with open(audio_file_path, 'rb') as audio_file:
            content = audio_file.read()
        
        # Configure recognition
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
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
    """Convert text to speech and return path to audio file"""
    client = get_tts_client()
    if not client:
        logger.error("TTS client not available")
        return None
    
    try:
        # Set up the text input
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Configure voice parameters
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            name=f"{language_code}-Standard-C"  # Use a pleasant female voice
        )
        
        # Configure audio output
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
            speaking_rate=1.0,
            pitch=0.0,
            volume_gain_db=0.0
        )
        
        # Perform text-to-speech
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        # Save audio to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            temp_file.write(response.audio_content)
            logger.info(f"Generated speech audio file: {temp_file.name}")
            return temp_file.name
            
    except Exception as e:
        logger.error(f"Error in text-to-speech conversion: {e}")
        return None

def should_respond_with_voice(user_sent_voice: bool, text_length: int = 0) -> bool:
    """Determine if response should be voice based on context"""
    # Respond with voice if:
    # 1. User sent a voice message, OR
    # 2. Response is short enough for voice (under 200 characters)
    # 3. Voice responses are enabled via environment variable
    
    voice_enabled = os.getenv("ENABLE_VOICE_RESPONSES", "true").lower() == "true"
    if not voice_enabled:
        return False
    
    if user_sent_voice:
        return True
    
    # For text messages, only use voice for short responses
    max_voice_length = int(os.getenv("MAX_VOICE_RESPONSE_LENGTH", "200"))
    return text_length <= max_voice_length

def cleanup_temp_file(file_path: str):
    """Clean up temporary audio file"""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logger.warning(f"Could not clean up temp file {file_path}: {e}")