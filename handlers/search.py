"""
Web search functionality for the WhatsApp Assistant

Provides internet search capabilities to make the assistant smarter
"""

import os
import logging
import requests
from typing import Optional, List, Dict
import json

logger = logging.getLogger(__name__)

class WebSearchService:
    """Web search service using multiple providers"""
    
    def __init__(self):
        self.serpapi_key = os.getenv('SERPAPI_API_KEY')
        self.bing_key = os.getenv('BING_SEARCH_KEY')
        self.google_cse_key = os.getenv('GOOGLE_CSE_KEY')
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
    
    def is_configured(self) -> bool:
        """Check if any search provider is configured"""
        return any([self.serpapi_key, self.bing_key, 
                   (self.google_cse_key and self.google_cse_id)])
    
    def search(self, query: str, num_results: int = 5) -> Dict:
        """Search the web using available providers"""
        if not self.is_configured():
            return {
                "success": False,
                "error": "No search provider configured",
                "results": []
            }
        
        # Try providers in order of preference
        providers = [
            ('SerpAPI', self._search_serpapi),
            ('Bing', self._search_bing),
            ('Google CSE', self._search_google_cse)
        ]
        
        for provider_name, search_func in providers:
            try:
                if provider_name == 'SerpAPI' and not self.serpapi_key:
                    continue
                elif provider_name == 'Bing' and not self.bing_key:
                    continue
                elif provider_name == 'Google CSE' and not (self.google_cse_key and self.google_cse_id):
                    continue
                
                logger.info(f"Searching with {provider_name}: {query}")
                result = search_func(query, num_results)
                
                if result.get("success"):
                    result["provider"] = provider_name
                    return result
                    
            except Exception as e:
                logger.warning(f"{provider_name} search failed: {e}")
                continue
        
        return {
            "success": False,
            "error": "All search providers failed",
            "results": []
        }
    
    def _search_serpapi(self, query: str, num_results: int) -> Dict:
        """Search using SerpAPI (Google Search)"""
        if not self.serpapi_key:
            return {"success": False, "error": "SerpAPI key not configured"}
        
        url = "https://serpapi.com/search.json"
        params = {
            'q': query,
            'api_key': self.serpapi_key,
            'num': num_results,
            'safe': 'active'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('organic_results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'source': item.get('displayed_link', '')
            })
        
        return {
            "success": True,
            "results": results,
            "query": query
        }
    
    def _search_bing(self, query: str, num_results: int) -> Dict:
        """Search using Bing Search API"""
        if not self.bing_key:
            return {"success": False, "error": "Bing search key not configured"}
        
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {'Ocp-Apim-Subscription-Key': self.bing_key}
        params = {
            'q': query,
            'count': num_results,
            'safeSearch': 'Moderate'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('webPages', {}).get('value', []):
            results.append({
                'title': item.get('name', ''),
                'url': item.get('url', ''),
                'snippet': item.get('snippet', ''),
                'source': item.get('displayUrl', '')
            })
        
        return {
            "success": True,
            "results": results,
            "query": query
        }
    
    def _search_google_cse(self, query: str, num_results: int) -> Dict:
        """Search using Google Custom Search Engine"""
        if not (self.google_cse_key and self.google_cse_id):
            return {"success": False, "error": "Google CSE not configured"}
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': self.google_cse_key,
            'cx': self.google_cse_id,
            'q': query,
            'num': num_results,
            'safe': 'active'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('items', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'source': item.get('displayLink', '')
            })
        
        return {
            "success": True,
            "results": results,
            "query": query
        }
    
    def search_and_summarize(self, query: str, num_results: int = 3) -> str:
        """Search the web and return a formatted summary"""
        try:
            search_result = self.search(query, num_results)
            
            if not search_result.get("success"):
                return f"🔍 Unable to search the web: {search_result.get('error', 'Unknown error')}"
            
            results = search_result.get("results", [])
            if not results:
                return f"🔍 No results found for: {query}"
            
            # Format the results
            summary_parts = [f"🔍 Web Search Results for: {query}\n"]
            
            for i, result in enumerate(results, 1):
                title = result.get('title', 'No title')
                snippet = result.get('snippet', 'No description')
                source = result.get('source', result.get('url', ''))
                
                summary_parts.append(f"{i}. **{title}**")
                summary_parts.append(f"   {snippet}")
                summary_parts.append(f"   📎 {source}")
                summary_parts.append("")
            
            provider = search_result.get("provider", "Web")
            summary_parts.append(f"_Source: {provider} Search_")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Search and summarize error: {e}")
            return f"🔍 Search error: {str(e)}"

# Global instance
web_search = WebSearchService()