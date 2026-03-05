"""
Image Analysis Handler
Analyzes images sent via WhatsApp using Bytez Vision models or Gemini as fallback.

Supports multiple vision models through Bytez:
- google/gemma-3-4b-it (default)
- llava-hf/LLaVA models
- And many more multimodal models
"""

import logging
import base64
import os
import tempfile
from typing import Dict, Any, Optional
import requests

# Try Bytez first (primary)
try:
    from bytez import Bytez
    BYTEZ_AVAILABLE = True
except ImportError:
    BYTEZ_AVAILABLE = False
    Bytez = None

# Gemini as fallback
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

logger = logging.getLogger(__name__)

# API Keys
BYTEZ_API_KEY = os.getenv("BYTEZ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Model Configuration
BYTEZ_VISION_MODEL = os.getenv("BYTEZ_VISION_MODEL", "google/gemma-3-4b-it")
GENERATION_MODEL = "gemini-2.5-flash"

# Initialize clients
bytez_client = None
genai_client = None

if BYTEZ_API_KEY and BYTEZ_AVAILABLE:
    try:
        bytez_client = Bytez(BYTEZ_API_KEY)
        logger.info(f"Bytez vision client ready with model: {BYTEZ_VISION_MODEL}")
    except Exception as e:
        logger.warning(f"Bytez client unavailable for image analysis: {e}")

if GEMINI_API_KEY and GENAI_AVAILABLE and not bytez_client:
    try:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini fallback ready for image analysis")
    except Exception as e:
        logger.warning(f"Gemini client unavailable for image analysis: {e}")


def analyze_image_from_url(image_url: str, question: str = None) -> Dict[str, Any]:
    """
    Analyze an image from a URL using Bytez Vision models or Gemini fallback.
    
    Args:
        image_url: URL of the image to analyze
        question: Optional specific question about the image
        
    Returns:
        Analysis result dictionary
    """
    # Try Bytez first
    if bytez_client:
        return _analyze_with_bytez(image_url, question)
    
    # Fallback to Gemini
    if genai_client:
        return _analyze_with_gemini_url(image_url, question)
    
    return {'error': 'No image analysis service configured. Set BYTEZ_API_KEY or GEMINI_API_KEY'}


def _analyze_with_bytez(image_url: str, question: str = None) -> Dict[str, Any]:
    """Analyze image using Bytez multimodal models."""
    try:
        model = bytez_client.model(BYTEZ_VISION_MODEL)
        
        # Build the prompt
        prompt_text = question or """Analyze this image comprehensively. Describe:
1. What the image shows (objects, people, text, etc.)
2. If it's a screenshot, identify the app/website and what's happening
3. If there's text, read and transcribe it
4. Any notable details or context
Be concise but thorough."""
        
        # Build multimodal input for Bytez
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "image",
                        "url": image_url
                    }
                ]
            }
        ]
        
        result = model.run(input_content)
        
        if result.error:
            logger.error(f"Bytez vision error: {result.error}")
            return {'error': str(result.error)}
        
        # Extract the response
        output = result.output
        if isinstance(output, dict):
            analysis = output.get("content", str(output))
        else:
            analysis = str(output)
        
        return {
            'success': True,
            'analysis': analysis,
            'provider': 'bytez',
            'model': BYTEZ_VISION_MODEL,
            'has_text': 'text' in analysis.lower(),
            'is_screenshot': any(word in analysis.lower() for word in ['screenshot', 'app', 'website', 'screen'])
        }
        
    except Exception as e:
        logger.error(f"Bytez image analysis error: {e}")
        # Try Gemini fallback
        if genai_client:
            return _analyze_with_gemini_url(image_url, question)
        return {'error': str(e)}


def _analyze_with_gemini_url(image_url: str, question: str = None) -> Dict[str, Any]:
    """Analyze image using Gemini Vision (fallback)."""
    try:
        # Download the image
        response = requests.get(image_url, timeout=30)
        if response.status_code != 200:
            return {'error': f'Failed to download image: {response.status_code}'}
        
        image_data = response.content
        
        # Determine mime type
        content_type = response.headers.get('content-type', 'image/jpeg')
        if 'png' in content_type:
            mime_type = 'image/png'
        elif 'gif' in content_type:
            mime_type = 'image/gif'
        elif 'webp' in content_type:
            mime_type = 'image/webp'
        else:
            mime_type = 'image/jpeg'
        
        return analyze_image_data(image_data, mime_type, question)
        
    except Exception as e:
        logger.error(f"Error analyzing image from URL: {e}")
        return {'error': str(e)}


