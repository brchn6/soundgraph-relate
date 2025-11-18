# src/sgr/io/soundcloud_client.py
from __future__ import annotations
import os
import time
from typing import Tuple, Dict, Any, Optional, List, Union
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from ratelimit import limits, sleep_and_retry
from dotenv import load_dotenv, set_key

# Load environment variables from .env file
load_dotenv()

DEFAULT_BASE = "https://api.soundcloud.com"


class SoundCloudError(Exception):
    """Custom exception for SoundCloud API errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"SoundCloudError: {self.message}"


def _env(key: str, default: Optional[str] = None) -> str:
    """
    Fetches an environment variable value.

    Args:
        key (str): The environment variable to fetch.
        default (Optional[str], optional): A default value to return if the variable is not found. Defaults to None.

    Raises:
        SoundCloudError: If the environment variable is missing and no default is provided.

    Returns:
        str: The environment variable value.
    """
    val = os.getenv(key, default)
    if val is None:
        raise SoundCloudError(f"Missing env var: {key}")
    return val


Json = Union[Dict[str, Any], List[Dict[str, Any]]]


class SCClient:
    def __init__(self, client_id: str | None = None, base_url: str = DEFAULT_BASE,
                 user_agent: str = "sgr/0.1", access_token: str | None = None,
                 refresh_token: str | None = None, client_secret: str | None = None):
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_secret = client_secret
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if self.access_token:
            self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

    def refresh_access_token(self) -> bool:
        """
        Refresh the OAuth access token using the refresh token.
        
        Returns:
            bool: True if refresh was successful, False otherwise
        """
        if not all([self.refresh_token, self.client_id, self.client_secret]):
            print("Missing refresh_token, client_id, or client_secret - cannot refresh token")
            return False
            
        url = "https://secure.soundcloud.com/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json; charset=utf-8"
        }
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=20)
            
            if response.status_code == 200:
                # Save new tokens
                new_token_data = response.json()
                new_access_token = new_token_data["access_token"]
                new_refresh_token = new_token_data.get("refresh_token", self.refresh_token)
                
                # Update instance variables
                self.access_token = new_access_token
                self.refresh_token = new_refresh_token
                
                # Update session headers
                self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
                
                # Save tokens to .env file
                set_key(".env", "SOUNDCLOUD_ACCESS_TOKEN", new_access_token)
                if new_refresh_token != self.refresh_token:
                    set_key(".env", "SOUNDCLOUD_REFRESH_TOKEN", new_refresh_token)
                
                print("✅ Access token refreshed successfully!")
                return True
            else:
                print(f"❌ Error refreshing access token: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Exception during token refresh: {e}")
            return False

    def _auth_params_and_headers(self, params: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        q = dict(params or {})
        h = {}
        if self.access_token:
            # OAuth: DO NOT append client_id; header already set
            return q, h
        if not self.client_id:
            raise SoundCloudError("No SOUNDCLOUD_ACCESS_TOKEN and no SOUNDCLOUD_CLIENT_ID set")
        q["client_id"] = self.client_id
        return q, h

    @sleep_and_retry
    @limits(calls=50, period=60)
    @retry(reraise=True, stop=stop_after_attempt(5),
           wait=wait_exponential(multiplier=2, min=2, max=60),
           retry=retry_if_exception_type((requests.RequestException,)))
    def _get(self, path: str, params: Dict[str, Any]) -> Json:
        url = f"{self.base_url}/{path.lstrip('/')}"
        q, extra_headers = self._auth_params_and_headers(params)
        r = self.session.get(url, params=q, headers=extra_headers, timeout=20)
        
        # Handle 401 Unauthorized - try to refresh token once
        if r.status_code == 401 and self.access_token and self.refresh_token:
            print("🔄 Access token expired, attempting refresh...")
            if self.refresh_access_token():
                # Retry the request with refreshed token
                print("🔄 Retrying request with refreshed token...")
                q, extra_headers = self._auth_params_and_headers(params)
                r = self.session.get(url, params=q, headers=extra_headers, timeout=20)
            else:
                print("❌ Token refresh failed")
        
        if r.status_code in (401, 403):
            # Helpful message when auth mode is wrong
            raise requests.RequestException(f"{r.status_code} Unauthorized/Forbidden for {url} – "
                                            f"checked headers={'Authorization' in self.session.headers}, "
                                            f"client_id_present={'client_id' in q}")
        if r.status_code == 429:
            time.sleep(60)
            raise requests.RequestException("429 Too Many Requests")
        r.raise_for_status()
        return r.json()

    # --- v1 search (works with Bearer in your env) ---
    def search_tracks(self, q: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        # v1 endpoint: https://api.soundcloud.com/tracks
        return self._get("/tracks", {"q": q, "limit": limit, "offset": offset})

    # --- v2 search (try only if needed) ---
    def search_tracks_v2(self, q: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        # Endpoint path is /search/tracks on api-v2; on v1 it often 403's
        return self._get("/search/tracks", {"q": q, "limit": limit, "offset": offset})

    def resolve(self, url: str) -> Dict[str, Any]:
        """Resolve a SoundCloud URL to get track/playlist/user info."""
        return self._get("/resolve", {"url": url})

    def user_playlists(self, user_id: int, limit: int = 50, offset: int = 0):
        """Get a user's playlists."""
        return self._get(f"/users/{user_id}/playlists", {"limit": limit, "offset": offset})

    #  user and track endpoints
    def track_favoriters(self, track_id: int, limit: int = 50, offset: int = 0):
        # In some environments this is /tracks/{id}/favoriters or /likes
        try:
            return self._get(f"/tracks/{track_id}/favoriters", {"limit": limit, "offset": offset})
        except Exception:
            try:
                return self._get(f"/tracks/{track_id}/likes", {"limit": limit, "offset": offset})
            except Exception:
                return []

    def track_reposters(self, track_id: int, limit: int = 50, offset: int = 0):
        try:
            return self._get(f"/tracks/{track_id}/reposters", {"limit": limit, "offset": offset})
        except Exception:
            return []

    def user_likes(self, user_id: int, limit: int = 50, offset: int = 0):
        try:
            return self._get(f"/users/{user_id}/favorites", {"limit": limit, "offset": offset})
        except Exception:
            try:
                return self._get(f"/users/{user_id}/likes", {"limit": limit, "offset": offset})
            except Exception:
                return []


