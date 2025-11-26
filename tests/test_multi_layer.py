"""
Tests for multi-layer relationship collection system.

Tests the 4 layers of relationships:
- Layer 1: Track-to-Track (playlist co-occurrence) - existing
- Layer 2: User-to-Track (likes, reposts, plays)
- Layer 3: User-to-User (taste similarity, follows)
- Layer 4: Artist-to-Artist (collaborations, co-follow networks)
"""

import tempfile
import shutil
from pathlib import Path
import pytest

from sgr.cache.track_cache import TrackCache


class TestMultiLayerSchema:
    """Test the enhanced database schema for multi-layer relationships."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
    
    def teardown_method(self):
        """Clean up temporary cache."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_schema_includes_new_tables(self):
        """Test that new multi-layer tables are created."""
        cursor = self.cache.conn.cursor()
        
        # Check for new tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        assert "user_engagements" in tables
        assert "user_similarity" in tables
        assert "artist_relationships" in tables
        assert "user_follows" in tables
    
    def test_cache_stats_includes_multi_layer(self):
        """Test that cache stats include multi-layer counts."""
        stats = self.cache.get_cache_stats()
        
        assert "user_engagements" in stats
        assert "user_similarities" in stats
        assert "artist_relationships" in stats
        assert "user_follows" in stats
        
        # All should be 0 initially
        assert stats["user_engagements"] == 0
        assert stats["user_similarities"] == 0
        assert stats["artist_relationships"] == 0
        assert stats["user_follows"] == 0


class TestLayer2UserEngagement:
    """Test Layer 2: User engagement functionality."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
        
        # Create test data
        self.user1 = {"id": 1001, "username": "user1", "followers_count": 100}
        self.user2 = {"id": 1002, "username": "user2", "followers_count": 200}
        self.track1 = {"id": 2001, "title": "Track 1", "user": {"id": 3001, "username": "artist1"}}
        self.track2 = {"id": 2002, "title": "Track 2", "user": {"id": 3002, "username": "artist2"}}
        
        # Cache users and tracks
        self.cache.cache_user(self.user1)
        self.cache.cache_user(self.user2)
        self.cache.cache_track(self.track1)
        self.cache.cache_track(self.track2)
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_user_engagement_like(self):
        """Test adding a like engagement."""
        self.cache.add_user_engagement(1001, 2001, "like")
        
        stats = self.cache.get_cache_stats()
        assert stats["user_engagements"] == 1
    
    def test_add_user_engagement_repost(self):
        """Test adding a repost engagement."""
        self.cache.add_user_engagement(1001, 2001, "repost")
        
        stats = self.cache.get_cache_stats()
        assert stats["user_engagements"] == 1
    
    def test_get_track_engagers(self):
        """Test retrieving users who engaged with a track."""
        # Add engagements
        self.cache.add_user_engagement(1001, 2001, "like")
        self.cache.add_user_engagement(1002, 2001, "like")
        
        # Get engagers
        engagers = self.cache.get_track_engagers(2001, engagement_type="like")
        
        assert len(engagers) == 2
        user_ids = {e["user_id"] for e in engagers}
        assert user_ids == {1001, 1002}
    
    def test_get_user_liked_tracks(self):
        """Test retrieving tracks liked by a user."""
        # Add likes
        self.cache.add_user_engagement(1001, 2001, "like")
        self.cache.add_user_engagement(1001, 2002, "like")
        
        # Get liked tracks
        liked = self.cache.get_user_liked_tracks(1001)
        
        assert len(liked) == 2
        track_ids = {t["track_id"] for t in liked}
        assert track_ids == {2001, 2002}
    
    def test_engagement_types_separate(self):
        """Test that different engagement types are tracked separately."""
        # Add both like and repost for same user/track
        self.cache.add_user_engagement(1001, 2001, "like")
        self.cache.add_user_engagement(1001, 2001, "repost")
        
        # Should have 2 engagements
        stats = self.cache.get_cache_stats()
        assert stats["user_engagements"] == 2
        
        # Get by type
        likers = self.cache.get_track_engagers(2001, engagement_type="like")
        reposters = self.cache.get_track_engagers(2001, engagement_type="repost")
        
        assert len(likers) == 1
        assert len(reposters) == 1


class TestLayer3UserSimilarity:
    """Test Layer 3: User similarity functionality."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
        
        # Create test users
        self.cache.cache_user({"id": 1001, "username": "user1"})
        self.cache.cache_user({"id": 1002, "username": "user2"})
        self.cache.cache_user({"id": 1003, "username": "user3"})
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_user_similarity(self):
        """Test adding user similarity."""
        self.cache.add_user_similarity(
            1001, 1002, "jaccard_likes", 0.75,
            common_tracks=15, total_tracks_a=20, total_tracks_b=25
        )
        
        stats = self.cache.get_cache_stats()
        assert stats["user_similarities"] == 1
    
    def test_canonical_ordering(self):
        """Test that user pairs are stored in canonical order (smaller ID first)."""
        # Add with reversed order
        self.cache.add_user_similarity(1002, 1001, "jaccard_likes", 0.75)
        
        # Should still be stored as (1001, 1002)
        cursor = self.cache.conn.cursor()
        cursor.execute("SELECT user_id_a, user_id_b FROM user_similarity")
        row = cursor.fetchone()
        
        assert row["user_id_a"] == 1001
        assert row["user_id_b"] == 1002
    
    def test_get_similar_users(self):
        """Test retrieving similar users."""
        # Add similarities
        self.cache.add_user_similarity(1001, 1002, "jaccard_likes", 0.75, common_tracks=15)
        self.cache.add_user_similarity(1001, 1003, "jaccard_likes", 0.50, common_tracks=10)
        
        # Get similar users for user 1001
        similar = self.cache.get_similar_users(1001, min_score=0.4)
        
        assert len(similar) == 2
        # Should be ordered by score descending
        assert similar[0]["similarity_score"] == 0.75
        assert similar[1]["similarity_score"] == 0.50
    
    def test_filter_by_similarity_type(self):
        """Test filtering similar users by type."""
        self.cache.add_user_similarity(1001, 1002, "jaccard_likes", 0.75)
        self.cache.add_user_similarity(1001, 1003, "follow", 1.0)
        
        # Get only jaccard similarities
        similar = self.cache.get_similar_users(1001, similarity_type="jaccard_likes")
        
        assert len(similar) == 1
        assert similar[0]["similarity_type"] == "jaccard_likes"
    
    def test_add_user_follow(self):
        """Test adding user follow relationships."""
        self.cache.add_user_follow(1001, 1002)
        
        stats = self.cache.get_cache_stats()
        assert stats["user_follows"] == 1


