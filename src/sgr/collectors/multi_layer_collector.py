"""
Multi-layer relationship collector for building rich music graphs.

This module implements collectors for 4 layers of relationships:
- Layer 1: Track-to-Track (playlist co-occurrence) - existing
- Layer 2: User-to-Track (likes, reposts, plays)
- Layer 3: User-to-User (taste similarity, follows)
- Layer 4: Artist-to-Artist (collaborations, co-follow networks)
"""

from __future__ import annotations
import time
from typing import Dict, Any, List, Set, Optional
from collections import defaultdict
from loguru import logger

from sgr.io.soundcloud_client import SCClient
from sgr.cache.track_cache import TrackCache


class Layer2Collector:
    """
    Layer 2: User engagement collector.
    
    Collects user-to-track relationships via:
    - Likes (track favoriters)
    - Reposts
    
    Note: Play count data collection is planned for future implementation
    when SoundCloud API provides this endpoint.
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, config: Dict[str, Any]):
        """
        Initialize Layer 2 collector.
        
        Args:
            sc_client: SoundCloud API client
            cache: Track cache instance
            config: Layer 2 configuration
        """
        self.sc = sc_client
        self.cache = cache
        self.config = config
        self.max_likers_per_track = config.get("max_likers_per_track", 50)
        self.max_tracks_per_user = config.get("max_tracks_per_user", 100)
        self.min_likes_threshold = config.get("min_likes_threshold", 10)
        self.collect_reposts = config.get("collect_reposts", True)
        
    def collect_track_engagers(self, track_id: int) -> Dict[str, Any]:
        """
        Collect users who engaged with a track.
        
        Args:
            track_id: Track ID to collect engagers for
            
        Returns:
            Statistics about collected engagements
        """
        stats = {
            "track_id": track_id,
            "likers_collected": 0,
            "reposters_collected": 0,
            "engagement_relationships": 0
        }
        
        # Get track info to check likes threshold
        track_data = self.cache.get_track(track_id)
        if not track_data:
            logger.warning(f"Track {track_id} not in cache, skipping engager collection")
            return stats
        
        like_count = track_data.get("like_count", 0)
        if like_count < self.min_likes_threshold:
            logger.debug(f"Track {track_id} has only {like_count} likes, below threshold")
            return stats
        
        # Collect likers
        try:
            likers = self.sc.track_favoriters(track_id, limit=self.max_likers_per_track)
            for user in likers:
                user_id = user.get("id")
                if not user_id:
                    continue
                
                # Cache the user
                self.cache.cache_user(user)
                
                # Add engagement
                self.cache.add_user_engagement(
                    user_id, track_id, "like",
                    engagement_count=1
                )
                stats["likers_collected"] += 1
                stats["engagement_relationships"] += 1
            
            logger.debug(f"Collected {len(likers)} likers for track {track_id}")
            time.sleep(0.2)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error collecting likers for track {track_id}: {e}")
        
        # Collect reposters (if enabled)
        if self.collect_reposts:
            try:
                reposters = self.sc.track_reposters(track_id, limit=self.max_likers_per_track)
                for user in reposters:
                    user_id = user.get("id")
                    if not user_id:
                        continue
                    
                    # Cache the user
                    self.cache.cache_user(user)
                    
                    # Add engagement
                    self.cache.add_user_engagement(
                        user_id, track_id, "repost",
                        engagement_count=1
                    )
                    stats["reposters_collected"] += 1
                    stats["engagement_relationships"] += 1
                
                logger.debug(f"Collected {len(reposters)} reposters for track {track_id}")
                time.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error collecting reposters for track {track_id}: {e}")
        
        return stats
    
    def expand_user_liked_tracks(self, user_id: int) -> Dict[str, Any]:
        """
        Expand to tracks liked by a user and create relationships.
        
        Args:
            user_id: User ID to expand from
            
        Returns:
            Statistics about expansion
        """
        stats = {
            "user_id": user_id,
            "tracks_collected": 0,
            "relationships_created": 0
        }
        
        try:
            # Get user's liked tracks from API
            liked_tracks = self.sc.user_likes(user_id, limit=self.max_tracks_per_user)
            
            for track in liked_tracks:
                track_id = track.get("id")
                if not track_id:
                    continue
                
                # Cache the track
                self.cache.cache_track(track)
                stats["tracks_collected"] += 1
                
                # Add engagement relationship
                self.cache.add_user_engagement(
                    user_id, track_id, "like",
                    engagement_count=1
                )
                stats["relationships_created"] += 1
            
            logger.debug(f"Collected {len(liked_tracks)} liked tracks for user {user_id}")
            time.sleep(0.2)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error collecting liked tracks for user {user_id}: {e}")
        
        return stats


class Layer3Collector:
    """
    Layer 3: User similarity collector.
    
    Calculates user-to-user relationships via:
    - Taste similarity (Jaccard index on liked tracks)
    - Follow relationships
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, config: Dict[str, Any]):
        """
        Initialize Layer 3 collector.
        
        Args:
            sc_client: SoundCloud API client
            cache: Track cache instance
            config: Layer 3 configuration
        """
        self.sc = sc_client
        self.cache = cache
        self.config = config
        self.min_common_tracks = config.get("min_common_tracks", 3)
        self.min_similarity_score = config.get("min_similarity_score", 0.1)
        self.max_similar_users = config.get("max_similar_users", 50)
    
    def calculate_user_similarity(self, user_id: int, candidate_users: List[int]) -> Dict[str, Any]:
        """
        Calculate similarity between a user and candidate users based on liked tracks.
        
        Args:
            user_id: Source user ID
            candidate_users: List of candidate user IDs
            
        Returns:
            Statistics about calculated similarities
        """
        stats = {
            "user_id": user_id,
            "candidates_processed": 0,
            "similarities_computed": 0
        }
        
        # Get user's liked tracks
        user_liked = self.cache.get_user_liked_tracks(user_id, limit=500)
        user_track_ids = {t["track_id"] for t in user_liked}
        
        if len(user_track_ids) < self.min_common_tracks:
            logger.debug(f"User {user_id} has too few liked tracks for similarity")
            return stats
        
        # Calculate Jaccard similarity with each candidate
        for candidate_id in candidate_users:
            if candidate_id == user_id:
                continue
            
            # Get candidate's liked tracks
            candidate_liked = self.cache.get_user_liked_tracks(candidate_id, limit=500)
            candidate_track_ids = {t["track_id"] for t in candidate_liked}
            
            if len(candidate_track_ids) < self.min_common_tracks:
                continue
            
            # Calculate Jaccard index
            common = user_track_ids & candidate_track_ids
            union = user_track_ids | candidate_track_ids
            
            if len(union) == 0:
                continue
            
            jaccard_score = len(common) / len(union)
            
            if jaccard_score >= self.min_similarity_score and len(common) >= self.min_common_tracks:
                # Store similarity
                self.cache.add_user_similarity(
                    user_id, candidate_id,
                    "jaccard_likes", jaccard_score,
                    common_tracks=len(common),
                    total_tracks_a=len(user_track_ids),
                    total_tracks_b=len(candidate_track_ids)
                )
                stats["similarities_computed"] += 1
            
            stats["candidates_processed"] += 1
        
        return stats
    
    def find_similar_users_for_track(self, track_id: int) -> Dict[str, Any]:
        """
        Find users with similar taste based on who liked a track.
        
        Args:
            track_id: Track ID
            
        Returns:
            Statistics about similarity calculations
        """
        stats = {
            "track_id": track_id,
            "users_found": 0,
            "similarities_computed": 0
        }
        
        # Get users who liked this track
        engagers = self.cache.get_track_engagers(track_id, engagement_type="like")
        user_ids = [e["user_id"] for e in engagers]
        
        stats["users_found"] = len(user_ids)
        
        # Calculate pairwise similarities among these users
        for i, user_id in enumerate(user_ids):
            # Only compare with users we haven't compared yet
            candidates = user_ids[i+1:]
            
            if not candidates:
                continue
            
            result = self.calculate_user_similarity(user_id, candidates)
            stats["similarities_computed"] += result["similarities_computed"]
        
        return stats