def make_client_from_env() -> SCClient:
    """Create a SoundCloud client from environment variables with auto-refresh capability."""
    client_id = os.getenv("SOUNDCLOUD_CLIENT_ID")
    access_token = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")  # preferred
    refresh_token = os.getenv("SOUNDCLOUD_REFRESH_TOKEN")
    client_secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET")
    base = os.getenv("SC_BASE_URL", DEFAULT_BASE)        # default to https://api.soundcloud.com
    ua = os.getenv("SC_USER_AGENT", "sgr/0.1")
    
    return SCClient(
        client_id=client_id, 
        base_url=base, 
        user_agent=ua, 
        access_token=access_token,
        refresh_token=refresh_token,
        client_secret=client_secret
    )


# At the bottom of the file, add this test snippet
if __name__ == "__main__":
    print("🔍 SoundGraph Environment Check")
    print("=" * 40)
    print("SoundCloud Client ID:", "✅" if os.getenv("SOUNDCLOUD_CLIENT_ID") else "❌")
    print("SoundCloud Access Token:", "✅" if os.getenv("SOUNDCLOUD_ACCESS_TOKEN") else "❌")
    print("SoundCloud Refresh Token:", "✅" if os.getenv("SOUNDCLOUD_REFRESH_TOKEN") else "❌")
    print("SoundCloud Client Secret:", "✅" if os.getenv("SOUNDCLOUD_CLIENT_SECRET") else "❌")
    print("Postgres Host:", os.getenv("PGHOST", "❌ Not set"))
    print("Postgres User:", os.getenv("PGUSER", "❌ Not set"))
    print("Sample Query:", os.getenv("SAMPLE_QUERY", "lofi"))
    print("=" * 40)

    # Test the client by searching for tracks
    try:
        client = make_client_from_env()
        print("🧪 Testing SoundCloud API...")
        
        # Fetch the top 5 tracks with the query "lofi"
        tracks = client.search_tracks("lofi", limit=5)
        
        print(f"✅ Successfully fetched {len(tracks)} tracks!")
        print("\n📋 Sample Results:")
        print("-" * 40)
        
        # Print out the results
        for i, track in enumerate(tracks[:3], 1):
            print(f"{i}. {track['title']}")
            print(f"   ID: {track['id']}")
            
            # Handle playback_count formatting safely
            plays = track.get('playback_count')
            if plays is not None:
                print(f"   Plays: {plays:,}")
            else:
                print(f"   Plays: N/A")
                
            print(f"   Artist: {track.get('user', {}).get('username', 'Unknown')}")
            print("-" * 40)
            
    except Exception as e:
        print(f"❌ Error testing SoundCloud API: {e}")
        print("\n💡 Try running: make refresh_and_request")
        print("   This will refresh your OAuth token.")