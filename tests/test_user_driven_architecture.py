"""
Tests for the new user-driven architecture components.
"""

import tempfile
import shutil
from pathlib import Path
import pytest

from sgr.cache.track_cache import TrackCache
from sgr.graph.personal_graph import PersonalGraph


class TestTrackCache:
    """Tests for TrackCache."""
    
    def setup_method(self):
        """Create a temporary cache for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
    
    def teardown_method(self):
        """Clean up temporary cache."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cache_initialization(self):
        """Test that cache initializes correctly."""
        assert self.cache_path.exists()
        stats = self.cache.get_cache_stats()
        assert stats["tracks"] == 0
        assert stats["users"] == 0
        assert stats["playlists"] == 0
    
    def test_cache_track(self):
        """Test caching a track."""
        track_data = {
            "id": 12345,
            "title": "Test Track",
            "user": {"id": 67890, "username": "TestArtist"},
            "genre": "Electronic",
            "duration": 180000,
            "playback_count": 5000,
            "permalink_url": "https://soundcloud.com/test/track"
        }
        
        track_id = self.cache.cache_track(track_data)
        assert track_id == 12345
        
        # Retrieve and verify
        cached = self.cache.get_track(12345)
        assert cached is not None
        assert cached["title"] == "Test Track"
        assert cached["artist_name"] == "TestArtist"
    
    def test_cache_user(self):
        """Test caching a user."""
        user_data = {
            "id": 67890,
            "username": "TestArtist",
            "permalink_url": "https://soundcloud.com/testartist",
            "followers_count": 1000
        }
        
        user_id = self.cache.cache_user(user_data)
        assert user_id == 67890
        
        stats = self.cache.get_cache_stats()
        assert stats["users"] == 1
    
    def test_add_related_track(self):
        """Test adding relationships between tracks."""
        # Cache two tracks
        track1 = {"id": 111, "title": "Track 1", "user": {"id": 1, "username": "A"}}
        track2 = {"id": 222, "title": "Track 2", "user": {"id": 2, "username": "B"}}
        
        self.cache.cache_track(track1)
        self.cache.cache_track(track2)
        
        # Add relationship
        self.cache.add_related_track(111, 222, "co_playlist", 0.8)
        
        # Verify
        related = self.cache.get_related_tracks(111)
        assert len(related) == 1
        assert related[0]["track_id"] == 222
        assert related[0]["weight"] == 0.8
    
    def test_is_track_cached(self):
        """Test checking if a track is cached."""
        track_data = {
            "id": 999,
            "title": "Cached Track",
            "user": {"id": 1, "username": "Artist"}
        }
        
        assert not self.cache.is_track_cached(999)
        
        self.cache.cache_track(track_data)
        
        assert self.cache.is_track_cached(999)
        assert self.cache.is_track_cached(999, max_age_hours=1)


class TestPersonalGraph:
    """Tests for PersonalGraph."""
    
    def setup_method(self):
        """Create a temporary cache and graph for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
        self.graph = PersonalGraph(self.cache)
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_graph_initialization(self):
        """Test that graph initializes correctly."""
        assert self.graph.graph.number_of_nodes() == 0
        assert self.graph.graph.number_of_edges() == 0
    
    def test_build_from_seed(self):
        """Test building a graph from a seed track."""
        # Create test data
        tracks = [
            {"id": 1, "title": "Track 1", "user": {"id": 10, "username": "Artist1"}},
            {"id": 2, "title": "Track 2", "user": {"id": 20, "username": "Artist2"}},
            {"id": 3, "title": "Track 3", "user": {"id": 30, "username": "Artist3"}},
        ]
        
        # Cache tracks
        for track in tracks:
            self.cache.cache_track(track)
        
        # Create relationships
        self.cache.add_related_track(1, 2, "co_playlist", 0.9)
        self.cache.add_related_track(1, 3, "co_playlist", 0.7)
        self.cache.add_related_track(2, 3, "co_playlist", 0.5)
        
        # Build graph
        stats = self.graph.build_from_seed(1, max_depth=2)
        
        assert stats["nodes"] >= 3
        assert stats["edges"] >= 2
        assert stats["track_nodes"] >= 3
    
    def test_get_neighbors(self):
        """Test getting neighbors of a track."""
        # Create and cache tracks
        self.cache.cache_track({"id": 1, "title": "Track 1", "user": {"id": 1, "username": "A"}})
        self.cache.cache_track({"id": 2, "title": "Track 2", "user": {"id": 2, "username": "B"}})
        
        self.cache.add_related_track(1, 2, "co_playlist", 1.0)
        
        # Build graph
        self.graph.build_from_seed(1, max_depth=1)
        
        # Get neighbors
        neighbors = self.graph.get_neighbors(1)
        assert len(neighbors) > 0
        assert neighbors[0]["track_id"] == 2
    
    def test_export_and_load_json(self):
        """Test exporting and loading graph from JSON."""
        # Create simple graph
        self.cache.cache_track({"id": 1, "title": "Track 1", "user": {"id": 1, "username": "A"}})
        self.cache.cache_track({"id": 2, "title": "Track 2", "user": {"id": 2, "username": "B"}})
        self.cache.add_related_track(1, 2, "co_playlist", 1.0)
        
        self.graph.build_from_seed(1, max_depth=1)
        
        # Export
        json_path = Path(self.temp_dir) / "graph.json"
        self.graph.export_to_json(json_path)
        
        assert json_path.exists()
        
        # Load into new graph
        new_graph = PersonalGraph(self.cache)
        new_graph.load_from_json(json_path)
        
        assert new_graph.graph.number_of_nodes() == self.graph.graph.number_of_nodes()
        assert new_graph.graph.number_of_edges() == self.graph.graph.number_of_edges()


if __name__ == "__main__":
    # Run tests
    import sys
    pytest.main([__file__, "-v"] + sys.argv[1:])
