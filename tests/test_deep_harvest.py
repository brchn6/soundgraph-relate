"""
Tests for Deep Harvest Engine

Tests the exhaustive data collection system.
"""

import tempfile
import shutil
from pathlib import Path
import pytest

from sgr.cache.track_cache import TrackCache
from sgr.collectors.deep_harvest import DeepHarvestEngine


class TestDeepHarvestEngine:
    """Test Deep Harvest Engine functionality."""
    
    def setup_method(self):
        """Create temporary cache for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "test_cache.db"
        self.cache = TrackCache(self.cache_path)
    
    def teardown_method(self):
        """Clean up."""
        self.cache.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_engine_initialization(self):
        """Test that Deep Harvest Engine initializes correctly."""
        # Mock SC client (we won't make real API calls in tests)
        mock_client = None
        
        config = {
            "max_users_per_track": 100,
            "max_tracks_per_user": 200,
            "request_delay": 0.1
        }
        
        engine = DeepHarvestEngine(mock_client, self.cache, config)
        
        assert engine.max_users_per_track == 100
        assert engine.max_tracks_per_user == 200
        assert engine.request_delay == 0.1
    
    def test_harvest_stats_initialization(self):
        """Test that harvest stats are initialized correctly."""
        engine = DeepHarvestEngine(None, self.cache, {})
        
        assert "tracks_collected" in engine.harvest_stats
        assert "users_collected" in engine.harvest_stats
        assert "playlists_collected" in engine.harvest_stats
        assert engine.harvest_stats["tracks_collected"] == 0
    
    def test_extract_key_terms(self):
        """Test key term extraction from track titles."""
        engine = DeepHarvestEngine(None, self.cache, {})
        
        title = "Lofi Beats to Study and Relax"
        terms = engine._extract_key_terms(title)
        
        # Should extract key terms and remove stopwords
        assert "lofi" in terms
        assert "beats" in terms
        assert "study" in terms
        assert "the" not in terms  # stopword
        assert "to" not in terms   # stopword
    
    def test_string_similarity(self):
        """Test string similarity calculation."""
        engine = DeepHarvestEngine(None, self.cache, {})
        
        # Identical strings
        assert engine._string_similarity("test", "test") == 1.0
        
        # Similar strings
        sim = engine._string_similarity("Lofi Beats", "LoFi Beats")
        assert sim > 0.8  # Should be high similarity
        
        # Different strings
        sim = engine._string_similarity("Lofi Beats", "Heavy Metal")
        assert sim < 0.5  # Should be low similarity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
