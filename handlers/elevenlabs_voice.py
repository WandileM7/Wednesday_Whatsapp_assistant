"""
ElevenLabs Voice Synthesis Module
=================================
Premium AI voice synthesis for JARVIS-quality speech output.
Supports voice cloning, multiple voices, and emotional styles.
"""

import os
import logging
import tempfile
import requests
import json
import base64
from typing import Optional, Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# JARVIS-style voice presets (ElevenLabs voice IDs)
# These are some popular voices - user can customize
VOICE_PRESETS = {
    'jarvis': os.getenv("ELEVENLABS_JARVIS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"),  # Adam - deep, authoritative
    'friday': os.getenv("ELEVENLABS_FRIDAY_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),  # Bella - female assistant
    'british_butler': os.getenv("ELEVENLABS_BUTLER_VOICE_ID", "onwK4e9ZLuTAKqWW03F9"),  # Daniel - British
    'warm': os.getenv("ELEVENLABS_WARM_VOICE_ID", "jsCqWAovK2LkecY7zXl4"),  # Freya - warm
    'narrator': os.getenv("ELEVENLABS_NARRATOR_VOICE_ID", "N2lVS1w4EtoT3dr4eOWO"),  # Callum - narrator
    'default': os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "pNInz6obpgDQGcFmaJgB"),  # Default to JARVIS
}

# Voice model settings
VOICE_MODELS = {
    'turbo': 'eleven_turbo_v2_5',  # Fastest, good quality
    'multilingual': 'eleven_multilingual_v2',  # Best for non-English
    'english': 'eleven_monolingual_v1',  # English only, highest quality
    'flash': 'eleven_flash_v2_5',  # Ultra low latency
}

# Voice styles for different contexts
VOICE_STYLES = {
    'default': {'stability': 0.5, 'similarity_boost': 0.75, 'style': 0.0, 'use_speaker_boost': True},
    'expressive': {'stability': 0.3, 'similarity_boost': 0.8, 'style': 0.5, 'use_speaker_boost': True},
    'calm': {'stability': 0.8, 'similarity_boost': 0.7, 'style': 0.0, 'use_speaker_boost': True},
    'urgent': {'stability': 0.4, 'similarity_boost': 0.85, 'style': 0.3, 'use_speaker_boost': True},
    'whisper': {'stability': 0.9, 'similarity_boost': 0.6, 'style': 0.0, 'use_speaker_boost': False},
}