class TestLayer4ArtistRelationships:
    """Test Layer 4: Artist relationship functionality."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
        
        # Create test users (artists)
        self.cache.cache_user({"id": 3001, "username": "artist1"})
        self.cache.cache_user({"id": 3002, "username": "artist2"})
        self.cache.cache_user({"id": 3003, "username": "artist3"})
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_artist_relationship(self):
        """Test adding artist relationships."""
        self.cache.add_artist_relationship(
            3001, 3002, "collaboration", strength=0.9,
            evidence_count=5, metadata={"tracks": ["track1", "track2"]}
        )
        
        stats = self.cache.get_cache_stats()
        assert stats["artist_relationships"] == 1
    
    def test_canonical_ordering(self):
        """Test that artist pairs are stored in canonical order."""
        # Add with reversed order
        self.cache.add_artist_relationship(3002, 3001, "collaboration", strength=0.9)
        
        # Should be stored as (3001, 3002)
        cursor = self.cache.conn.cursor()
        cursor.execute("SELECT artist_id_a, artist_id_b FROM artist_relationships")
        row = cursor.fetchone()
        
        assert row["artist_id_a"] == 3001
        assert row["artist_id_b"] == 3002
    
    def test_get_related_artists(self):
        """Test retrieving related artists."""
        # Add relationships
        self.cache.add_artist_relationship(3001, 3002, "collaboration", strength=0.9, evidence_count=5)
        self.cache.add_artist_relationship(3001, 3003, "co_library", strength=0.6, evidence_count=3)
        
        # Get related artists for artist 3001
        related = self.cache.get_related_artists(3001, min_strength=0.5)
        
        assert len(related) == 2
        # Should be ordered by strength descending
        assert related[0]["strength"] == 0.9
        assert related[1]["strength"] == 0.6
    
    def test_filter_by_relationship_type(self):
        """Test filtering by relationship type."""
        self.cache.add_artist_relationship(3001, 3002, "collaboration", strength=0.9)
        self.cache.add_artist_relationship(3001, 3003, "co_library", strength=0.6)
        
        # Get only collaborations
        related = self.cache.get_related_artists(3001, relationship_type="collaboration")
        
        assert len(related) == 1
        assert related[0]["relationship_type"] == "collaboration"
    
    def test_metadata_serialization(self):
        """Test that metadata is properly serialized and deserialized."""
        metadata = {"tracks": ["track1", "track2"], "source": "api"}
        self.cache.add_artist_relationship(
            3001, 3002, "collaboration", strength=0.9,
            metadata=metadata
        )
        
        # Retrieve and check metadata
        related = self.cache.get_related_artists(3001)
        assert len(related) == 1
        assert related[0]["metadata"] == metadata


class TestBackwardCompatibility:
    """Test that new features don't break existing functionality."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_existing_track_caching_works(self):
        """Test that existing track caching still works."""
        track_data = {
            "id": 12345,
            "title": "Test Track",
            "user": {"id": 67890, "username": "TestArtist"},
            "genre": "Electronic",
        }
        
        track_id = self.cache.cache_track(track_data)
        assert track_id == 12345
        
        cached = self.cache.get_track(12345)
        assert cached is not None
        assert cached["title"] == "Test Track"
    
    def test_existing_related_tracks_works(self):
        """Test that existing related tracks functionality works."""
        track1 = {"id": 111, "title": "Track 1", "user": {"id": 1, "username": "A"}}
        track2 = {"id": 222, "title": "Track 2", "user": {"id": 2, "username": "B"}}
        
        self.cache.cache_track(track1)
        self.cache.cache_track(track2)
        
        # Add Layer 1 relationship (playlist co-occurrence)
        self.cache.add_related_track(111, 222, "co_playlist", 0.8)
        
        # Verify it still works
        related = self.cache.get_related_tracks(111)
        assert len(related) == 1
        assert related[0]["track_id"] == 222
    
    def test_cache_stats_backward_compatible(self):
        """Test that cache stats still has original fields."""
        stats = self.cache.get_cache_stats()
        
        # Original fields should still exist
        assert "tracks" in stats
        assert "users" in stats
        assert "playlists" in stats
        assert "relationships" in stats


if __name__ == "__main__":
    # Run tests
    import sys
    pytest.main([__file__, "-v"] + sys.argv[1:])
