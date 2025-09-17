"""
Enhanced Media Generation Handler for Wednesday WhatsApp Assistant

Provides AI-powered image and video generation capabilities:
- Image generation using OpenAI DALL-E or Stable Diffusion
- Video generation using available APIs
- Avatar system for assistant personality
- Media optimization for WhatsApp delivery
"""

import os
import logging
import requests
import base64
import io
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import openai
from database import db_manager

logger = logging.getLogger(__name__)

class MediaGenerator:
    """Advanced media generation service"""
    
    def __init__(self):
        self.openai_client = None
        self.avatar_cache = {}
        self.media_dir = "generated_media"
        self.max_file_size = 16 * 1024 * 1024  # 16MB WhatsApp limit
        
        # Ensure media directory exists
        os.makedirs(self.media_dir, exist_ok=True)
        
        # Initialize OpenAI client if API key is available
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                self.openai_client = openai.OpenAI(api_key=openai_key)
                logger.info("OpenAI client initialized for image generation")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        
        # Initialize Stable Diffusion if available
        self.stability_key = os.getenv("STABILITY_API_KEY")
        if self.stability_key:
            logger.info("Stability API key found for image generation")
    
    async def generate_image(self, prompt: str, phone: str, style: str = "realistic") -> Dict[str, Any]:
        """Generate image from text prompt"""
        try:
            media_id = str(uuid.uuid4())
            
            # Try OpenAI DALL-E first
            if self.openai_client:
                result = await self._generate_with_dalle(prompt, style, media_id)
                if result['success']:
                    self._save_media_metadata(phone, media_id, 'image', result)
                    return result
            
            # Fallback to Stability AI
            if self.stability_key:
                result = await self._generate_with_stability(prompt, style, media_id)
                if result['success']:
                    self._save_media_metadata(phone, media_id, 'image', result)
                    return result
            
            # Fallback to placeholder image
            return await self._generate_placeholder_image(prompt, media_id)
            
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'fallback_available': True
            }
    
    async def _generate_with_dalle(self, prompt: str, style: str, media_id: str) -> Dict[str, Any]:
        """Generate image using OpenAI DALL-E"""
        try:
            # Enhance prompt based on style
            enhanced_prompt = self._enhance_prompt(prompt, style)
            
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=enhanced_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            image_url = response.data[0].url
            
            # Download and save image
            img_response = requests.get(image_url)
            img_response.raise_for_status()
            
            file_path = os.path.join(self.media_dir, f"{media_id}.png")
            with open(file_path, 'wb') as f:
                f.write(img_response.content)
            
            # Optimize for WhatsApp if needed
            optimized_path = await self._optimize_for_whatsapp(file_path, 'image')
            
            return {
                'success': True,
                'media_id': media_id,
                'file_path': optimized_path,
                'file_size': os.path.getsize(optimized_path),
                'mime_type': 'image/png',
                'generator': 'dalle-3',
                'prompt': enhanced_prompt,
                'original_prompt': prompt
            }
            
        except Exception as e:
            logger.error(f"DALL-E generation failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _generate_with_stability(self, prompt: str, style: str, media_id: str) -> Dict[str, Any]:
        """Generate image using Stability AI"""
        try:
            url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.stability_key}"
            }
            
            enhanced_prompt = self._enhance_prompt(prompt, style)
            
            body = {
                "text_prompts": [
                    {
                        "text": enhanced_prompt,
                        "weight": 1
                    }
                ],
                "cfg_scale": 7,
                "height": 1024,
                "width": 1024,
                "samples": 1,
                "steps": 30,
            }
            
            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()
            
            data = response.json()
            
            # Save generated image
            image_data = base64.b64decode(data["artifacts"][0]["base64"])
            file_path = os.path.join(self.media_dir, f"{media_id}.png")
            
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            # Optimize for WhatsApp if needed
            optimized_path = await self._optimize_for_whatsapp(file_path, 'image')
            
            return {
                'success': True,
                'media_id': media_id,
                'file_path': optimized_path,
                'file_size': os.path.getsize(optimized_path),
                'mime_type': 'image/png',
                'generator': 'stability-ai',
                'prompt': enhanced_prompt,
                'original_prompt': prompt
            }
            
        except Exception as e:
            logger.error(f"Stability AI generation failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _generate_placeholder_image(self, prompt: str, media_id: str) -> Dict[str, Any]:
        """Generate a placeholder image with text"""
        try:
            # Create a simple placeholder image
            width, height = 800, 600
            image = Image.new('RGB', (width, height), color='lightblue')
            draw = ImageDraw.Draw(image)
            
            # Try to use a default font, fallback to basic if not available
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
            except:
                font = ImageFont.load_default()
            
            # Add text to image
            text_lines = [
                "🎨 AI Image Generation",
                "",
                "Generated for:",
                prompt[:50] + "..." if len(prompt) > 50 else prompt,
                "",
                f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ]
            
            y_offset = 100
            for line in text_lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                draw.text((x, y_offset), line, fill='darkblue', font=font)
                y_offset += 60
            
            # Save placeholder image
            file_path = os.path.join(self.media_dir, f"{media_id}_placeholder.png")
            image.save(file_path, 'PNG')
            
            return {
                'success': True,
                'media_id': media_id,
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'mime_type': 'image/png',
                'generator': 'placeholder',
                'prompt': prompt,
                'note': 'Placeholder image generated - configure OPENAI_API_KEY or STABILITY_API_KEY for AI generation'
            }
            
        except Exception as e:
            logger.error(f"Placeholder generation failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """Enhance prompt based on style preferences"""
        style_prefixes = {
            'realistic': 'Photorealistic, high quality, detailed, ',
            'artistic': 'Digital art, creative, vibrant colors, artistic style, ',
            'cartoon': 'Cartoon style, animated, colorful, friendly, ',
            'professional': 'Professional, clean, modern, business style, ',
            'avatar': 'Avatar style, character design, expressive, '
        }
        
        prefix = style_prefixes.get(style, '')
        return f"{prefix}{prompt}"
    
    async def _optimize_for_whatsapp(self, file_path: str, media_type: str) -> str:
        """Optimize media for WhatsApp delivery"""
        try:
            file_size = os.path.getsize(file_path)
            
            if file_size <= self.max_file_size:
                return file_path
            
            if media_type == 'image':
                # Compress image if too large
                with Image.open(file_path) as img:
                    # Reduce quality and/or size
                    quality = 85
                    while file_size > self.max_file_size and quality > 20:
                        optimized_path = file_path.replace('.png', f'_optimized_{quality}.jpg')
                        img.save(optimized_path, 'JPEG', quality=quality, optimize=True)
                        file_size = os.path.getsize(optimized_path)
                        quality -= 10
                    
                    if file_size <= self.max_file_size:
                        return optimized_path
            
            # If still too large, create a notification instead
            return file_path
            
        except Exception as e:
            logger.error(f"Media optimization failed: {e}")
            return file_path
    
    def _save_media_metadata(self, phone: str, media_id: str, media_type: str, result: Dict):
        """Save media metadata to database"""
        try:
            media_data = {
                'id': media_id,
                'phone': phone,
                'media_type': media_type,
                'file_path': result.get('file_path'),
                'file_size': result.get('file_size'),
                'mime_type': result.get('mime_type'),
                'metadata': {
                    'generator': result.get('generator'),
                    'prompt': result.get('prompt'),
                    'original_prompt': result.get('original_prompt'),
                    'created_at': datetime.now().isoformat()
                }
            }
            
            db_manager.add_media(media_data)
            
        except Exception as e:
            logger.error(f"Failed to save media metadata: {e}")
    
    def create_avatar(self, personality: str = "wednesday", style: str = "professional") -> str:
        """Create or get cached avatar for the assistant"""
        cache_key = f"{personality}_{style}"
        
        if cache_key in self.avatar_cache:
            return self.avatar_cache[cache_key]
        
        try:
            # Create a simple avatar using PIL
            width, height = 400, 400
            
            # Different avatar styles based on personality
            if personality.lower() == "wednesday":
                bg_color = 'darkslategray'
                text_color = 'lightcyan'
                avatar_text = "W"
            else:
                bg_color = 'royalblue'
                text_color = 'white'
                avatar_text = "AI"
            
            # Create circular avatar
            image = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(image)
            
            # Draw circle
            margin = 20
            draw.ellipse([margin, margin, width-margin, height-margin], fill=bg_color, outline=text_color, width=5)
            
            # Add letter
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
            except:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), avatar_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2 - 20
            
            draw.text((x, y), avatar_text, fill=text_color, font=font)
            
            # Save avatar
            avatar_path = os.path.join(self.media_dir, f"avatar_{cache_key}.png")
            image.save(avatar_path, 'PNG')
            
            self.avatar_cache[cache_key] = avatar_path
            return avatar_path
            
        except Exception as e:
            logger.error(f"Avatar creation failed: {e}")
            return None
    
    def get_media_info(self, media_id: str) -> Optional[Dict]:
        """Get media information by ID"""
        try:
            # This would query the database for media info
            # Implementation depends on your database structure
            return None
            
        except Exception as e:
            logger.error(f"Failed to get media info: {e}")
            return None
    
    def cleanup_old_media(self, days_old: int = 7):
        """Clean up old generated media files"""
        try:
            from pathlib import Path
            import time
            
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)
            media_path = Path(self.media_dir)
            
            if not media_path.exists():
                return
            
            cleaned_count = 0
            for file_path in media_path.iterdir():
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path}: {e}")
            
            logger.info(f"Cleaned up {cleaned_count} old media files")
            
        except Exception as e:
            logger.error(f"Media cleanup failed: {e}")
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get media generation service status"""
        return {
            'openai_available': bool(self.openai_client),
            'stability_available': bool(self.stability_key),
            'media_directory': self.media_dir,
            'cached_avatars': len(self.avatar_cache),
            'max_file_size_mb': self.max_file_size / (1024 * 1024)
        }

# Global media generator instance
media_generator = MediaGenerator()