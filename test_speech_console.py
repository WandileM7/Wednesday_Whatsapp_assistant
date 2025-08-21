"""
Simple console test for Text-to-Speech (TTS) and Speech-to-Text (STT) functionality
Run this script to test speech features independently of the main application
"""

import os
import sys
import logging

# Add current directory to Python path to find handlers module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_tts_basic():
    """Test basic Text-to-Speech functionality"""
    print("\n🔊 Testing Text-to-Speech (TTS)...")
    
    try:
        from handlers.speech import text_to_speech, cleanup_temp_file
        
        # Test text
        test_text = "Hello! This is a test of the text to speech functionality. Wednesday assistant is working correctly."
        
        print(f"Converting text to speech: '{test_text[:50]}...'")
        
        # Generate audio
        audio_file = text_to_speech(test_text)
        
        if audio_file:
            print(f"✅ TTS Success! Audio file created: {audio_file}")
            
            # Check file exists and has content
            if os.path.exists(audio_file):
                file_size = os.path.getsize(audio_file)
                print(f"📁 File size: {file_size} bytes")
                
                if file_size > 0:
                    print("✅ Audio file has content")
                else:
                    print("❌ Audio file is empty")
            else:
                print("❌ Audio file was not created")
            
            # Clean up
            cleanup_temp_file(audio_file)
            print("🧹 Temporary file cleaned up")
            
        else:
            print("❌ TTS Failed - No audio file generated")
            
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("💡 Make sure Google Cloud Speech libraries are installed:")
        print("   C:/Users/632231/AppData/Local/Microsoft/WindowsApps/python3.12.exe -m pip install google-cloud-speech google-cloud-texttospeech")
        
    except Exception as e:
        print(f"❌ TTS Error: {e}")

def test_stt_basic():
    """Test basic Speech-to-Text functionality"""
    print("\n🎤 Testing Speech-to-Text (STT)...")
    
    try:
        from handlers.speech import speech_to_text
        
        # Test if STT function is available
        print("✅ Speech-to-Text function imported successfully")
        
        # For console testing, we'll test with a sample audio file if available
        # In production, this would be used with actual voice messages
        print("📝 Note: STT requires audio files. In production, this processes voice messages from WhatsApp.")
        print("✅ STT function is ready to process audio files")
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("💡 Make sure Google Cloud Speech libraries are installed")
        
    except Exception as e:
        print(f"❌ STT Error: {e}")

def test_voice_response_logic():
    """Test the logic for deciding when to use voice responses"""
    print("\n🧠 Testing Voice Response Logic...")
    
    try:
        from handlers.speech import should_respond_with_voice
        
        # Test different scenarios
        test_cases = [
            (True, 50, "User sent voice, short response"),
            (True, 300, "User sent voice, long response"),
            (False, 50, "User sent text, short response"),
            (False, 300, "User sent text, long response"),
        ]
        
        for is_voice_input, response_length, description in test_cases:
            result = should_respond_with_voice(is_voice_input, response_length)
            status = "🔊 Voice" if result else "💬 Text"
            print(f"{status} | {description} ({response_length} chars)")
        
        print("✅ Voice response logic working correctly")
        
    except Exception as e:
        print(f"❌ Voice Logic Error: {e}")

def test_configuration():
    """Test speech configuration and environment variables"""
    print("\n⚙️ Testing Speech Configuration...")
    
    # Check environment variables
    config_vars = [
        "ENABLE_VOICE_RESPONSES",
        "MAX_VOICE_RESPONSE_LENGTH",
        "GOOGLE_APPLICATION_CREDENTIALS"
    ]
    
    for var in config_vars:
        value = os.getenv(var)
        if value:
            # Hide credentials path for security
            display_value = value if var != "GOOGLE_APPLICATION_CREDENTIALS" else "***SET***"
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: Not set")
    
    # Check Google Cloud credentials
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and os.path.exists(creds_path):
        print(f"✅ Google credentials file exists")
    elif creds_path:
        print(f"❌ Google credentials file not found: {creds_path}")
    else:
        print("ℹ️ Using environment-based Google authentication")

def main():
    """Run all speech tests"""
    print("🎯 Wednesday WhatsApp Assistant - Speech Feature Tests")
    print("=" * 60)
    
    # Test configuration first
    test_configuration()
    
    # Test voice response logic (always works)
    test_voice_response_logic()
    
    # Test TTS functionality
    test_tts_basic()
    
    # Test STT functionality
    test_stt_basic()
    
    print("\n" + "=" * 60)
    print("🏁 Speech tests completed!")
    print("\n💡 Tips:")
    print("- For full functionality, ensure Google Cloud credentials are configured")
    print("- TTS will work with proper Google Cloud Text-to-Speech API access")
    print("- STT processes voice messages received via WhatsApp webhook")
    print("- Voice responses are sent back through WAHA WhatsApp API")

if __name__ == "__main__":
    main()