"""
Mood-Based Music Handler
Analyzes message mood and plays matching music.
"""

import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Mood to playlist/genre mapping
MOOD_PLAYLISTS = {
    'happy': {
        'genres': ['pop', 'dance', 'funk'],
        'keywords': ['happy', 'great', 'amazing', 'awesome', 'excited', 'joy', 'wonderful', 'fantastic', 'love', 'celebrate'],
        'spotify_queries': ['happy hits', 'feel good', 'good vibes'],
        'emoji': '😊'
    },
    'sad': {
        'genres': ['acoustic', 'indie', 'soul'],
        'keywords': ['sad', 'down', 'depressed', 'upset', 'crying', 'miss', 'lonely', 'heartbreak', 'hurt', 'broken'],
        'spotify_queries': ['sad songs', 'melancholy', 'emotional'],
        'emoji': '😢'
    },
    'energetic': {
        'genres': ['edm', 'hip-hop', 'rock'],
        'keywords': ['pumped', 'energy', 'workout', 'gym', 'run', 'exercise', 'hype', 'lets go', 'fired up', 'motivated'],
        'spotify_queries': ['workout', 'pump up', 'high energy'],
        'emoji': '💪'
    },
    'relaxed': {
        'genres': ['chill', 'ambient', 'jazz'],
        'keywords': ['relax', 'chill', 'calm', 'peaceful', 'rest', 'unwind', 'cozy', 'lazy', 'sleepy', 'tired'],
        'spotify_queries': ['chill vibes', 'relaxing', 'lo-fi'],
        'emoji': '😌'
    },
    'focused': {
        'genres': ['classical', 'ambient', 'electronic'],
        'keywords': ['focus', 'work', 'study', 'concentrate', 'productive', 'coding', 'reading', 'thinking'],
        'spotify_queries': ['deep focus', 'concentration', 'study music'],
        'emoji': '🎯'
    },
    'romantic': {
        'genres': ['r&b', 'soul', 'love songs'],
        'keywords': ['love', 'romantic', 'date', 'bae', 'partner', 'girlfriend', 'boyfriend', 'valentine'],
        'spotify_queries': ['romantic', 'love songs', 'date night'],
        'emoji': '❤️'
    },
    'angry': {
        'genres': ['rock', 'metal', 'hip-hop'],
        'keywords': ['angry', 'frustrated', 'annoyed', 'mad', 'furious', 'rage', 'hate', 'pissed'],
        'spotify_queries': ['rock anthems', 'aggressive', 'rage'],
        'emoji': '😤'
    },
    'nostalgic': {
        'genres': ['80s', '90s', 'oldies'],
        'keywords': ['remember', 'memories', 'old', 'throwback', 'nostalgia', 'childhood', 'back in'],
        'spotify_queries': ['throwback', 'nostalgia', 'classics'],
        'emoji': '🥹'
    },
    'party': {
        'genres': ['dance', 'edm', 'pop'],
        'keywords': ['party', 'dance', 'club', 'weekend', 'friday', 'saturday', 'drinks', 'celebration'],
        'spotify_queries': ['party hits', 'dance party', 'club bangers'],
        'emoji': '🎉'
    }
}


def detect_mood(text: str) -> Dict[str, Any]:
    """
    Detect the mood from a message.
    
    Args:
        text: User's message
        
    Returns:
        Detected mood and confidence
    """
    text_lower = text.lower()
    
    mood_scores = {}
    
    for mood, config in MOOD_PLAYLISTS.items():
        score = 0
        matched_keywords = []
        
        for keyword in config['keywords']:
            if keyword in text_lower:
                score += 1
                matched_keywords.append(keyword)
        
        if score > 0:
            mood_scores[mood] = {
                'score': score,
                'keywords': matched_keywords
            }
    
    if not mood_scores:
        # Default mood based on time of day
        hour = datetime.now().hour
        if 6 <= hour < 12:
            return {'mood': 'energetic', 'confidence': 0.3, 'source': 'time_of_day'}
        elif 12 <= hour < 17:
            return {'mood': 'focused', 'confidence': 0.3, 'source': 'time_of_day'}
        elif 17 <= hour < 21:
            return {'mood': 'relaxed', 'confidence': 0.3, 'source': 'time_of_day'}
        else:
            return {'mood': 'relaxed', 'confidence': 0.3, 'source': 'time_of_day'}
    
    # Get the mood with highest score
    best_mood = max(mood_scores.items(), key=lambda x: x[1]['score'])
    
    return {
        'mood': best_mood[0],
        'confidence': min(best_mood[1]['score'] / 3, 1.0),  # Normalize confidence
        'keywords': best_mood[1]['keywords'],
        'source': 'text_analysis'
    }