def analyze_image_from_file(file_path: str, question: str = None) -> Dict[str, Any]:
    """
    Analyze an image from a local file using Gemini Vision.
    
    Args:
        file_path: Path to the image file
        question: Optional specific question about the image
        
    Returns:
        Analysis result dictionary
    """
    try:
        if not os.path.exists(file_path):
            return {'error': 'File not found'}
        
        with open(file_path, 'rb') as f:
            image_data = f.read()
        
        # Determine mime type from extension
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        return analyze_image_data(image_data, mime_type, question)
        
    except Exception as e:
        logger.error(f"Error analyzing image from file: {e}")
        return {'error': str(e)}


def analyze_image_data(image_data: bytes, mime_type: str, question: str = None) -> Dict[str, Any]:
    """
    Analyze image data using Gemini Vision (used as fallback for Bytez).
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
        question: Optional specific question about the image
        
    Returns:
        Analysis result dictionary
    """
    try:
        if not genai_client:
            return {'error': 'Gemini API key not configured for image data analysis'}
        
        # Encode image to base64
        image_b64 = base64.standard_b64encode(image_data).decode('utf-8')
        
        # Build the prompt
        if question:
            prompt = f"""Analyze this image and answer the following question: {question}

Be specific and helpful in your response. If the image contains text, read it. 
If it's a screenshot, describe what app or website it's from and what it shows.
If it's a photo, describe what you see."""
        else:
            prompt = """Analyze this image comprehensively. Describe:
1. What the image shows (objects, people, text, etc.)
2. If it's a screenshot, identify the app/website and what's happening
3. If there's text, read and transcribe it
4. Any notable details or context
5. If it's a document, summarize the key information

Be concise but thorough."""

        # Create the image part
        image_part = {
            "inline_data": {
                "mime_type": mime_type,
                "data": image_b64
            }
        }

        # Generate response
        response = genai_client.models.generate_content(
            model=GENERATION_MODEL,
            contents=[prompt, image_part],
        )
        
        if response and response.text:
            return {
                'success': True,
                'analysis': response.text,
                'provider': 'gemini',
                'model': GENERATION_MODEL,
                'has_text': 'text' in response.text.lower(),
                'is_screenshot': any(word in response.text.lower() for word in ['screenshot', 'app', 'website', 'screen'])
            }
        else:
            return {'error': 'No analysis generated'}
            
    except Exception as e:
        logger.error(f"Error in image analysis: {e}")
        return {'error': str(e)}


def analyze_whatsapp_image(media_url: str, caption: str = None) -> str:
    """
    Analyze an image received via WhatsApp.
    
    Args:
        media_url: URL of the WhatsApp media
        caption: Optional caption/question from user
        
    Returns:
        Formatted analysis response
    """
    result = analyze_image_from_url(media_url, caption)
    
    if result.get('error'):
        return f"❌ Couldn't analyze image: {result['error']}"
    
    analysis = result.get('analysis', 'No analysis available')
    provider = result.get('provider', 'unknown')
    model = result.get('model', 'unknown')
    
    response = "🔍 **Image Analysis**\n\n"
    response += analysis
    
    if result.get('is_screenshot'):
        response += "\n\n📱 _This appears to be a screenshot_"
    
    if result.get('has_text'):
        response += "\n📝 _Text was detected in the image_"
    
    response += f"\n\n_Powered by {provider} ({model})_"
    
    return response


def extract_text_from_image(image_url: str) -> Dict[str, Any]:
    """
    Extract text from an image (OCR).
    
    Args:
        image_url: URL of the image
        
    Returns:
        Extracted text result
    """
    result = analyze_image_from_url(
        image_url, 
        "Extract and transcribe ALL text visible in this image. Format it clearly."
    )
    
    if result.get('error'):
        return result
    
    return {
        'success': True,
        'text': result.get('analysis', ''),
        'source': result.get('provider', 'vision-model')
    }


def describe_image(image_url: str) -> str:
    """
    Get a simple description of an image.
    
    Args:
        image_url: URL of the image
        
    Returns:
        Image description string
    """
    result = analyze_image_from_url(
        image_url,
        "Describe this image in 2-3 sentences."
    )
    
    if result.get('error'):
        return f"Couldn't describe image: {result['error']}"
    
    return result.get('analysis', 'No description available')


def get_vision_status() -> Dict[str, Any]:
    """Get the status of vision/image analysis services."""
    return {
        'bytez_available': bytez_client is not None,
        'gemini_available': genai_client is not None,
        'primary_provider': 'bytez' if bytez_client else ('gemini' if genai_client else 'none'),
        'bytez_model': BYTEZ_VISION_MODEL if bytez_client else None,
        'gemini_model': GENERATION_MODEL if genai_client else None
    }
