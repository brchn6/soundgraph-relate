"""
SQLite-based cache for track metadata and relationships.

This cache stores track information and related tracks to minimize API calls
and enable offline graph exploration.
"""

from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger


class TrackCache:
    """
    SQLite-based cache for track metadata and relationships.
    
    Stores:
    - Track metadata (title, artist, genre, etc.)
    - Related tracks (from playlists, co-occurrence, etc.)
    - User data
    - Playlist information
    """
    
    def __init__(self, cache_path: str | Path = "data/cache/tracks.db"):
        """
        Initialize the track cache.
        
        Args:
            cache_path: Path to the SQLite database file
        """
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.cache_path))
        self.conn.row_factory = sqlite3.Row  # Return rows as dicts
        self._create_schema()
        
    def _create_schema(self):
        """Create the cache database schema."""
        cursor = self.conn.cursor()
        
        # Tracks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                track_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                artist_id INTEGER,
                artist_name TEXT,
                genre TEXT,
                tags TEXT,  -- JSON array
                duration_ms INTEGER,
                playback_count INTEGER,
                like_count INTEGER,
                permalink_url TEXT,
                raw_json TEXT,  -- Full API response
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                permalink_url TEXT,
                followers_count INTEGER,
                raw_json TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Playlists table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                playlist_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                creator_user_id INTEGER,
                track_count INTEGER,
                permalink_url TEXT,
                raw_json TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Playlist tracks (which tracks are in which playlists)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                position INTEGER,
                PRIMARY KEY (playlist_id, track_id),
                FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id),
                FOREIGN KEY (track_id) REFERENCES tracks(track_id)
            )
        """)
        
        # Related tracks (co-occurrence, similar tracks, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS related_tracks (
                src_track_id INTEGER NOT NULL,
                dst_track_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,  -- 'co_playlist', 'similar', 'artist', etc.
                weight REAL DEFAULT 1.0,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (src_track_id, dst_track_id, relation_type),
                FOREIGN KEY (src_track_id) REFERENCES tracks(track_id),
                FOREIGN KEY (dst_track_id) REFERENCES tracks(track_id)
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks(track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_src ON related_tracks(src_track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_dst ON related_tracks(dst_track_id)")
        
        self.conn.commit()
    
    def cache_track(self, track_data: Dict[str, Any]) -> int:
        """
        Cache a track's metadata.
        
        Args:
            track_data: Track data from SoundCloud API
            
        Returns:
            track_id: The ID of the cached track
        """
        track_id = track_data.get("id")
        if not track_id:
            raise ValueError("Track data must contain 'id' field")
        
        user = track_data.get("user") or {}
        artist_id = user.get("id")
        artist_name = user.get("username", "Unknown")
        
        tags = track_data.get("tag_list", "")
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        elif isinstance(tags, str):
            tags_json = json.dumps([t.strip() for t in tags.split() if t.strip()])
        else:
            tags_json = json.dumps([])
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tracks (
                track_id, title, artist_id, artist_name, genre, tags,
                duration_ms, playback_count, like_count, permalink_url,
                raw_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            track_id,
            track_data.get("title", "Untitled"),
            artist_id,
            artist_name,
            track_data.get("genre"),
            tags_json,
            track_data.get("duration"),
            track_data.get("playback_count", 0),
            track_data.get("likes_count", 0) or track_data.get("favoritings_count", 0),
            track_data.get("permalink_url"),
            json.dumps(track_data)
        ))
        self.conn.commit()
        
        logger.debug(f"Cached track {track_id}: {track_data.get('title')}")
        return track_id
    
    def get_track(self, track_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a track from the cache.
        
        Args:
            track_id: The track ID to retrieve
            
        Returns:
            Track data dict or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tracks WHERE track_id = ?", (track_id,))
        row = cursor.fetchone()
        
        if row:
            track = dict(row)
            # Parse JSON fields
            if track.get("tags"):
                track["tags"] = json.loads(track["tags"])
            if track.get("raw_json"):
                track["raw_data"] = json.loads(track["raw_json"])
            return track
        return None
    
    def cache_user(self, user_data: Dict[str, Any]) -> int:
        """Cache a user's metadata."""
        user_id = user_data.get("id")
        if not user_id:
            raise ValueError("User data must contain 'id' field")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users (
                user_id, username, permalink_url, followers_count, raw_json
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            user_data.get("username", "Unknown"),
            user_data.get("permalink_url"),
            user_data.get("followers_count", 0),
            json.dumps(user_data)
        ))
        self.conn.commit()
        return user_id
    
    def cache_playlist(self, playlist_data: Dict[str, Any]) -> int:
        """Cache a playlist's metadata."""
        playlist_id = playlist_data.get("id")
        if not playlist_id:
            raise ValueError("Playlist data must contain 'id' field")
        
        user = playlist_data.get("user") or {}
        creator_id = user.get("id")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO playlists (
                playlist_id, title, creator_user_id, track_count, permalink_url, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            playlist_id,
            playlist_data.get("title", "Untitled"),
            creator_id,
            playlist_data.get("track_count", 0),
            playlist_data.get("permalink_url"),
            json.dumps(playlist_data)
        ))
        self.conn.commit()
        return playlist_id
    
    def cache_playlist_tracks(self, playlist_id: int, tracks: List[Dict[str, Any]]):
        """
        Cache the tracks in a playlist.
        
        Args:
            playlist_id: The playlist ID
            tracks: List of track data dicts (must have 'id' field)
        """
        cursor = self.conn.cursor()
        for position, track in enumerate(tracks):
            track_id = track.get("id")
            if not track_id:
                continue
            
            # Cache the track itself
            self.cache_track(track)
            
            # Link it to the playlist
            cursor.execute("""
                INSERT OR REPLACE INTO playlist_tracks (
                    playlist_id, track_id, position
                ) VALUES (?, ?, ?)
            """, (playlist_id, track_id, position))
        
        self.conn.commit()
    
    def add_related_track(self, src_track_id: int, dst_track_id: int, 
                         relation_type: str = "co_playlist", weight: float = 1.0):
        """
        Add a relationship between two tracks.
        
        Args:
            src_track_id: Source track ID
            dst_track_id: Destination track ID
            relation_type: Type of relationship (co_playlist, similar, artist, etc.)
            weight: Strength of the relationship
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO related_tracks (
                src_track_id, dst_track_id, relation_type, weight
            ) VALUES (?, ?, ?, ?)
        """, (src_track_id, dst_track_id, relation_type, weight))
        self.conn.commit()
    
    def get_related_tracks(self, track_id: int, relation_type: Optional[str] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get tracks related to a given track.
        
        Args:
            track_id: The source track ID
            relation_type: Filter by relation type (None for all types)
            limit: Maximum number of results
            
        Returns:
            List of related track dicts with metadata
        """
        cursor = self.conn.cursor()
        
        if relation_type:
            cursor.execute("""
                SELECT t.*, rt.relation_type, rt.weight
                FROM related_tracks rt
                JOIN tracks t ON rt.dst_track_id = t.track_id
                WHERE rt.src_track_id = ? AND rt.relation_type = ?
                ORDER BY rt.weight DESC
                LIMIT ?
            """, (track_id, relation_type, limit))
        else:
            cursor.execute("""
                SELECT t.*, rt.relation_type, rt.weight
                FROM related_tracks rt
                JOIN tracks t ON rt.dst_track_id = t.track_id
                WHERE rt.src_track_id = ?
                ORDER BY rt.weight DESC
                LIMIT ?
            """, (track_id, limit))
        
        results = []
        for row in cursor.fetchall():
            track = dict(row)
            if track.get("tags"):
                track["tags"] = json.loads(track["tags"])
            results.append(track)
        
        return results
    
    def get_tracks_by_artist(self, artist_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all cached tracks by an artist."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM tracks WHERE artist_id = ? LIMIT ?
        """, (artist_id, limit))
        
        results = []
        for row in cursor.fetchall():
            track = dict(row)
            if track.get("tags"):
                track["tags"] = json.loads(track["tags"])
            results.append(track)
        
        return results
    
    def is_track_cached(self, track_id: int, max_age_hours: int = 24) -> bool:
        """
        Check if a track is cached and fresh.
        
        Args:
            track_id: The track ID to check
            max_age_hours: Maximum age in hours (0 = ignore age)
            
        Returns:
            True if track is cached and fresh
        """
        cursor = self.conn.cursor()
        
        if max_age_hours > 0:
            cursor.execute("""
                SELECT 1 FROM tracks 
                WHERE track_id = ? 
                AND datetime(updated_at) > datetime('now', '-' || ? || ' hours')
            """, (track_id, max_age_hours))
        else:
            cursor.execute("SELECT 1 FROM tracks WHERE track_id = ?", (track_id,))
        
        return cursor.fetchone() is not None
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about the cache."""
        cursor = self.conn.cursor()
        
        stats = {}
        cursor.execute("SELECT COUNT(*) as count FROM tracks")
        stats["tracks"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM users")
        stats["users"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM playlists")
        stats["playlists"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM related_tracks")
        stats["relationships"] = cursor.fetchone()["count"]
        
        return stats
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