def get_mood_playlist(mood: str) -> Dict[str, Any]:
    """
    Get playlist recommendations for a mood.
    
    Args:
        mood: Detected or specified mood
        
    Returns:
        Playlist recommendation
    """
    config = MOOD_PLAYLISTS.get(mood, MOOD_PLAYLISTS['relaxed'])
    
    return {
        'mood': mood,
        'emoji': config['emoji'],
        'genres': config['genres'],
        'search_queries': config['spotify_queries'],
        'recommended_query': config['spotify_queries'][0]
    }


def play_music_for_mood(mood: str, phone: str = "") -> str:
    """
    Play music matching a mood on Spotify.
    
    Args:
        mood: The mood to match
        phone: User's phone for context
        
    Returns:
        Response message
    """
    try:
        from handlers.spotify import play_song, search_and_play
        
        playlist_info = get_mood_playlist(mood)
        query = playlist_info['recommended_query']
        
        # Try to play a playlist matching the mood
        try:
            result = search_and_play(query, 'playlist')
            if 'error' not in str(result).lower():
                return f"{playlist_info['emoji']} Playing **{mood}** music!\n\n🎵 Searching for: {query}"
        except Exception:
            pass
        
        # Fallback to playing a song with the mood keyword
        try:
            result = play_song(f"{mood} music")
            return f"{playlist_info['emoji']} Playing **{mood}** vibes!\n\n🎵 Enjoying some {mood} music"
        except Exception as e:
            return f"Couldn't play {mood} music: {e}"
            
    except ImportError:
        return "Spotify integration not available"
    except Exception as e:
        logger.error(f"Error playing mood music: {e}")
        return f"Error playing music: {e}"


def analyze_and_play(text: str, phone: str = "") -> str:
    """
    Analyze message mood and play matching music.
    
    Args:
        text: User's message
        phone: User's phone for context
        
    Returns:
        Response message
    """
    mood_result = detect_mood(text)
    mood = mood_result['mood']
    confidence = mood_result.get('confidence', 0.5)
    
    playlist_info = get_mood_playlist(mood)
    
    response = f"{playlist_info['emoji']} I sense you're feeling **{mood}**"
    
    if mood_result.get('keywords'):
        response += f" (picked up on: {', '.join(mood_result['keywords'])})"
    
    response += "\n\n"
    
    # Try to play music
    play_result = play_music_for_mood(mood, phone)
    response += play_result
    
    return response


def get_mood_suggestions(mood: str) -> str:
    """
    Get music suggestions for a mood without playing.
    
    Args:
        mood: The mood
        
    Returns:
        Formatted suggestions
    """
    playlist_info = get_mood_playlist(mood)
    
    response = f"{playlist_info['emoji']} **Music for {mood.title()} Mood**\n\n"
    response += f"🎸 **Genres**: {', '.join(playlist_info['genres'])}\n"
    response += f"🔍 **Try searching**: {', '.join(playlist_info['search_queries'])}\n\n"
    response += f"Say 'play {mood} music' to start listening!"
    
    return response


# Service class
class MoodMusicService:
    """Service for mood-based music playback."""
    
    def detect_mood(self, text: str) -> Dict[str, Any]:
        return detect_mood(text)
    
    def play_for_mood(self, mood: str, phone: str = "") -> str:
        return play_music_for_mood(mood, phone)
    
    def analyze_and_play(self, text: str, phone: str = "") -> str:
        return analyze_and_play(text, phone)
    
    def get_suggestions(self, mood: str) -> str:
        return get_mood_suggestions(mood)


mood_music_service = MoodMusicService()
