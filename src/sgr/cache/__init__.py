"""
Cache module for SoundGraph.

This module provides caching functionality for track data and relationships,
reducing the need for repeated API calls.
"""

from .track_cache import TrackCache

__all__ = ["TrackCache"]
