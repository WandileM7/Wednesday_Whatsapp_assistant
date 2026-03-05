#!/usr/bin/env python3
"""
Bytez AI Integration Test Suite for Wednesday WhatsApp Assistant

This test file demonstrates the amazing capabilities of Bytez:
- 175,000+ AI models accessible through one API
- Chat models (Qwen, Phi, DeepSeek)
- Image generation (Dreamlike, Stability AI)
- Text-to-speech (Suno Bark)
- Vision/Image analysis (Gemma)

Get your API key at: https://bytez.com/settings
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for Bytez package
try:
    from bytez import Bytez
    BYTEZ_AVAILABLE = True
except ImportError:
    BYTEZ_AVAILABLE = False
    print("❌ Bytez not installed. Run: pip install bytez")
    sys.exit(1)

# Get API key
BYTEZ_API_KEY = os.getenv("BYTEZ_API_KEY")

if not BYTEZ_API_KEY:
    print("❌ BYTEZ_API_KEY not set!")
    print("\nTo get your API key:")
    print("1. Visit https://bytez.com/settings")
    print("2. Create an account and get your API key")
    print("3. Add to your .env file: BYTEZ_API_KEY=your_key_here")
    sys.exit(1)

# Initialize Bytez client
print("🚀 Initializing Bytez client...")
sdk = Bytez(BYTEZ_API_KEY)
print("✅ Bytez client ready!\n")


def test_chat():
    """Test chat/conversation capabilities"""
    print("=" * 50)
    print("🗣️ TEST: Chat Model (Qwen/Qwen3-4B)")
    print("=" * 50)
    
    model = sdk.model("Qwen/Qwen3-4B")
    
    messages = [
        {"role": "system", "content": "You are Wednesday, a helpful AI assistant with a witty personality."},
        {"role": "user", "content": "Hello! What can you help me with today?"}
    ]
    
    params = {"temperature": 0.7, "max_new_tokens": 200}
    
    print("Sending message to Qwen...")
    result = model.run(messages, params)
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        print(f"✅ Response:\n{result.output}\n")


def test_streaming_chat():
    """Test streaming chat responses"""
    print("=" * 50)
    print("🔄 TEST: Streaming Chat")
    print("=" * 50)
    
    model = sdk.model("Qwen/Qwen3-4B")
    
    messages = [
        {"role": "user", "content": "Count from 1 to 5 slowly."}
    ]
    
    print("Streaming response:")
    stream = model.run(messages, {"max_new_tokens": 100}, stream=True)
    
    full_text = ""
    for chunk in stream:
        print(chunk, end="", flush=True)
        full_text += chunk
    
    print(f"\n✅ Streaming complete! Total length: {len(full_text)}\n")


def test_text_generation():
    """Test text generation (completion)"""
    print("=" * 50)
    print("✍️ TEST: Text Generation (GPT-2)")
    print("=" * 50)
    
    model = sdk.model("openai-community/gpt2")
    
    input_text = "Once upon a time, in a land far away,"
    
    print(f"Prompt: {input_text}")
    result = model.run(input_text)
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        print(f"✅ Generated:\n{result.output}\n")


def test_text_to_speech():
    """Test text-to-speech with Bark model"""
    print("=" * 50)
    print("🔊 TEST: Text-to-Speech (suno/bark-small)")
    print("=" * 50)
    
    model = sdk.model("suno/bark-small")
    
    input_text = "Hello! I am Wednesday, your AI assistant."
    
    print(f"Converting to speech: '{input_text}'")
    result = model.run(input_text)
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        print(f"✅ Audio generated!")
        print(f"   Output: {result.output}\n")


def test_image_generation():
    """Test image generation"""
    print("=" * 50)
    print("🎨 TEST: Image Generation (Dreamlike)")
    print("=" * 50)
    
    model = sdk.model("dreamlike-art/dreamlike-photoreal-2.0")
    
    prompt = "A futuristic AI assistant, cyberpunk style, neon lights"
    
    print(f"Generating image: '{prompt}'")
    result = model.run(prompt)
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        print(f"✅ Image generated!")
        print(f"   URL: {result.output}\n")


def test_vision():
    """Test image/vision analysis"""
    print("=" * 50)
    print("👁️ TEST: Vision/Image Analysis")
    print("=" * 50)
    
    model = sdk.model("google/gemma-3-4b-it")
    
    # Test with a sample image URL
    input_content = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe this image in detail."
                },
                {
                    "type": "image",
                    "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/200px-PNG_transparency_demonstration_1.png"
                }
            ]
        }
    ]
    
    print("Analyzing image...")
    result = model.run(input_content)
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        output = result.output
        if isinstance(output, dict):
            print(f"✅ Analysis:\n{output.get('content', output)}\n")
        else:
            print(f"✅ Analysis:\n{output}\n")


def list_models():
    """List available models"""
    print("=" * 50)
    print("📋 Available Models (showing first 10)")
    print("=" * 50)
    
    result = sdk.list.models()
    
    if result.error:
        print(f"❌ Error: {result.error}")
    else:
        models = result.output[:10]
        for i, model in enumerate(models, 1):
            model_id = model.get('id', 'Unknown')
            print(f"   {i}. {model_id}")
        print(f"\n   ... and {len(result.output) - 10}+ more models!\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🤖 BYTEZ AI INTEGRATION TEST SUITE")
    print("   175,000+ AI Models at Your Fingertips!")
    print("=" * 60 + "\n")
    
    tests = [
        ("List Models", list_models),
        ("Chat", test_chat),
        ("Text Generation", test_text_generation),
        # Uncomment these to test additional features:
        # ("Streaming Chat", test_streaming_chat),
        # ("Text-to-Speech", test_text_to_speech),
        # ("Image Generation", test_image_generation),
        # ("Vision Analysis", test_vision),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"❌ {name} failed: {e}\n")
    
    print("=" * 60)
    print("✨ Tests complete!")
    print("\nBytez gives you access to:")
    print("   • 175,000+ AI models")
    print("   • Chat, Image, Speech, Vision, and more")
    print("   • All through one simple API")
    print("\nLearn more: https://docs.bytez.com")
    print("=" * 60)


if __name__ == "__main__":
    main()

