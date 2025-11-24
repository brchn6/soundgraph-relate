"""
Smart expansion logic for building personal music graphs.

This module implements intelligent strategies for expanding a music graph
from a seed track, using heuristics to prioritize interesting connections.
"""

from __future__ import annotations
import time
from typing import Dict, Any, List, Set, Optional
from collections import deque
from loguru import logger

from sgr.io.soundcloud_client import SCClient
from sgr.cache.track_cache import TrackCache


class SmartExpander:
    """
    Smart expansion engine for building personal music graphs.
    
    Starting from a seed track, this expander:
    1. Fetches the artist's playlists
    2. Extracts tracks from those playlists
    3. Builds co-occurrence relationships
    4. Optionally expands to related artists
    
    Uses caching to minimize API calls and supports configurable depth limits.
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, 
                 max_playlists_per_artist: int = 20,
                 max_tracks_per_playlist: int = 100,
                 min_playback_count: int = 1000):
        """
        Initialize the smart expander.
        
        Args:
            sc_client: SoundCloud API client
            cache: Track cache instance
            max_playlists_per_artist: Max playlists to fetch per artist
            max_tracks_per_playlist: Max tracks to consider per playlist
            min_playback_count: Min playback count for tracks to include
        """
        self.sc = sc_client
        self.cache = cache
        self.max_playlists_per_artist = max_playlists_per_artist
        self.max_tracks_per_playlist = max_tracks_per_playlist
        self.min_playback_count = min_playback_count
        
    def expand_from_track(self, track_id: int, depth: int = 1, 
                         max_tracks: int = 500) -> Dict[str, Any]:
        """
        Expand the graph starting from a seed track.
        
        Args:
            track_id: The seed track ID
            depth: How many hops to expand (1 = just artist's playlists, 2 = related artists too)
            max_tracks: Maximum total tracks to collect
            
        Returns:
            Expansion results with statistics
        """
        logger.info(f"Starting expansion from track {track_id}, depth={depth}, max_tracks={max_tracks}")
        
        results = {
            "seed_track_id": track_id,
            "depth": depth,
            "tracks_collected": 0,
            "playlists_processed": 0,
            "relationships_created": 0,
            "artists_visited": set(),
            "tracks_visited": set()
        }
        
        # Queue for BFS: (track_id, current_depth)
        queue = deque([(track_id, 0)])
        visited_tracks = {track_id}
        
        while queue and results["tracks_collected"] < max_tracks:
            current_track_id, current_depth = queue.popleft()
            
            if current_depth > depth:
                continue
            
            # Get track data (from cache or API)
            track_data = self._get_track(current_track_id)
            if not track_data:
                logger.warning(f"Could not fetch track {current_track_id}")
                continue
            
            results["tracks_visited"].add(current_track_id)
            
            # Get artist info
            user = track_data.get("user") or {}
            artist_id = user.get("id")
            if not artist_id:
                continue
            
            if artist_id not in results["artists_visited"]:
                results["artists_visited"].add(artist_id)
                
                # Expand through this artist's playlists
                expansion_stats = self._expand_artist_playlists(artist_id, current_track_id)
                results["playlists_processed"] += expansion_stats["playlists_processed"]
                results["relationships_created"] += expansion_stats["relationships_created"]
                results["tracks_collected"] += expansion_stats["new_tracks"]
                
                # Add related tracks to queue if we haven't hit depth limit
                if current_depth < depth:
                    related_tracks = self.cache.get_related_tracks(
                        current_track_id, 
                        limit=10
                    )
                    for rel_track in related_tracks:
                        rel_track_id = rel_track["track_id"]
                        if rel_track_id not in visited_tracks:
                            queue.append((rel_track_id, current_depth + 1))
                            visited_tracks.add(rel_track_id)
        
        # Convert sets to counts for JSON serialization
        results["artists_visited"] = len(results["artists_visited"])
        results["tracks_visited"] = len(results["tracks_visited"])
        
        logger.success(f"Expansion complete: {results['tracks_collected']} tracks, "
                      f"{results['playlists_processed']} playlists, "
                      f"{results['relationships_created']} relationships")
        
        return results
    
    def _get_track(self, track_id: int) -> Optional[Dict[str, Any]]:
        """
        Get track data from cache or API.
        
        Args:
            track_id: The track ID
            
        Returns:
            Track data dict or None
        """
        # Check cache first
        cached = self.cache.get_track(track_id)
        if cached and cached.get("raw_data"):
            return cached["raw_data"]
        
        # Not in cache, fetch from API
        try:
            # SoundCloud API doesn't have a direct /tracks/{id} endpoint in v1
            # We'll need to use resolve with the permalink_url if we have it
            # For now, return None and handle in caller
            logger.debug(f"Track {track_id} not in cache and direct fetch not available")
            return None
        except Exception as e:
            logger.error(f"Error fetching track {track_id}: {e}")
            return None
    
    def _expand_artist_playlists(self, artist_id: int, seed_track_id: int) -> Dict[str, int]:
        """
        Expand through an artist's playlists to find related tracks.
        
        Args:
            artist_id: The artist/user ID
            seed_track_id: The original seed track
            
        Returns:
            Statistics about the expansion
        """
        stats = {
            "playlists_processed": 0,
            "new_tracks": 0,
            "relationships_created": 0
        }
        
        # Fetch artist's playlists
        playlists = self._fetch_user_playlists(artist_id)
        
        for playlist in playlists[:self.max_playlists_per_artist]:
            playlist_id = playlist.get("id")
            if not playlist_id:
                continue
            
            # Cache the playlist
            self.cache.cache_playlist(playlist)
            stats["playlists_processed"] += 1
            
            # Get tracks in this playlist
            tracks = playlist.get("tracks") or []
            if not tracks:
                continue
            
            # Cache playlist tracks
            valid_tracks = [t for t in tracks if t and t.get("id")][:self.max_tracks_per_playlist]
            self.cache.cache_playlist_tracks(playlist_id, valid_tracks)
            
            # Build co-occurrence relationships
            for i, track_a in enumerate(valid_tracks):
                track_a_id = track_a.get("id")
                if not track_a_id:
                    continue
                
                # Filter by playback count if specified
                if self.min_playback_count > 0:
                    playback = track_a.get("playback_count", 0)
                    if playback < self.min_playback_count:
                        continue
                
                stats["new_tracks"] += 1
                
                # Create relationships with other tracks in the same playlist
                for track_b in valid_tracks[i+1:]:
                    track_b_id = track_b.get("id")
                    if not track_b_id or track_b_id == track_a_id:
                        continue
                    
                    # Add bidirectional relationship
                    # Weight by inverse playlist size (smaller playlists = stronger signal)
                    weight = 1.0 / max(len(valid_tracks), 1)
                    
                    self.cache.add_related_track(track_a_id, track_b_id, "co_playlist", weight)
                    self.cache.add_related_track(track_b_id, track_a_id, "co_playlist", weight)
                    stats["relationships_created"] += 2
            
            time.sleep(0.2)  # Rate limiting
        
        return stats
    
    def _fetch_user_playlists(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Fetch a user's playlists from API.
        
        Args:
            user_id: The user/artist ID
            
        Returns:
            List of playlist dicts
        """
        playlists = []
        offset, limit = 0, 50
        
        try:
            while len(playlists) < self.max_playlists_per_artist:
                batch = self.sc.user_playlists(user_id, limit=limit, offset=offset) or []
                if not batch:
                    break
                
                playlists.extend(batch)
                
                if len(batch) < limit:
                    break
                
                offset += limit
                time.sleep(0.2)  # Rate limiting
                
        except Exception as e:
            logger.error(f"Error fetching playlists for user {user_id}: {e}")
        
        return playlists
    
    def expand_from_url(self, track_url: str, depth: int = 1, 
                       max_tracks: int = 500) -> Dict[str, Any]:
        """
        Expand the graph starting from a SoundCloud track URL.
        
        Args:
            track_url: SoundCloud track URL
            depth: How many hops to expand
            max_tracks: Maximum total tracks to collect
            
        Returns:
            Expansion results with statistics
        """
        logger.info(f"Resolving track URL: {track_url}")
        
        try:
            # Resolve the URL to get track data
            obj = self.sc.resolve(track_url)
            
            if obj.get("kind") != "track":
                raise ValueError(f"URL resolved to {obj.get('kind')}, expected 'track'")
            
            track_id = obj.get("id")
            if not track_id:
                raise ValueError("Resolved track has no ID")
            
            # Cache the seed track
            self.cache.cache_track(obj)
            
            # Cache the artist/user
            user = obj.get("user")
            if user:
                self.cache.cache_user(user)
            
            # Now expand from this track
            return self.expand_from_track(track_id, depth, max_tracks)
            
        except Exception as e:
            logger.error(f"Error expanding from URL {track_url}: {e}")
            raise
