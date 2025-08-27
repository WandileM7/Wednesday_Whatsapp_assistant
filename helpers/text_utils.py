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
    # This includes the latest Unicode emoji specifications
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
        # Additional common emoji ranges that might be missed
        "\U0000231A-\U0000231B"  # watch, hourglass
        "\U0000FE30-\U0000FE4F"  # CJK compatibility forms
        "\U0001F004-\U0001F004"  # mahjong tile red dragon
        "\U0001F170-\U0001F251"  # enclosed alphanumeric supplement
        "]+", 
        flags=re.UNICODE
    )
    
    # Remove emojis
    text_no_emoji = emoji_pattern.sub('', text)
    
    # Additional cleanup for remaining problematic characters
    # Remove remaining emoji modifiers, variation selectors, and skin tone modifiers
    text_no_emoji = re.sub(r'[\u200d\ufe0f\u20e3\U0001f3fb-\U0001f3ff]', '', text_no_emoji)
    
    # Handle specific common emoji that might slip through
    # This catches emoji that use combining characters or are in unusual ranges
    additional_emoji_chars = [
        '\u231a', '\u231b',  # watch, hourglass
        '\u23f0', '\u23f3',  # alarm clock, hourglass
        '\u2600', '\u2601', '\u2602', '\u2603',  # sun, cloud, umbrella, snowman
        '\u260e', '\u2614', '\u2615',  # phone, umbrella, coffee
        '\u2618', '\u261d', '\u2620',  # shamrock, pointing finger, skull
        '\u2622', '\u2623', '\u2626',  # radioactive, biohazard, orthodox cross
        '\u262a', '\u262e', '\u262f',  # star and crescent, peace, yin yang
        '\u2638', '\u2639', '\u263a',  # wheel of dharma, frowning face, smiling face
        '\u2648', '\u2649', '\u264a', '\u264b', '\u264c', '\u264d', '\u264e', '\u264f',  # zodiac
        '\u2650', '\u2651', '\u2652', '\u2653',  # more zodiac
        '\u2660', '\u2663', '\u2665', '\u2666',  # card suits
        '\u2668', '\u267b', '\u267e', '\u267f',  # hot springs, recycling, infinity, wheelchair
        '\u2692', '\u2693', '\u2694', '\u2695', '\u2696', '\u2697', '\u2698', '\u2699',  # tools
        '\u269a', '\u269b', '\u269c',  # staff of aesculapius, atom, fleur-de-lis
        '\u26a0', '\u26a1', '\u26aa', '\u26ab', '\u26bd', '\u26be', '\u26c4', '\u26c5',  # warning, lightning, circles, balls, snowman, sun
        '\u26ce', '\u26d1', '\u26d3', '\u26d4', '\u26e9', '\u26ea', '\u26f0', '\u26f1',  # ophiuchus, helmet, chains, no entry, shinto shrine, church, mountain, umbrella
        '\u26f2', '\u26f3', '\u26f4', '\u26f5', '\u26f7', '\u26f8', '\u26f9', '\u26fa',  # fountain, golf, boat, sailing, skier, ice skate, person bouncing ball, tent
        '\u26fd',  # fuel pump
        # Add the specific clock emojis that were missed
        '\u23f1', '\u23f2',  # stopwatch, timer clock
        '\U0001f550', '\U0001f551', '\U0001f552', '\U0001f553', '\U0001f554', '\U0001f555',  # clock faces 1-6
        '\U0001f556', '\U0001f557', '\U0001f558', '\U0001f559', '\U0001f55a', '\U0001f55b',  # clock faces 7-12
        '\U0001f55c', '\U0001f55d', '\U0001f55e', '\U0001f55f', '\U0001f560', '\U0001f561',  # clock faces 12:30-6:30
        '\U0001f562', '\U0001f563', '\U0001f564', '\U0001f565', '\U0001f566', '\U0001f567'   # clock faces 7:30-12:30
    ]
    
    for emoji_char in additional_emoji_chars:
        text_no_emoji = text_no_emoji.replace(emoji_char, '')
    
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