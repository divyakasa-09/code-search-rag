
import asyncio
import httpx
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class RateLimiter:
    def __init__(self, calls_per_hour: int = 5000):
        self.calls_per_hour = calls_per_hour
        self.calls = []
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        async with self.lock:
            now = datetime.now()
            # Remove calls older than 1 hour
            self.calls = [call_time for call_time in self.calls 
                         if now - call_time < timedelta(hours=1)]
            
            if len(self.calls) >= self.calls_per_hour:
                oldest_call = self.calls[0]
                sleep_time = 3600 - (now - oldest_call).total_seconds()
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)
            
            self.calls.append(now)

class GitHubService:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {settings.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.rate_limiter = RateLimiter()
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    
    async def _make_request(self, url: str, method: str = "GET", **kwargs) -> Dict:
        """Make a rate-limited request to GitHub API with retries."""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                await self.rate_limiter.acquire()
                response = await self.client.request(
                    method,
                    url,
                    headers=self.headers,
                    **kwargs
                )
                
                if response.status_code == 403 and "rate limit exceeded" in response.text.lower():
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    wait_time = max(reset_time - datetime.now().timestamp(), 0)
                    logger.warning(f"Rate limit exceeded. Waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise ValueError(f"Repository or resource not found: {url}")
                if attempt == max_retries - 1:
                    raise
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                
            await asyncio.sleep(retry_delay * (2 ** attempt))
        
        raise RuntimeError("Maximum retries exceeded")
    
    async def validate_repository(self, owner: str, repo: str) -> bool:
        """Validate if repository exists and is accessible."""
        try:
            await self._make_request(f"{self.base_url}/repos/{owner}/{repo}")
            return True
        except (ValueError, Exception):
            return False
    
    async def get_repository_content(self, owner: str, repo: str, path: str = "") -> List[Dict]:
        """Get repository contents with proper error handling."""
        return await self._make_request(
            f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        )
    
    async def get_file_content(self, file_url: str) -> Optional[str]:
        """Get file content from GitHub."""
        try:
            response = await self._make_request(file_url)
            return response.get('content')
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return None
    
    async def get_repository_tree(self, owner: str, repo: str) -> List[Dict]:
        """Get complete repository tree using Git Tree API."""
        # Get the default branch's latest commit
        repo_info = await self._make_request(
            f"{self.base_url}/repos/{owner}/{repo}"
        )
        default_branch = repo_info['default_branch']
        
        # Get the tree
        tree_url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        tree_data = await self._make_request(tree_url)
        
        return [
            {
                'path': item['path'],
                'url': item['url'],
                'type': item['type']
            }
            for item in tree_data.get('tree', [])
            if item['type'] == 'blob'  # Only return files, not directories
        ]
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()