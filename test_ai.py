#!/usr/bin/env python3
"""
Comprehensive AI Test Suite for Wednesday WhatsApp Assistant
Tests all Bytez AI functionality: Chat, Image Generation, TTS, STT, Vision

Run: python test_ai.py
Or specific tests: python test_ai.py --test chat
"""

import os
import sys
import time
import json
import argparse
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ANSI colors for pretty output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_test(name: str, status: bool, details: str = ""):
    icon = f"{Colors.GREEN}✅" if status else f"{Colors.RED}❌"
    color = Colors.GREEN if status else Colors.RED
    print(f"{icon} {color}{name}{Colors.ENDC}")
    if details:
        print(f"   {Colors.CYAN}{details[:200]}{'...' if len(details) > 200 else ''}{Colors.ENDC}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

# Initialize Bytez
try:
    from bytez import Bytez
    BYTEZ_API_KEY = os.getenv("BYTEZ_API_KEY")
    if BYTEZ_API_KEY:
        sdk = Bytez(BYTEZ_API_KEY)
        BYTEZ_AVAILABLE = True
    else:
        BYTEZ_AVAILABLE = False
        sdk = None
except ImportError:
    BYTEZ_AVAILABLE = False
    sdk = None

# Model configurations (matching bytez_handler.py)
MODELS = {
    "chat": os.getenv("BYTEZ_CHAT_MODEL", "openai/gpt-oss-20b"),
    "chat_fast": os.getenv("BYTEZ_CHAT_MODEL_FAST", "Qwen/Qwen3-30B-A3B"),
    "chat_fallback": os.getenv("BYTEZ_CHAT_MODEL_FALLBACK", "Qwen/Qwen3-4B"),
    "audio": os.getenv("BYTEZ_AUDIO_MODEL", "Qwen/Qwen2-Audio-7B-Instruct"),
    "image": os.getenv("BYTEZ_IMAGE_MODEL", "black-forest-labs/FLUX.1-dev"),
    "image_fast": os.getenv("BYTEZ_IMAGE_MODEL_FAST", "black-forest-labs/FLUX.1-schnell"),
    "tts": os.getenv("BYTEZ_TTS_MODEL", "suno/bark"),
    "tts_fast": os.getenv("BYTEZ_TTS_MODEL_FAST", "nari-labs/Dia-1.6B"),
    "vision": os.getenv("BYTEZ_VISION_MODEL", "Qwen/Qwen2-VL-72B-Instruct"),
    "vision_fast": os.getenv("BYTEZ_VISION_MODEL_FAST", "Qwen/Qwen2-VL-7B-Instruct"),
}

# Test results storage
test_results: List[Dict[str, Any]] = []


def record_result(test_name: str, passed: bool, duration: float, details: str = "", error: str = ""):
    """Record test result for summary"""
    test_results.append({
        "name": test_name,
        "passed": passed,
        "duration": duration,
        "details": details,
        "error": error,
        "timestamp": datetime.now().isoformat()
    })


# ============== CHAT TESTS ==============

def test_chat_basic():
    """Test basic chat completion"""
    test_name = "Chat - Basic Completion"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["chat_fallback"])  # Use fast model for testing
        
        messages = [
            {"role": "user", "content": "What is 2 + 2? Reply with just the number."}
        ]
        
        result = model.run(messages)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        response = str(result.output)
        passed = "4" in response
        print_test(test_name, passed, f"Response: {response} ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=response)
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


def test_chat_streaming():
    """Test streaming chat completion"""
    test_name = "Chat - Streaming"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["chat_fallback"])
        
        messages = [
            {"role": "user", "content": "Count from 1 to 5, each number on a new line."}
        ]
        
        full_response = ""
        chunk_count = 0
        
        stream = model.run(messages, stream=True)
        for chunk in stream:
            if hasattr(chunk, 'output') and chunk.output:
                full_response += str(chunk.output)
                chunk_count += 1
        
        duration = time.time() - start
        passed = chunk_count > 0 and len(full_response) > 0
        print_test(test_name, passed, f"Got {chunk_count} chunks ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=f"{chunk_count} chunks")
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


def test_chat_conversation():
    """Test multi-turn conversation"""
    test_name = "Chat - Conversation"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["chat_fallback"])
        
        messages = [
            {"role": "user", "content": "My name is Alice."},
            {"role": "assistant", "content": "Hello Alice! Nice to meet you."},
            {"role": "user", "content": "What is my name?"}
        ]
        
        result = model.run(messages)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        response = str(result.output).lower()
        passed = "alice" in response
        print_test(test_name, passed, f"Remembered name: {'Yes' if passed else 'No'} ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=response[:100])
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


def test_chat_function_calling():
    """Test function calling via instruction"""
    test_name = "Chat - Function Calling Pattern"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["chat_fallback"])
        
        system_prompt = """You are an assistant with access to these functions:
- get_weather(location: string) - Get weather for a location
- play_song(song_name: string) - Play a song

When the user requests something that matches a function, respond ONLY with JSON:
{"function": "function_name", "params": {"param": "value"}}

If no function matches, respond normally."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "What's the weather in Tokyo?"}
        ]
        
        result = model.run(messages)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        response = str(result.output)
        # Check if response contains function call pattern
        passed = "get_weather" in response.lower() or "tokyo" in response.lower()
        print_test(test_name, passed, f"Function detected: {passed} ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=response[:150])
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


# ============== IMAGE TESTS ==============

def test_image_generation():
    """Test text-to-image generation"""
    test_name = "Image - Generation (FLUX)"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["image_fast"])  # Use fast model for testing
        
        prompt = "A cute robot holding a coffee cup, digital art style"
        result = model.run(prompt)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        # Check if we got an image URL or data
        output = result.output
        passed = output is not None and (
            isinstance(output, str) and (output.startswith("http") or output.startswith("data:"))
        ) or isinstance(output, bytes)
        
        print_test(test_name, passed, f"Image generated ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=str(output)[:100] if output else "No output")
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


# ============== TEXT-TO-SPEECH TESTS ==============

def test_tts_generation():
    """Test text-to-speech generation"""
    test_name = "TTS - Speech Synthesis (Bark)"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["tts_fast"])  # Use fast model
        
        text = "Hello! This is a test of text to speech synthesis."
        result = model.run(text)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        # Check if we got audio output
        output = result.output
        passed = output is not None
        
        print_test(test_name, passed, f"Audio generated ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=str(output)[:100] if output else "No output")
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


# ============== SPEECH-TO-TEXT TESTS ==============

def test_audio_transcription():
    """Test audio-to-text transcription (Qwen2-Audio)"""
    test_name = "STT - Audio Transcription (Qwen2-Audio)"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["audio"])
        
        # Use a sample audio URL (public domain)
        # Note: In real testing, use a local audio file or test URL
        sample_audio_url = "https://upload.wikimedia.org/wikipedia/commons/4/4c/En-us-hello.ogg"
        
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe this audio exactly."
                    },
                    {
                        "type": "audio",
                        "url": sample_audio_url
                    }
                ]
            }
        ]
        
        result = model.run(input_content)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        transcription = str(result.output) if result.output else ""
        passed = len(transcription) > 0
        
        print_test(test_name, passed, f"Transcription: {transcription[:100]} ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=transcription[:100])
        return passed
        
    except Exception as e:
        duration = time.time() - start
        # Audio model might not be available in all regions
        if "not found" in str(e).lower() or "404" in str(e):
            print_test(test_name, False, "Model not available in region")
            record_result(test_name, False, duration, error="Model not available")
        else:
            print_test(test_name, False, f"Exception: {e}")
            record_result(test_name, False, duration, error=str(e))
        return False


# ============== VISION TESTS ==============

def test_vision_analysis():
    """Test image analysis/vision (Qwen2-VL)"""
    test_name = "Vision - Image Analysis (Qwen2-VL)"
    start = time.time()
    
    if not sdk:
        print_test(test_name, False, "Bytez SDK not available")
        record_result(test_name, False, 0, error="SDK not available")
        return False
    
    try:
        model = sdk.model(MODELS["vision_fast"])  # Use fast model
        
        # Use a sample image URL
        sample_image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/300px-PNG_transparency_demonstration_1.png"
        
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What do you see in this image? Describe briefly."
                    },
                    {
                        "type": "image",
                        "url": sample_image_url
                    }
                ]
            }
        ]
        
        result = model.run(input_content)
        duration = time.time() - start
        
        if result.error:
            print_test(test_name, False, f"Error: {result.error}")
            record_result(test_name, False, duration, error=str(result.error))
            return False
        
        description = str(result.output) if result.output else ""
        passed = len(description) > 10  # Should have some meaningful description
        
        print_test(test_name, passed, f"Analysis: {description[:100]} ({duration:.2f}s)")
        record_result(test_name, passed, duration, details=description[:100])
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Exception: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


# ============== INTEGRATION TESTS ==============

def test_bytez_handler_import():
    """Test that bytez_handler imports correctly"""
    test_name = "Integration - Handler Import"
    start = time.time()
    
    try:
        from handlers.bytez_handler import (
            chat_with_functions,
            execute_function,
            generate_image,
            synthesize_speech,
            transcribe_audio,
            analyze_image,
            get_bytez_status
        )
        
        duration = time.time() - start
        status = get_bytez_status()
        
        passed = status.get("configured", False) or status.get("available", False)
        print_test(test_name, passed, f"Handler loaded, status: {status.get('chat_model', 'N/A')}")
        record_result(test_name, passed, duration, details=json.dumps(status))
        return passed
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Import failed: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


def test_speech_handler_import():
    """Test that speech handler imports correctly with Bytez"""
    test_name = "Integration - Speech Handler Import"
    start = time.time()
    
    try:
        from handlers.speech import (
            speech_to_text,
            speech_to_text_bytez,
            text_to_speech,
            text_to_speech_bytez
        )
        
        duration = time.time() - start
        print_test(test_name, True, f"Speech handler loaded with Bytez support")
        record_result(test_name, True, duration)
        return True
        
    except Exception as e:
        duration = time.time() - start
        print_test(test_name, False, f"Import failed: {e}")
        record_result(test_name, False, duration, error=str(e))
        return False


# ============== MODEL INFO ==============

def test_list_models():
    """List and verify configured models"""
    test_name = "Info - Model Configuration"
    start = time.time()
    
    print_info("Configured models:")
    for model_type, model_name in MODELS.items():
        print(f"   {Colors.CYAN}{model_type:15}{Colors.ENDC}: {model_name}")
    
    duration = time.time() - start
    record_result(test_name, True, duration, details=json.dumps(MODELS))
    return True


# ============== MAIN ==============

def run_all_tests():
    """Run all tests"""
    print_header("Wednesday AI Test Suite - Bytez Integration")
    
    # Check prerequisites
    print_info(f"Bytez SDK Available: {BYTEZ_AVAILABLE}")
    print_info(f"API Key Set: {bool(os.getenv('BYTEZ_API_KEY'))}")
    
    if not BYTEZ_AVAILABLE:
        print_warning("Bytez SDK not installed. Run: pip install bytez")
        return
    
    if not os.getenv("BYTEZ_API_KEY"):
        print_warning("BYTEZ_API_KEY not set. Add it to your .env file")
        return
    
    # Model info
    print_header("Model Configuration")
    test_list_models()
    
    # Chat tests
    print_header("Chat Tests")
    test_chat_basic()
    test_chat_streaming()
    test_chat_conversation()
    test_chat_function_calling()
    
    # Image tests
    print_header("Image Generation Tests")
    test_image_generation()
    
    # TTS tests
    print_header("Text-to-Speech Tests")
    test_tts_generation()
    
    # STT tests  
    print_header("Speech-to-Text Tests")
    test_audio_transcription()
    
    # Vision tests
    print_header("Vision Tests")
    test_vision_analysis()
    
    # Integration tests
    print_header("Integration Tests")
    test_bytez_handler_import()
    test_speech_handler_import()
    
    # Summary
    print_header("Test Summary")
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    
    print(f"{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}")
    print(f"Total time: {sum(r['duration'] for r in test_results):.2f}s")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 All tests passed!{Colors.ENDC}")
    else:
        print(f"\n{Colors.YELLOW}Failed tests:{Colors.ENDC}")
        for r in test_results:
            if not r["passed"]:
                print(f"   {Colors.RED}• {r['name']}: {r.get('error', 'Unknown error')}{Colors.ENDC}")
    
    return passed == total


def run_specific_test(test_name: str):
    """Run a specific test by name"""
    tests = {
        "chat": [test_chat_basic, test_chat_streaming, test_chat_conversation, test_chat_function_calling],
        "image": [test_image_generation],
        "tts": [test_tts_generation],
        "stt": [test_audio_transcription],
        "vision": [test_vision_analysis],
        "integration": [test_bytez_handler_import, test_speech_handler_import],
        "models": [test_list_models],
    }
    
    if test_name not in tests:
        print_warning(f"Unknown test: {test_name}")
        print_info(f"Available tests: {', '.join(tests.keys())}")
        return False
    
    print_header(f"Running {test_name} tests")
    
    for test_func in tests[test_name]:
        test_func()
    
    # Summary
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}")
    
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Test Suite for Wednesday Assistant")
    parser.add_argument("--test", "-t", help="Run specific test (chat, image, tts, stt, vision, integration, models)")
    parser.add_argument("--list", "-l", action="store_true", help="List available tests")
    
    args = parser.parse_args()
    
    if args.list:
        print("Available tests:")
        print("  chat        - Chat completion tests")
        print("  image       - Image generation tests")
        print("  tts         - Text-to-speech tests")
        print("  stt         - Speech-to-text tests")
        print("  vision      - Vision/image analysis tests")
        print("  integration - Handler import tests")
        print("  models      - List configured models")
        sys.exit(0)
    
    if args.test:
        success = run_specific_test(args.test)
    else:
        success = run_all_tests()
    
    sys.exit(0 if success else 1)
