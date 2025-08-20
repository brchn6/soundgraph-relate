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
from dotenv import load_dotenv

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
                 user_agent: str = "sgr/0.1", access_token: str | None = None):
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if self.access_token:
            self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

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
    client_id = os.getenv("SOUNDCLOUD_CLIENT_ID")
    access_token = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")  # preferred
    base = os.getenv("SC_BASE_URL", DEFAULT_BASE)        # default to https://api.soundcloud.com
    ua = os.getenv("SC_USER_AGENT", "sgr/0.1")
    return SCClient(client_id=client_id, base_url=base, user_agent=ua, access_token=access_token)


# At the bottom of the file, add this test snippet
if __name__ == "__main__":
    print("SoundCloud Client ID:", os.getenv("SOUNDCLOUD_CLIENT_ID"))
    print("Postgres Host:", os.getenv("PGHOST"))
    print("Postgres User:", os.getenv("PGUSER"))
    print("Sample Query:", os.getenv("SAMPLE_QUERY"))

    print(f"Loaded Client ID: {os.getenv('SOUNDCLOUD_CLIENT_ID')}")

    # Test the client by searching for tracks
    client = make_client_from_env()

    # Fetch the top 5 tracks with the query "lofi"
    tracks = client.search_tracks("lofi", limit=5)

    # Print out the results
    for track in tracks:
        print(f"Track Title: {track['title']}")
        print(f"Track ID: {track['id']}")
        print(f"Play Count: {track['playback_count']}")
        print("-" * 40)
