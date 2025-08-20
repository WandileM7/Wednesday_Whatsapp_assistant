"""
News service for WhatsApp Assistant

Provides news summaries using NewsAPI
"""

import os
import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class NewsService:
    """News information service"""
    
    def __init__(self):
        self.api_key = os.getenv("NEWS_API_KEY")
        self.base_url = "https://newsapi.org/v2"
        
    def is_configured(self) -> bool:
        """Check if news service is properly configured"""
        return bool(self.api_key)
    
    def get_top_headlines(self, country: str = "us", category: Optional[str] = None, limit: int = 5) -> str:
        """Get top headlines"""
        if not self.is_configured():
            return "News service not configured. Please set NEWS_API_KEY environment variable."
        
        try:
            url = f"{self.base_url}/top-headlines"
            params = {
                'apiKey': self.api_key,
                'country': country,
                'pageSize': limit
            }
            
            if category:
                params['category'] = category
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['status'] != 'ok':
                return f"News API error: {data.get('message', 'Unknown error')}"
            
            return self._format_headlines(data['articles'], f"Top Headlines ({country.upper()})")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"News API request failed: {e}")
            return f"Failed to get news: {str(e)}"
        except Exception as e:
            logger.error(f"News service error: {e}")
            return f"News service error: {str(e)}"
    
    def search_news(self, query: str, limit: int = 5, language: str = "en") -> str:
        """Search for news articles"""
        if not self.is_configured():
            return "News service not configured. Please set NEWS_API_KEY environment variable."
        
        try:
            url = f"{self.base_url}/everything"
            params = {
                'apiKey': self.api_key,
                'q': query,
                'language': language,
                'sortBy': 'publishedAt',
                'pageSize': limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['status'] != 'ok':
                return f"News API error: {data.get('message', 'Unknown error')}"
            
            return self._format_headlines(data['articles'], f"Search results for '{query}'")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"News search API request failed: {e}")
            return f"Failed to search news: {str(e)}"
        except Exception as e:
            logger.error(f"News search service error: {e}")
            return f"News search service error: {str(e)}"
    
    def get_business_news(self, limit: int = 5) -> str:
        """Get business news headlines"""
        return self.get_top_headlines(category='business', limit=limit)
    
    def get_technology_news(self, limit: int = 5) -> str:
        """Get technology news headlines"""
        return self.get_top_headlines(category='technology', limit=limit)
    
    def get_science_news(self, limit: int = 5) -> str:
        """Get science news headlines"""
        return self.get_top_headlines(category='science', limit=limit)
    
    def get_daily_briefing(self) -> str:
        """Get a daily news briefing with mixed categories"""
        if not self.is_configured():
            return "News service not configured. Please set NEWS_API_KEY environment variable."
        
        try:
            briefing = "📰 Daily News Briefing\n"
            briefing += "=" * 30 + "\n\n"
            
            # Get top general headlines (2 articles)
            general = self.get_top_headlines(limit=2)
            if "News service error" not in general and "Failed to get news" not in general:
                briefing += "🌟 Top Stories:\n"
                briefing += general.split('\n', 1)[1] + "\n\n"  # Remove title line
            
            # Get business news (2 articles)
            business = self.get_business_news(limit=2)
            if "News service error" not in business and "Failed to get news" not in business:
                briefing += "💼 Business:\n"
                briefing += business.split('\n', 1)[1] + "\n\n"  # Remove title line
            
            # Get technology news (1 article)
            tech = self.get_technology_news(limit=1)
            if "News service error" not in tech and "Failed to get news" not in tech:
                briefing += "🔬 Technology:\n"
                briefing += tech.split('\n', 1)[1] + "\n"  # Remove title line
            
            return briefing.strip()
            
        except Exception as e:
            logger.error(f"Daily briefing error: {e}")
            return f"Error generating daily briefing: {str(e)}"
    
    def _format_headlines(self, articles: List[Dict[str, Any]], title: str) -> str:
        """Format news articles for display"""
        if not articles:
            return f"{title}\n\nNo articles found."
        
        result = f"📰 {title}\n"
        result += "=" * len(title) + "\n\n"
        
        for i, article in enumerate(articles, 1):
            headline = article.get('title', 'No title')
            source = article.get('source', {}).get('name', 'Unknown source')
            published = article.get('publishedAt', '')
            description = article.get('description', '')
            
            # Format publication date
            try:
                if published:
                    pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    time_ago = self._time_ago(pub_date)
                    published_str = f" ({time_ago})"
                else:
                    published_str = ""
            except:
                published_str = ""
            
            result += f"{i}. {headline}\n"
            result += f"   📡 {source}{published_str}\n"
            
            if description and len(description.strip()) > 0:
                # Truncate description if too long
                desc = description.strip()
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                result += f"   📄 {desc}\n"
            
            result += "\n"
        
        return result.strip()
    
    def _time_ago(self, published_date: datetime) -> str:
        """Calculate time ago string"""
        now = datetime.now(published_date.tzinfo)
        diff = now - published_date
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"


# Global news service instance
news_service = NewsService()