class Layer4Collector:
    """
    Layer 4: Artist relationship collector.
    
    Detects artist-to-artist relationships via:
    - Collaborations (tracks with multiple artists)
    - Co-follow networks (artists followed by same users)
    - Co-library patterns (artists appearing in same user libraries)
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, config: Dict[str, Any]):
        """
        Initialize Layer 4 collector.
        
        Args:
            sc_client: SoundCloud API client
            cache: Track cache instance
            config: Layer 4 configuration
        """
        self.sc = sc_client
        self.cache = cache
        self.config = config
        self.min_collaboration_evidence = config.get("min_collaboration_evidence", 2)
        self.detect_co_library = config.get("detect_co_library", True)
    
    def detect_artist_cooccurrence(self, track_ids: List[int]) -> Dict[str, Any]:
        """
        Detect artist relationships based on track co-occurrence.
        
        When tracks by different artists appear in the same playlists,
        it suggests an artist relationship.
        
        Args:
            track_ids: List of track IDs to analyze
            
        Returns:
            Statistics about detected relationships
        """
        stats = {
            "tracks_analyzed": 0,
            "artist_pairs_found": 0,
            "relationships_created": 0
        }
        
        # Build artist to tracks mapping
        artist_tracks = defaultdict(set)
        
        for track_id in track_ids:
            track = self.cache.get_track(track_id)
            if not track:
                continue
            
            artist_id = track.get("artist_id")
            if artist_id:
                artist_tracks[artist_id].add(track_id)
                stats["tracks_analyzed"] += 1
        
        # Find artists whose tracks co-occur in playlists
        artist_cooccurrence = defaultdict(int)
        
        for track_id in track_ids:
            # Get related tracks (co-playlist)
            related = self.cache.get_related_tracks(track_id, relation_type="co_playlist", limit=100)
            
            # Get artist of current track
            track = self.cache.get_track(track_id)
            if not track:
                continue
            artist_id = track.get("artist_id")
            if not artist_id:
                continue
            
            # Count co-occurrences with other artists
            for rel in related:
                rel_track_id = rel["track_id"]
                rel_track = self.cache.get_track(rel_track_id)
                if not rel_track:
                    continue
                
                rel_artist_id = rel_track.get("artist_id")
                if not rel_artist_id or rel_artist_id == artist_id:
                    continue
                
                # Create canonical pair
                pair = tuple(sorted([artist_id, rel_artist_id]))
                artist_cooccurrence[pair] += 1
        
        # Create relationships for pairs with sufficient evidence
        for (artist_a, artist_b), count in artist_cooccurrence.items():
            if count >= self.min_collaboration_evidence:
                strength = min(1.0, count / 10.0)  # Normalize strength
                
                self.cache.add_artist_relationship(
                    artist_a, artist_b,
                    "co_library", strength,
                    evidence_count=count,
                    metadata={"source": "playlist_cooccurrence"}
                )
                stats["relationships_created"] += 1
            
            stats["artist_pairs_found"] += 1
        
        return stats
    
    def detect_user_library_patterns(self, user_id: int) -> Dict[str, Any]:
        """
        Detect artist relationships based on user's library.
        
        Args:
            user_id: User ID to analyze
            
        Returns:
            Statistics about detected relationships
        """
        stats = {
            "user_id": user_id,
            "artists_found": 0,
            "relationships_created": 0
        }
        
        # Get user's liked tracks
        liked_tracks = self.cache.get_user_liked_tracks(user_id, limit=200)
        
        # Count tracks by each artist
        artist_tracks_count = defaultdict(int)
        artist_ids = []
        
        for track in liked_tracks:
            artist_id = track.get("artist_id")
            if artist_id:
                artist_tracks_count[artist_id] += 1
                if artist_id not in artist_ids:
                    artist_ids.append(artist_id)
        
        stats["artists_found"] = len(artist_ids)
        
        # If user likes multiple tracks by multiple artists, create co-library relationships
        if len(artist_ids) >= 2:
            for i, artist_a in enumerate(artist_ids):
                for artist_b in artist_ids[i+1:]:
                    # Strength based on number of tracks by each artist
                    count_a = artist_tracks_count[artist_a]
                    count_b = artist_tracks_count[artist_b]
                    
                    # Simple strength: average of normalized counts
                    strength = min(1.0, (count_a + count_b) / 20.0)
                    
                    self.cache.add_artist_relationship(
                        artist_a, artist_b,
                        "co_library", strength,
                        evidence_count=1,
                        metadata={"source": "user_library", "user_id": user_id}
                    )
                    stats["relationships_created"] += 1
        
        return stats


class MultiLayerCollector:
    """
    Main multi-layer collector that orchestrates all 4 layers.
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, config: Dict[str, Any]):
        """
        Initialize multi-layer collector.
        
        Args:
            sc_client: SoundCloud API client
            cache: Track cache instance
            config: Multi-layer configuration
        """
        self.sc = sc_client
        self.cache = cache
        self.config = config
        
        # Initialize layer collectors
        self.layer2 = Layer2Collector(sc_client, cache, config.get("layer2", {}))
        self.layer3 = Layer3Collector(sc_client, cache, config.get("layer3", {}))
        self.layer4 = Layer4Collector(sc_client, cache, config.get("layer4", {}))
        
        # Get enabled layers
        enabled = config.get("enabled_layers", {})
        self.layer2_enabled = enabled.get("layer2_user_engagement", True)
        self.layer3_enabled = enabled.get("layer3_user_similarity", True)
        self.layer4_enabled = enabled.get("layer4_artist_collaboration", True)
    
    def collect_multi_layer_relationships(self, track_ids: List[int]) -> Dict[str, Any]:
        """
        Collect all enabled layers of relationships for a set of tracks.
        
        Args:
            track_ids: List of track IDs to process
            
        Returns:
            Aggregated statistics for all layers
        """
        logger.info(f"Starting multi-layer collection for {len(track_ids)} tracks")
        
        results = {
            "tracks_processed": len(track_ids),
            "layer2": {"enabled": self.layer2_enabled},
            "layer3": {"enabled": self.layer3_enabled},
            "layer4": {"enabled": self.layer4_enabled}
        }
        
        # Layer 2: User engagements
        if self.layer2_enabled:
            logger.info("Collecting Layer 2: User engagements...")
            layer2_stats = {
                "total_likers": 0,
                "total_reposters": 0,
                "total_engagements": 0,
                "tracks_processed": 0
            }
            
            for track_id in track_ids:
                stats = self.layer2.collect_track_engagers(track_id)
                layer2_stats["total_likers"] += stats["likers_collected"]
                layer2_stats["total_reposters"] += stats["reposters_collected"]
                layer2_stats["total_engagements"] += stats["engagement_relationships"]
                if stats["engagement_relationships"] > 0:
                    layer2_stats["tracks_processed"] += 1
            
            results["layer2"].update(layer2_stats)
            logger.success(f"Layer 2 complete: {layer2_stats['total_engagements']} engagements")
        
        # Layer 3: User similarity
        if self.layer3_enabled:
            logger.info("Collecting Layer 3: User similarity...")
            layer3_stats = {
                "total_similarities": 0,
                "tracks_processed": 0
            }
            
            for track_id in track_ids:
                stats = self.layer3.find_similar_users_for_track(track_id)
                layer3_stats["total_similarities"] += stats["similarities_computed"]
                if stats["users_found"] > 0:
                    layer3_stats["tracks_processed"] += 1
            
            results["layer3"].update(layer3_stats)
            logger.success(f"Layer 3 complete: {layer3_stats['total_similarities']} similarities")
        
        # Layer 4: Artist relationships
        if self.layer4_enabled:
            logger.info("Collecting Layer 4: Artist relationships...")
            layer4_stats = self.layer4.detect_artist_cooccurrence(track_ids)
            
            results["layer4"].update(layer4_stats)
            logger.success(f"Layer 4 complete: {layer4_stats['relationships_created']} artist relationships")
        
        logger.success("Multi-layer collection complete!")
        return results