class ElevenLabsVoice:
    """ElevenLabs voice synthesis with JARVIS personality"""
    
    def __init__(self):
        self.api_key = ELEVENLABS_API_KEY
        self.enabled = bool(self.api_key)
        self.current_voice = VOICE_PRESETS.get('jarvis', VOICE_PRESETS['default'])
        self.current_model = VOICE_MODELS['turbo']
        self.current_style = VOICE_STYLES['default']
        self.available_voices: List[Dict] = []
        self.cloned_voices: Dict[str, str] = {}
        
        if self.enabled:
            logger.info("🎤 ElevenLabs voice synthesis initialized")
            self._load_available_voices()
        else:
            logger.warning("ElevenLabs API key not configured")
    
    def _headers(self) -> Dict[str, str]:
        """Get API headers"""
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _load_available_voices(self):
        """Load available voices from ElevenLabs"""
        try:
            response = requests.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers=self._headers(),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.available_voices = data.get('voices', [])
                logger.info(f"Loaded {len(self.available_voices)} ElevenLabs voices")
            else:
                logger.warning(f"Could not load voices: {response.status_code}")
        except Exception as e:
            logger.error(f"Error loading ElevenLabs voices: {e}")
    
    def text_to_speech(
        self,
        text: str,
        voice: str = None,
        model: str = None,
        style: str = None,
        output_format: str = "mp3_44100_128"
    ) -> Optional[str]:
        """
        Convert text to speech using ElevenLabs.
        
        Args:
            text: Text to synthesize
            voice: Voice preset name or voice ID
            model: Model to use (turbo, multilingual, english, flash)
            style: Style preset (default, expressive, calm, urgent, whisper)
            output_format: Audio format (mp3_44100_128, pcm_16000, etc.)
            
        Returns:
            Path to generated audio file or None
        """
        if not self.enabled:
            logger.warning("ElevenLabs not configured")
            return None
        
        try:
            # Resolve voice ID
            voice_id = self._resolve_voice(voice)
            
            # Get model
            model_id = VOICE_MODELS.get(model, self.current_model)
            
            # Get style settings
            voice_settings = VOICE_STYLES.get(style, self.current_style).copy()
            
            # Build request
            payload = {
                "text": text,
                "model_id": model_id,
                "voice_settings": voice_settings
            }
            
            # Make request
            response = requests.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
                headers=self._headers(),
                json=payload,
                params={"output_format": output_format},
                timeout=30
            )
            
            if response.status_code == 200:
                # Save audio to temp file
                suffix = '.mp3' if 'mp3' in output_format else '.wav'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(response.content)
                    logger.info(f"ElevenLabs TTS generated: {f.name} ({len(response.content)} bytes)")
                    return f.name
            else:
                logger.error(f"ElevenLabs TTS failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"ElevenLabs TTS error: {e}")
            return None
    
    def text_to_speech_streaming(
        self,
        text: str,
        voice: str = None,
        model: str = "flash"
    ):
        """
        Stream text to speech for low latency.
        
        Yields audio chunks as they're generated.
        """
        if not self.enabled:
            return
        
        try:
            voice_id = self._resolve_voice(voice)
            model_id = VOICE_MODELS.get(model, VOICE_MODELS['flash'])
            
            payload = {
                "text": text,
                "model_id": model_id,
                "voice_settings": self.current_style
            }
            
            response = requests.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}/stream",
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=60
            )
            
            if response.status_code == 200:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk
            else:
                logger.error(f"ElevenLabs streaming failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"ElevenLabs streaming error: {e}")
    
    def clone_voice(
        self,
        name: str,
        audio_files: List[str],
        description: str = "Cloned voice for JARVIS"
    ) -> Optional[str]:
        """
        Clone a voice from audio samples.
        
        Args:
            name: Name for the cloned voice
            audio_files: List of paths to audio samples
            description: Voice description
            
        Returns:
            Voice ID of cloned voice or None
        """
        if not self.enabled:
            return None
        
        try:
            files = []
            for audio_path in audio_files:
                with open(audio_path, 'rb') as f:
                    files.append(('files', (Path(audio_path).name, f.read(), 'audio/mpeg')))
            
            response = requests.post(
                f"{ELEVENLABS_BASE_URL}/voices/add",
                headers={"xi-api-key": self.api_key},
                data={"name": name, "description": description},
                files=files,
                timeout=60
            )
            
            if response.status_code == 200:
                voice_data = response.json()
                voice_id = voice_data.get('voice_id')
                self.cloned_voices[name] = voice_id
                logger.info(f"Voice cloned successfully: {name} -> {voice_id}")
                return voice_id
            else:
                logger.error(f"Voice cloning failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Voice cloning error: {e}")
            return None
    
    def _resolve_voice(self, voice: str = None) -> str:
        """Resolve voice name/preset to voice ID"""
        if voice is None:
            return self.current_voice
        
        # Check presets
        if voice.lower() in VOICE_PRESETS:
            return VOICE_PRESETS[voice.lower()]
        
        # Check cloned voices
        if voice in self.cloned_voices:
            return self.cloned_voices[voice]
        
        # Assume it's a voice ID
        return voice
    
    def set_voice(self, voice: str):
        """Set current voice"""
        self.current_voice = self._resolve_voice(voice)
        logger.info(f"Voice set to: {self.current_voice}")
    
    def set_style(self, style: str):
        """Set voice style"""
        if style in VOICE_STYLES:
            self.current_style = VOICE_STYLES[style]
            logger.info(f"Voice style set to: {style}")
    
    def get_voices_list(self) -> List[Dict[str, str]]:
        """Get list of available voices"""
        voices = []
        
        # Add presets
        for name, voice_id in VOICE_PRESETS.items():
            voices.append({'name': f"preset:{name}", 'id': voice_id, 'type': 'preset'})
        
        # Add available voices
        for voice in self.available_voices:
            voices.append({
                'name': voice.get('name'),
                'id': voice.get('voice_id'),
                'type': 'library',
                'category': voice.get('category')
            })
        
        # Add cloned voices
        for name, voice_id in self.cloned_voices.items():
            voices.append({'name': name, 'id': voice_id, 'type': 'cloned'})
        
        return voices
    
    def get_usage(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        if not self.enabled:
            return {'enabled': False}
        
        try:
            response = requests.get(
                f"{ELEVENLABS_BASE_URL}/user/subscription",
                headers=self._headers(),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'enabled': True,
                    'character_count': data.get('character_count', 0),
                    'character_limit': data.get('character_limit', 0),
                    'tier': data.get('tier', 'unknown'),
                    'can_extend': data.get('can_extend_character_limit', False)
                }
        except Exception as e:
            logger.error(f"Error getting ElevenLabs usage: {e}")
        
        return {'enabled': True, 'error': 'Could not fetch usage'}
    
    def get_usage_status(self) -> Dict[str, Any]:
        """Alias for get_usage() - used by MCP server"""
        return self.get_usage()


# Global instance
elevenlabs_voice = ElevenLabsVoice()


def jarvis_speak(
    text: str,
    style: str = "default",
    urgent: bool = False,
    whisper: bool = False
) -> Optional[str]:
    """
    JARVIS speech synthesis with context-aware voice.
    
    Args:
        text: Text for JARVIS to speak
        style: Voice style (default, expressive, calm)
        urgent: If True, use urgent style
        whisper: If True, use whisper style
        
    Returns:
        Path to audio file or None
    """
    if urgent:
        style = "urgent"
    elif whisper:
        style = "whisper"
    
    return elevenlabs_voice.text_to_speech(
        text=text,
        voice="jarvis",
        model="turbo",
        style=style
    )


def friday_speak(text: str) -> Optional[str]:
    """F.R.I.D.A.Y. voice (female assistant)"""
    return elevenlabs_voice.text_to_speech(
        text=text,
        voice="friday",
        model="turbo",
        style="default"
    )
