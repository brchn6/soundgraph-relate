"""
Post-Ingestion Relationship Builder

This module builds relationships and vectors AFTER the Deep Harvest Engine
has completed exhaustive data collection. It operates on the dense data lake
created by the harvest phase.

Philosophy: "Connect After Collection"
- Assumes data is already in the database
- Builds relationships from dense data
- Prepares vectors for ML/embedding models
"""

from __future__ import annotations
from typing import Dict, Any, List, Set, Tuple, Optional
from collections import defaultdict
from loguru import logger

from sgr.cache.track_cache import TrackCache


class PostIngestionProcessor:
    """
    Builds relationships from collected data after harvest is complete.
    
    This processor operates in phases:
    1. User-Track relationships (from engagements)
    2. User-User similarity (from shared likes)
    3. Track-Track co-occurrence (from playlists)
    4. Artist-Artist relationships (from co-library patterns)
    """
    
    def __init__(self, cache: TrackCache, config: Optional[Dict[str, Any]] = None):
        """
        Initialize post-ingestion processor.
        
        Args:
            cache: Database cache with harvested data
            config: Processing configuration
        """
        self.cache = cache
        self.config = config or {}
        
        # Processing thresholds
        self.min_common_tracks = self.config.get("min_common_tracks", 3)
        self.min_similarity_score = self.config.get("min_similarity_score", 0.1)
        self.min_co_occurrence = self.config.get("min_co_occurrence", 2)
        self.min_artist_strength = self.config.get("min_artist_strength", 0.3)
        
        self.stats = {
            "user_similarities": 0,
            "track_relationships": 0,
            "artist_relationships": 0
        }
    
    def process_all(self, seed_track_id: int) -> Dict[str, Any]:
        """
        Run all post-ingestion processing phases.
        
        Args:
            seed_track_id: The seed track that was harvested
            
        Returns:
            Processing statistics
        """
        logger.info("=" * 70)
        logger.info("🔨 POST-INGESTION PROCESSING")
        logger.info("=" * 70)
        logger.info("Building relationships from dense data lake...")
        logger.info("=" * 70)
        
        # Get all data that was collected
        cache_stats = self.cache.get_cache_stats()
        logger.info(f"Database contains:")
        logger.info(f"  Tracks: {cache_stats.get('tracks', 0):,}")
        logger.info(f"  Users: {cache_stats.get('users', 0):,}")
        logger.info(f"  Playlists: {cache_stats.get('playlists', 0):,}")
        logger.info(f"  User Engagements: {cache_stats.get('user_engagements', 0):,}")
        
        # Phase 1: Build user-user similarities
        logger.info("\n📊 Phase 1: Computing User Similarities...")
        logger.info("-" * 70)
        self._compute_user_similarities()
        
        # Phase 2: Build track-track co-occurrence
        logger.info("\n🎵 Phase 2: Computing Track Co-occurrence...")
        logger.info("-" * 70)
        self._compute_track_cooccurrence()
        
        # Phase 3: Build artist relationships
        logger.info("\n🎤 Phase 3: Computing Artist Relationships...")
        logger.info("-" * 70)
        self._compute_artist_relationships()
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.success("✅ POST-INGESTION PROCESSING COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"User similarities computed: {self.stats['user_similarities']:,}")
        logger.info(f"Track relationships built: {self.stats['track_relationships']:,}")
        logger.info(f"Artist relationships found: {self.stats['artist_relationships']:,}")
        logger.info("=" * 70)
        
        return self.stats
    
    def _compute_user_similarities(self):
        """
        Compute user-to-user similarities based on shared liked tracks.
        
        Uses Jaccard index: similarity = |A ∩ B| / |A ∪ B|
        """
        # Get all users who have engagement records
        cursor = self.cache.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT user_id 
            FROM user_engagements 
            WHERE engagement_type = 'like'
        """)
        
        user_ids = [row[0] for row in cursor.fetchall()]
        logger.info(f"Computing similarities for {len(user_ids)} users...")
        
        # For each pair of users, compute similarity
        computed = 0
        for i, user_a in enumerate(user_ids):
            # Get user A's liked tracks
            tracks_a = self.cache.get_user_liked_tracks(user_a, limit=10000)
            track_ids_a = {t['track_id'] for t in tracks_a}
            
            if len(track_ids_a) < self.min_common_tracks:
                continue
            
            # Compare with subsequent users (avoid duplicate pairs)
            for user_b in user_ids[i+1:]:
                # Get user B's liked tracks
                tracks_b = self.cache.get_user_liked_tracks(user_b, limit=10000)
                track_ids_b = {t['track_id'] for t in tracks_b}
                
                if len(track_ids_b) < self.min_common_tracks:
                    continue
                
                # Compute Jaccard similarity
                common = track_ids_a & track_ids_b
                union = track_ids_a | track_ids_b
                
                if len(common) >= self.min_common_tracks and len(union) > 0:
                    jaccard = len(common) / len(union)
                    
                    if jaccard >= self.min_similarity_score:
                        self.cache.add_user_similarity(
                            user_a, user_b,
                            "jaccard_likes", jaccard,
                            common_tracks=len(common),
                            total_tracks_a=len(track_ids_a),
                            total_tracks_b=len(track_ids_b)
                        )
                        computed += 1
            
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i+1}/{len(user_ids)} users processed, "
                          f"{computed} similarities found")
        
        self.stats['user_similarities'] = computed
        logger.success(f"✓ Computed {computed} user similarities")
    
    def _compute_track_cooccurrence(self):
        """
        Compute track-to-track relationships based on playlist co-occurrence.
        
        Tracks that appear together in multiple playlists are related.
        """
        # Get all playlists
        cursor = self.cache.conn.cursor()
        cursor.execute("SELECT playlist_id FROM playlists")
        playlist_ids = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"Computing co-occurrence from {len(playlist_ids)} playlists...")
        
        # Track co-occurrence counts
        cooccurrence = defaultdict(lambda: defaultdict(int))
        
        # For each playlist, count co-occurrences
        for playlist_id in playlist_ids:
            cursor.execute("""
                SELECT track_id FROM playlist_tracks 
                WHERE playlist_id = ?
                ORDER BY position
            """, (playlist_id,))
            
            tracks = [row[0] for row in cursor.fetchall()]
            
            # Count all pairs in this playlist
            for i, track_a in enumerate(tracks):
                for track_b in tracks[i+1:]:
                    cooccurrence[track_a][track_b] += 1
                    cooccurrence[track_b][track_a] += 1
        
        # Create relationships for significant co-occurrences
        relationships = 0
        for track_a, related_tracks in cooccurrence.items():
            for track_b, count in related_tracks.items():
                if count >= self.min_co_occurrence:
                    # Normalize weight (max playlist count seen is roughly log scale)
                    weight = min(1.0, count / 10.0)
                    
                    self.cache.add_related_track(
                        track_a, track_b,
                        "co_playlist", weight
                    )
                    relationships += 1
        
        self.stats['track_relationships'] = relationships
        logger.success(f"✓ Created {relationships} track relationships")
    
    def _compute_artist_relationships(self):
        """
        Compute artist-to-artist relationships based on co-library patterns.
        
        Artists whose tracks appear together in user libraries are related.
        """
        # Get all users and their liked tracks
        cursor = self.cache.conn.cursor()
        cursor.execute("""
            SELECT user_id, track_id 
            FROM user_engagements 
            WHERE engagement_type = 'like'
        """)
        
        # Build user -> artists mapping
        user_artists = defaultdict(set)
        for user_id, track_id in cursor.fetchall():
            # Get track's artist
            track = self.cache.get_track(track_id)
            if track and track.get('artist_id'):
                user_artists[user_id].add(track['artist_id'])
        
        logger.info(f"Analyzing {len(user_artists)} user libraries...")
        
        # Count artist co-occurrences in user libraries
        artist_cooccurrence = defaultdict(lambda: defaultdict(int))
        
        for user_id, artists in user_artists.items():
            artists_list = list(artists)
            # Count all artist pairs in this user's library
            for i, artist_a in enumerate(artists_list):
                for artist_b in artists_list[i+1:]:
                    artist_cooccurrence[artist_a][artist_b] += 1
                    artist_cooccurrence[artist_b][artist_a] += 1
        
        # Create relationships for significant co-occurrences
        relationships = 0
        for artist_a, related_artists in artist_cooccurrence.items():
            for artist_b, count in related_artists.items():
                if count >= 2:  # At least 2 users have both artists
                    # Strength based on evidence
                    strength = min(1.0, count / 20.0)
                    
                    if strength >= self.min_artist_strength:
                        self.cache.add_artist_relationship(
                            artist_a, artist_b,
                            "co_library", strength,
                            evidence_count=count,
                            metadata={"source": "user_libraries"}
                        )
                        relationships += 1
        
        self.stats['artist_relationships'] = relationships
        logger.success(f"✓ Created {relationships} artist relationships")
    
    def prepare_for_embeddings(self) -> Dict[str, Any]:
        """
        Prepare data structures for ML/embedding models.
        
        Returns:
            Dictionary containing:
            - track_vectors: Track features for embedding
            - user_vectors: User features for embedding
            - interaction_matrix: User-track interactions
        """
        logger.info("Preparing data for embedding models...")
        
        # This would extract features and create matrices suitable for
        # embedding models like Word2Vec, Node2Vec, or Graph Neural Networks
        
        # Placeholder for future implementation
        return {
            "ready_for_ml": True,
            "note": "Feature extraction and vectorization to be implemented"
        }
