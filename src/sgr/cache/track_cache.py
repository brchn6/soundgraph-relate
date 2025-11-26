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
import contextlib


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
        
        # Layer 2: User engagements (likes, reposts, plays)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_engagements (
                user_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                engagement_type TEXT NOT NULL,  -- 'like', 'repost', 'play'
                engagement_count INTEGER DEFAULT 1,  -- For plays
                engaged_at TIMESTAMP,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, track_id, engagement_type),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (track_id) REFERENCES tracks(track_id)
            )
        """)
        
        # Layer 3: User similarity (taste patterns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_similarity (
                user_id_a INTEGER NOT NULL,
                user_id_b INTEGER NOT NULL,
                similarity_type TEXT NOT NULL,  -- 'jaccard_likes', 'cosine_taste', 'follow'
                similarity_score REAL NOT NULL,
                common_tracks INTEGER,  -- Number of shared liked tracks
                total_tracks_a INTEGER,  -- Total liked tracks for user A
                total_tracks_b INTEGER,  -- Total liked tracks for user B
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id_a, user_id_b, similarity_type),
                FOREIGN KEY (user_id_a) REFERENCES users(user_id),
                FOREIGN KEY (user_id_b) REFERENCES users(user_id),
                CHECK (user_id_a < user_id_b)  -- Ensure canonical ordering
            )
        """)
        
        # Layer 4: Artist relationships (collaborations, co-follow networks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artist_relationships (
                artist_id_a INTEGER NOT NULL,
                artist_id_b INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,  -- 'collaboration', 'co_follow', 'co_library'
                strength REAL DEFAULT 1.0,
                evidence_count INTEGER DEFAULT 1,  -- Supporting evidence
                metadata TEXT,  -- JSON for additional data
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (artist_id_a, artist_id_b, relationship_type),
                CHECK (artist_id_a < artist_id_b)  -- Ensure canonical ordering
            )
        """)
        
        # User follows (for Layer 3 follow relationships)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_follows (
                follower_id INTEGER NOT NULL,
                followee_id INTEGER NOT NULL,
                followed_at TIMESTAMP,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (follower_id, followee_id),
                FOREIGN KEY (follower_id) REFERENCES users(user_id),
                FOREIGN KEY (followee_id) REFERENCES users(user_id)
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks(track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_src ON related_tracks(src_track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_related_dst ON related_tracks(dst_track_id)")
        
        # Layer 2 indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_engagements_user ON user_engagements(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_engagements_track ON user_engagements(track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_engagements_type ON user_engagements(engagement_type)")
        
        # Layer 3 indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_similarity_a ON user_similarity(user_id_a)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_similarity_b ON user_similarity(user_id_b)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_similarity_score ON user_similarity(similarity_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_follows_follower ON user_follows(follower_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_follows_followee ON user_follows(followee_id)")
        
        # Layer 4 indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_rel_a ON artist_relationships(artist_id_a)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_rel_b ON artist_relationships(artist_id_b)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_rel_type ON artist_relationships(relationship_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist_rel_strength ON artist_relationships(strength DESC)")
        
        self.conn.commit()
    
    @contextlib.contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        cursor = self.conn.cursor()
        try:
            yield cursor
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
    
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
        
        with self._transaction() as cursor:
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
        
        logger.debug(f"Cached track {track_id}: {track_data.get('title')}")
        return track_id
    
    def cache_tracks_batch(self, tracks_data: List[Dict[str, Any]]) -> List[int]:
        """
        Cache multiple tracks in a single transaction for better performance.
        
        Args:
            tracks_data: List of track data dicts
            
        Returns:
            List of cached track IDs
        """
        track_ids = []
        with self._transaction() as cursor:
            for track_data in tracks_data:
                track_id = track_data.get("id")
                if not track_id:
                    continue
                    
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
                track_ids.append(track_id)
        
        logger.debug(f"Cached {len(track_ids)} tracks in batch")
        return track_ids
    
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
        
        with self._transaction() as cursor:
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
        return user_id
    
    def cache_playlist(self, playlist_data: Dict[str, Any]) -> int:
        """Cache a playlist's metadata."""
        playlist_id = playlist_data.get("id")
        if not playlist_id:
            raise ValueError("Playlist data must contain 'id' field")
        
        user = playlist_data.get("user") or {}
        creator_id = user.get("id")
        
        with self._transaction() as cursor:
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
        return playlist_id
    
    def cache_playlist_tracks(self, playlist_id: int, tracks: List[Dict[str, Any]]):
        """
        Cache the tracks in a playlist.
        
        Args:
            playlist_id: The playlist ID
            tracks: List of track data dicts (must have 'id' field)
        """
        with self._transaction() as cursor:
            # Cache all tracks first
            self.cache_tracks_batch(tracks)
            
            # Then link them to the playlist
            for position, track in enumerate(tracks):
                track_id = track.get("id")
                if not track_id:
                    continue
                
                cursor.execute("""
                    INSERT OR REPLACE INTO playlist_tracks (
                        playlist_id, track_id, position
                    ) VALUES (?, ?, ?)
                """, (playlist_id, track_id, position))
    
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
        with self._transaction() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO related_tracks (
                    src_track_id, dst_track_id, relation_type, weight
                ) VALUES (?, ?, ?, ?)
            """, (src_track_id, dst_track_id, relation_type, weight))
    
    def add_related_tracks_batch(self, relationships: List[Tuple[int, int, str, float]]):
        """
        Add multiple track relationships in batch.
        
        Args:
            relationships: List of (src_track_id, dst_track_id, relation_type, weight) tuples
        """
        with self._transaction() as cursor:
            for src_id, dst_id, rel_type, weight in relationships:
                cursor.execute("""
                    INSERT OR REPLACE INTO related_tracks (
                        src_track_id, dst_track_id, relation_type, weight
                    ) VALUES (?, ?, ?, ?)
                """, (src_id, dst_id, rel_type, weight))
    
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
        
        # Multi-layer stats
        cursor.execute("SELECT COUNT(*) as count FROM user_engagements")
        stats["user_engagements"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM user_similarity")
        stats["user_similarities"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM artist_relationships")
        stats["artist_relationships"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM user_follows")
        stats["user_follows"] = cursor.fetchone()["count"]
        
        return stats
    
    # === Layer 2: User Engagement Methods ===
    
    def add_user_engagement(self, user_id: int, track_id: int, 
                           engagement_type: str, engagement_count: int = 1,
                           engaged_at: Optional[str] = None):
        """
        Add a user engagement record (like, repost, play).
        
        Args:
            user_id: User ID
            track_id: Track ID
            engagement_type: Type of engagement ('like', 'repost', 'play')
            engagement_count: Number of engagements (for plays)
            engaged_at: Timestamp of engagement
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_engagements (
                user_id, track_id, engagement_type, engagement_count, engaged_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (user_id, track_id, engagement_type, engagement_count, engaged_at))
        self.conn.commit()
    
    def get_track_engagers(self, track_id: int, engagement_type: Optional[str] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get users who engaged with a track.
        
        Args:
            track_id: Track ID
            engagement_type: Filter by engagement type (None for all)
            limit: Maximum results
            
        Returns:
            List of user dicts with engagement info
        """
        cursor = self.conn.cursor()
        
        if engagement_type:
            cursor.execute("""
                SELECT u.*, ue.engagement_type, ue.engagement_count, ue.engaged_at
                FROM user_engagements ue
                JOIN users u ON ue.user_id = u.user_id
                WHERE ue.track_id = ? AND ue.engagement_type = ?
                LIMIT ?
            """, (track_id, engagement_type, limit))
        else:
            cursor.execute("""
                SELECT u.*, ue.engagement_type, ue.engagement_count, ue.engaged_at
                FROM user_engagements ue
                JOIN users u ON ue.user_id = u.user_id
                WHERE ue.track_id = ?
                LIMIT ?
            """, (track_id, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        
        return results
    
    def get_user_liked_tracks(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get tracks liked by a user.
        
        Args:
            user_id: User ID
            limit: Maximum results
            
        Returns:
            List of track dicts
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.*, ue.engaged_at
            FROM user_engagements ue
            JOIN tracks t ON ue.track_id = t.track_id
            WHERE ue.user_id = ? AND ue.engagement_type = 'like'
            ORDER BY ue.engaged_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        results = []
        for row in cursor.fetchall():
            track = dict(row)
            if track.get("tags"):
                track["tags"] = json.loads(track["tags"])
            results.append(track)
        
        return results
    
    # === Layer 3: User Similarity Methods ===
    
    def add_user_similarity(self, user_id_a: int, user_id_b: int,
                           similarity_type: str, similarity_score: float,
                           common_tracks: int = 0, total_tracks_a: int = 0,
                           total_tracks_b: int = 0):
        """
        Add or update user similarity record.
        
        Args:
            user_id_a: First user ID (should be < user_id_b)
            user_id_b: Second user ID
            similarity_type: Type of similarity ('jaccard_likes', 'cosine_taste', 'follow')
            similarity_score: Similarity score (0.0 to 1.0)
            common_tracks: Number of shared tracks
            total_tracks_a: Total tracks for user A
            total_tracks_b: Total tracks for user B
        """
        # Ensure canonical ordering
        if user_id_a > user_id_b:
            user_id_a, user_id_b = user_id_b, user_id_a
            total_tracks_a, total_tracks_b = total_tracks_b, total_tracks_a
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_similarity (
                user_id_a, user_id_b, similarity_type, similarity_score,
                common_tracks, total_tracks_a, total_tracks_b
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id_a, user_id_b, similarity_type, similarity_score,
              common_tracks, total_tracks_a, total_tracks_b))
        self.conn.commit()
    
    def get_similar_users(self, user_id: int, similarity_type: Optional[str] = None,
                         min_score: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get users similar to a given user.
        
        Args:
            user_id: User ID
            similarity_type: Filter by similarity type
            min_score: Minimum similarity score
            limit: Maximum results
            
        Returns:
            List of similar user dicts with scores
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT 
                CASE 
                    WHEN us.user_id_a = ? THEN us.user_id_b
                    ELSE us.user_id_a
                END as similar_user_id,
                us.similarity_type,
                us.similarity_score,
                us.common_tracks,
                u.username,
                u.followers_count
            FROM user_similarity us
            JOIN users u ON (
                CASE 
                    WHEN us.user_id_a = ? THEN us.user_id_b
                    ELSE us.user_id_a
                END = u.user_id
            )
            WHERE (us.user_id_a = ? OR us.user_id_b = ?)
              AND us.similarity_score >= ?
        """
        params = [user_id, user_id, user_id, user_id, min_score]
        
        if similarity_type:
            query += " AND us.similarity_type = ?"
            params.append(similarity_type)
        
        query += " ORDER BY us.similarity_score DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        
        return results
    
    def add_user_follow(self, follower_id: int, followee_id: int, 
                       followed_at: Optional[str] = None):
        """
        Add a user follow relationship.
        
        Args:
            follower_id: User who follows
            followee_id: User being followed
            followed_at: Timestamp of follow
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_follows (
                follower_id, followee_id, followed_at
            ) VALUES (?, ?, ?)
        """, (follower_id, followee_id, followed_at))
        self.conn.commit()
    
    # === Layer 4: Artist Relationship Methods ===
    
    def add_artist_relationship(self, artist_id_a: int, artist_id_b: int,
                               relationship_type: str, strength: float = 1.0,
                               evidence_count: int = 1, metadata: Optional[Dict[str, Any]] = None):
        """
        Add or update artist relationship.
        
        Args:
            artist_id_a: First artist ID (should be < artist_id_b)
            artist_id_b: Second artist ID
            relationship_type: Type of relationship ('collaboration', 'co_follow', 'co_library')
            strength: Relationship strength
            evidence_count: Supporting evidence count
            metadata: Additional metadata as dict
        """
        # Ensure canonical ordering
        if artist_id_a > artist_id_b:
            artist_id_a, artist_id_b = artist_id_b, artist_id_a
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO artist_relationships (
                artist_id_a, artist_id_b, relationship_type, strength,
                evidence_count, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (artist_id_a, artist_id_b, relationship_type, strength,
              evidence_count, metadata_json))
        self.conn.commit()
    
    def get_related_artists(self, artist_id: int, relationship_type: Optional[str] = None,
                           min_strength: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get artists related to a given artist.
        
        Args:
            artist_id: Artist ID
            relationship_type: Filter by relationship type
            min_strength: Minimum relationship strength
            limit: Maximum results
            
        Returns:
            List of related artist dicts with relationship info
        """
        cursor = self.conn.cursor()
        
        query = """
            SELECT 
                CASE 
                    WHEN ar.artist_id_a = ? THEN ar.artist_id_b
                    ELSE ar.artist_id_a
                END as related_artist_id,
                ar.relationship_type,
                ar.strength,
                ar.evidence_count,
                ar.metadata
            FROM artist_relationships ar
            WHERE (ar.artist_id_a = ? OR ar.artist_id_b = ?)
              AND ar.strength >= ?
        """
        params = [artist_id, artist_id, artist_id, min_strength]
        
        if relationship_type:
            query += " AND ar.relationship_type = ?"
            params.append(relationship_type)
        
        query += " ORDER BY ar.strength DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])
            results.append(result)
        
        return results
    
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
