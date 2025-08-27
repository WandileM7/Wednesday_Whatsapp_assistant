"""
Text utility functions for WhatsApp Assistant

Provides text processing utilities including emoji removal for TTS
"""

import re
import logging

logger = logging.getLogger(__name__)

def remove_emojis(text: str) -> str:
    """
    Remove all emojis from text for TTS processing
    
    This function removes emojis to prevent TTS from reading them aloud,
    while preserving the actual text content.
    
    Args:
        text (str): Input text that may contain emojis
        
    Returns:
        str: Text with emojis removed and cleaned up
    """
    if not text:
        return text
    
    # More comprehensive emoji pattern that covers all Unicode emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "\U00002600-\U000026FF"  # Miscellaneous Symbols
        "\U00002700-\U000027BF"  # Additional Dingbats
        "\U0000FE00-\U0000FE0F"  # Variation Selectors
        "\U0001F000-\U0001F02F"  # Mahjong Tiles
        "\U0001F0A0-\U0001F0FF"  # Playing Cards
        "\U0000200D"             # Zero Width Joiner
        "\U0000FE0F"             # Variation Selector-16
        "]+", 
        flags=re.UNICODE
    )
    
    # Remove emojis
    text_no_emoji = emoji_pattern.sub('', text)
    
    # Additional cleanup for common emoji-related characters
    # Remove remaining emoji modifiers and variation selectors
    text_no_emoji = re.sub(r'[\u200d\ufe0f\u20e3]', '', text_no_emoji)
    
    # Clean up extra whitespace that might result from emoji removal
    text_cleaned = ' '.join(text_no_emoji.split())
    
    logger.debug(f"Emoji removal: '{text[:50]}...' -> '{text_cleaned[:50]}...'")
    
    return text_cleaned

def prepare_text_for_tts(text: str) -> str:
    """
    Prepare text for TTS by removing emojis and other problematic characters
    
    Args:
        text (str): Input text to prepare for TTS
        
    Returns:
        str: Text optimized for TTS processing
    """
    if not text:
        return text
    
    # Remove emojis
    text = remove_emojis(text)
    
    # Remove or replace other problematic characters for TTS
    # Replace markdown-style formatting that might interfere with TTS
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold markers
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Remove italic markers
    text = re.sub(r'`(.*?)`', r'\1', text)        # Remove code markers
    
    # Clean up extra whitespace
    text = ' '.join(text.split())
    
    # Ensure text ends with proper punctuation for natural speech
    if text and not text[-1] in '.!?':
        text += '.'
    
    return text

def format_text_for_display(text: str) -> str:
    """
    Format text for display (keeps emojis and formatting)
    
    This is used for text messages where emojis should be preserved.
    
    Args:
        text (str): Input text to format for display
        
    Returns:
        str: Text formatted for display (emojis preserved)
    """
    if not text:
        return text
    
    # Just clean up whitespace, preserve emojis and formatting
    return ' '.join(text.split())