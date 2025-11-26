"""
Deep Harvest Engine - Aggressive Data Ingestion Module

This module implements exhaustive data crawling for SoundGraph-Relate.
Instead of building relationships on-the-fly, it prioritizes complete data 
collection first, solving the sparsity problem by flooding the database 
with all available context.

Philosophy: "Spill-First, Connect Later"
- Fetch ALL related data points exhaustively
- Persist everything to database immediately
- Build relationships only after data lake is established
"""

from __future__ import annotations
import time
import re
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict
from loguru import logger
from difflib import SequenceMatcher

from sgr.io.soundcloud_client import SCClient
from sgr.cache.track_cache import TrackCache


class DeepHarvestEngine:
    """
    Deep Harvest Engine for exhaustive data collection.
    
    This engine performs aggressive, multi-dimensional crawling:
    1. User Depth - ALL users who liked/reposted + their entire libraries
    2. Playlist Depth - ALL playlists containing track + all their tracks
    3. Artist Depth - Complete discography of track creator
    4. Semantic Depth - Fuzzy name matching to find similar named tracks
    5. Commentary Depth - High-engagement users via comments
    6. Label/Network Depth - Entire label/collective catalogs
    7. Contextual Entity Depth - Mentioned artists/collaborators in metadata
    """
    
    def __init__(self, sc_client: SCClient, cache: TrackCache, 
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize Deep Harvest Engine.
        
        Args:
            sc_client: SoundCloud API client
            cache: Database cache for persistent storage
            config: Harvesting configuration (limits, thresholds, etc.)
        """
        self.sc = sc_client
        self.cache = cache
        self.config = config or {}
        
        # Harvest configuration with aggressive defaults
        self.max_users_per_track = self.config.get("max_users_per_track", 500)  # Up from 50
        self.max_tracks_per_user = self.config.get("max_tracks_per_user", 500)  # Up from 100
        self.max_playlists = self.config.get("max_playlists", 200)  # Up from 20
        self.max_artist_tracks = self.config.get("max_artist_tracks", 1000)  # Complete discography
        self.fuzzy_search_limit = self.config.get("fuzzy_search_limit", 100)
        self.name_similarity_threshold = self.config.get("name_similarity_threshold", 0.6)
        self.enable_commentary_layer = self.config.get("enable_commentary_layer", True)
        self.enable_label_layer = self.config.get("enable_label_layer", True)
        self.enable_contextual_layer = self.config.get("enable_contextual_layer", True)
        
        # Rate limiting
        self.request_delay = self.config.get("request_delay", 0.3)  # Slower but safer
        
        # Tracking
        self.harvest_stats = {
            "tracks_collected": 0,
            "users_collected": 0,
            "playlists_collected": 0,
            "artists_collected": 0,
            "labels_detected": 0,
            "entities_extracted": 0,
            "api_requests": 0
        }
    
    def deep_harvest(self, seed_track_id: int) -> Dict[str, Any]:
        """
        Execute deep harvest starting from seed track.
        
        This is the main entry point. It performs exhaustive data collection
        across all dimensions before any relationship building.
        
        Args:
            seed_track_id: The seed track to start crawling from
            
        Returns:
            Statistics about the harvest operation
        """
        logger.info(f"🌊 Starting Deep Harvest for track {seed_track_id}")
        logger.info("=" * 70)
        logger.info("Deep Harvest Engine - Exhaustive Data Collection Mode")
        logger.info("Prioritizing data density over speed...")
        logger.info("=" * 70)
        
        # Reset stats
        self.harvest_stats = {k: 0 for k in self.harvest_stats}
        
        # Get seed track data
        seed_track = self._fetch_and_cache_track(seed_track_id)
        if not seed_track:
            logger.error(f"Failed to fetch seed track {seed_track_id}")
            return self.harvest_stats
        
        # Phase 1: User Depth - Exhaustive user engagement crawl
        logger.info("\n📊 PHASE 1: User Depth Harvest")
        logger.info("-" * 70)
        self._harvest_user_depth(seed_track_id, seed_track)
        
        # Phase 2: Playlist Depth - Complete playlist ecosystem
        logger.info("\n📚 PHASE 2: Playlist Depth Harvest")
        logger.info("-" * 70)
        self._harvest_playlist_depth(seed_track_id, seed_track)
        
        # Phase 3: Artist Depth - Complete discography
        logger.info("\n🎤 PHASE 3: Artist Depth Harvest")
        logger.info("-" * 70)
        self._harvest_artist_depth(seed_track)
        
        # Phase 4: Semantic Depth - Fuzzy name matching
        logger.info("\n🔍 PHASE 4: Semantic Depth Harvest")
        logger.info("-" * 70)
        self._harvest_semantic_depth(seed_track)
        
        # Phase 5: Commentary Layer (if enabled)
        if self.enable_commentary_layer:
            logger.info("\n💬 PHASE 5: Commentary Depth Harvest")
            logger.info("-" * 70)
            self._harvest_commentary_depth(seed_track_id)
        
        # Phase 6: Label/Network Layer (if enabled)
        if self.enable_label_layer:
            logger.info("\n🏷️  PHASE 6: Label/Network Depth Harvest")
            logger.info("-" * 70)
            self._harvest_label_depth(seed_track)
        
        # Phase 7: Contextual Entity Layer (if enabled)
        if self.enable_contextual_layer:
            logger.info("\n🔗 PHASE 7: Contextual Entity Depth Harvest")
            logger.info("-" * 70)
            self._harvest_contextual_entities(seed_track)
        
        # Final summary
        logger.info("\n" + "=" * 70)
        logger.success("✅ Deep Harvest Complete!")
        logger.info("=" * 70)
        logger.info(f"Tracks collected: {self.harvest_stats['tracks_collected']}")
        logger.info(f"Users collected: {self.harvest_stats['users_collected']}")
        logger.info(f"Playlists collected: {self.harvest_stats['playlists_collected']}")
        logger.info(f"Artists collected: {self.harvest_stats['artists_collected']}")
        logger.info(f"Labels detected: {self.harvest_stats['labels_detected']}")
        logger.info(f"Entities extracted: {self.harvest_stats['entities_extracted']}")
        logger.info(f"Total API requests: {self.harvest_stats['api_requests']}")
        logger.info("=" * 70)
        
        return self.harvest_stats
    
    def _harvest_user_depth(self, track_id: int, track_data: Dict[str, Any]):
        """
        Phase 1: Harvest ALL users who engaged with track and their libraries.
        
        This solves the sparsity problem by:
        1. Finding ALL users who liked/reposted the track
        2. For each user, fetching their ENTIRE library of likes
        3. Persisting everything to database
        """
        logger.info("Fetching ALL users who liked/reposted this track...")
        
        # Collect all likers (exhaustive)
        likers = self._fetch_all_paginated(
            lambda offset: self.sc.track_favoriters(track_id, limit=50, offset=offset),
            max_results=self.max_users_per_track
        )
        
        logger.info(f"Found {len(likers)} users who liked this track")
        
        # Collect all reposters (exhaustive)
        reposters = self._fetch_all_paginated(
            lambda offset: self.sc.track_reposters(track_id, limit=50, offset=offset),
            max_results=self.max_users_per_track
        )
        
        logger.info(f"Found {len(reposters)} users who reposted this track")
        
        # Combine and deduplicate
        all_users = {u['id']: u for u in likers + reposters if u.get('id')}
        logger.info(f"Total unique users: {len(all_users)}")
        
        # For each user, harvest their entire library
        for i, (user_id, user_data) in enumerate(all_users.items(), 1):
            # Cache user
            self.cache.cache_user(user_data)
            self.harvest_stats['users_collected'] += 1
            
            # Add engagement record
            self.cache.add_user_engagement(user_id, track_id, "like", 1)
            
            # Fetch user's complete library
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(all_users)} users processed")
            
            user_library = self._fetch_all_paginated(
                lambda offset: self.sc.user_likes(user_id, limit=50, offset=offset),
                max_results=self.max_tracks_per_user
            )
            
            logger.debug(f"User {user_id}: {len(user_library)} liked tracks")
            
            # Cache all tracks from user's library
            for liked_track in user_library:
                if liked_track.get('id'):
                    self._cache_track_data(liked_track)
                    # Record engagement
                    self.cache.add_user_engagement(
                        user_id, liked_track['id'], "like", 1
                    )
            
            time.sleep(self.request_delay)
        
        logger.success(f"✓ User Depth: {self.harvest_stats['users_collected']} users, "
                      f"{self.harvest_stats['tracks_collected']} tracks collected")
    
    def _harvest_playlist_depth(self, track_id: int, track_data: Dict[str, Any]):
        """
        Phase 2: Find ALL playlists containing this track and harvest all their tracks.
        
        Note: SoundCloud API doesn't have direct "playlists containing track" endpoint,
        so we use heuristics:
        1. Search for playlists with track title
        2. Check artist's playlists
        3. Check likers' playlists
        """
        logger.info("Harvesting playlists containing this track...")
        
        playlists_found = set()
        
        # Get artist's playlists
        artist_id = track_data.get('user', {}).get('id')
        if artist_id:
            artist_playlists = self._fetch_all_paginated(
                lambda offset: self.sc.user_playlists(artist_id, limit=50, offset=offset),
                max_results=self.max_playlists
            )
            
            for playlist in artist_playlists:
                if playlist.get('id'):
                    playlists_found.add(playlist['id'])
                    self._harvest_playlist_tracks(playlist)
        
        logger.success(f"✓ Playlist Depth: {len(playlists_found)} playlists harvested")
    
    def _harvest_artist_depth(self, track_data: Dict[str, Any]):
        """
        Phase 3: Harvest complete discography of the track's creator.
        """
        artist = track_data.get('user', {})
        artist_id = artist.get('id')
        
        if not artist_id:
            logger.warning("No artist found for track")
            return
        
        logger.info(f"Harvesting complete discography for artist: {artist.get('username')}")
        
        # Cache artist
        self.cache.cache_user(artist)
        self.harvest_stats['artists_collected'] += 1
        
        # Search for all tracks by this artist
        # Note: SoundCloud doesn't have a direct user_tracks endpoint in v1
        # We'll use search with artist name filter
        artist_name = artist.get('username', '')
        
        # Search approach
        search_query = f'"{artist_name}"'
        artist_tracks = self._fetch_all_paginated(
            lambda offset: self.sc.search_tracks(search_query, limit=50, offset=offset),
            max_results=self.max_artist_tracks
        )
        
        # Filter to only tracks by this artist
        confirmed_tracks = [
            t for t in artist_tracks 
            if t.get('user', {}).get('id') == artist_id
        ]
        
        logger.info(f"Found {len(confirmed_tracks)} tracks by this artist")
        
        for track in confirmed_tracks:
            self._cache_track_data(track)
        
        logger.success(f"✓ Artist Depth: {len(confirmed_tracks)} tracks from discography")
    
    def _harvest_semantic_depth(self, track_data: Dict[str, Any]):
        """
        Phase 4: Find tracks with similar names using fuzzy matching.
        
        This catches remixes, covers, and variations that share semantic similarity.
        """
        title = track_data.get('title', '')
        if not title:
            return
        
        logger.info(f"Searching for semantically similar tracks to: {title}")
        
        # Extract key terms from title (remove common words)
        key_terms = self._extract_key_terms(title)
        
        similar_tracks = []
        for term in key_terms[:3]:  # Search top 3 key terms
            search_results = self._fetch_all_paginated(
                lambda offset: self.sc.search_tracks(term, limit=50, offset=offset),
                max_results=self.fuzzy_search_limit
            )
            
            for track in search_results:
                track_title = track.get('title', '')
                similarity = self._string_similarity(title, track_title)
                
                if similarity >= self.name_similarity_threshold:
                    similar_tracks.append(track)
                    self._cache_track_data(track)
            
            time.sleep(self.request_delay)
        
        logger.success(f"✓ Semantic Depth: {len(similar_tracks)} similar named tracks found")
    
    def _harvest_commentary_depth(self, track_id: int):
        """
        Phase 5: Harvest commenters (high-engagement users) and their activity.
        
        Note: SoundCloud v1 API has limited comment support.
        This is a placeholder for when comment data is available.
        """
        logger.info("Commentary layer currently limited by API availability")
        # Placeholder - would fetch comments and commenter libraries
    
    def _harvest_label_depth(self, track_data: Dict[str, Any]):
        """
        Phase 6: Detect label/collective and harvest entire catalog.
        
        Labels are often mentioned in:
        - Track description
        - Track label field
        - Publisher info
        """
        description = track_data.get('description', '') or ''
        label_field = track_data.get('label_name', '') or ''
        publisher = track_data.get('publisher_metadata', {})
        
        # Extract potential label names
        labels_found = set()
        
        if label_field:
            labels_found.add(label_field)
        
        # Look for label patterns in description
        label_patterns = [
            r'released (?:by|on) ([A-Z][A-Za-z\s]+(?:Records|Music|Label))',
            r'©\s*(\d{4})?\s*([A-Z][A-Za-z\s]+(?:Records|Music|Label))',
        ]
        
        for pattern in label_patterns:
            matches = re.findall(pattern, description)
            for match in matches:
                label_name = match if isinstance(match, str) else match[-1]
                labels_found.add(label_name.strip())
        
        if not labels_found:
            logger.info("No labels detected")
            return
        
        logger.info(f"Detected labels: {', '.join(labels_found)}")
        self.harvest_stats['labels_detected'] += len(labels_found)
        
        # Search for label catalog
        for label in list(labels_found)[:3]:  # Limit to top 3 labels
            logger.info(f"Harvesting catalog for label: {label}")
            label_catalog = self._fetch_all_paginated(
                lambda offset: self.sc.search_tracks(label, limit=50, offset=offset),
                max_results=200  # Reasonable label catalog size
            )
            
            for track in label_catalog:
                # Verify it's actually from this label
                if label.lower() in (track.get('label_name', '') or '').lower():
                    self._cache_track_data(track)
            
            time.sleep(self.request_delay)
        
        logger.success(f"✓ Label Depth: {len(labels_found)} labels processed")
    
    def _harvest_contextual_entities(self, track_data: Dict[str, Any]):
        """
        Phase 7: Extract mentioned entities (artists, collaborators) and crawl them.
        
        Looks for:
        - @mentions in description
        - "feat.", "ft.", "featuring" in title
        - "remix by", "prod. by" patterns
        """
        title = track_data.get('title', '') or ''
        description = track_data.get('description', '') or ''
        
        entities = set()
        
        # Extract @mentions
        mentions = re.findall(r'@([a-zA-Z0-9_-]+)', description)
        entities.update(mentions)
        
        # Extract featuring artists
        feat_patterns = [
            r'(?:feat\.|ft\.|featuring)\s+([A-Za-z0-9\s&,]+?)(?:\s|$|\))',
            r'(?:remix by|remixed by|prod\. by)\s+([A-Za-z0-9\s&,]+?)(?:\s|$|\))',
        ]
        
        for pattern in feat_patterns:
            matches = re.findall(pattern, title + ' ' + description, re.IGNORECASE)
            for match in matches:
                # Clean up and split multiple artists
                artists = re.split(r'[,&]', match)
                entities.update(a.strip() for a in artists if a.strip())
        
        if not entities:
            logger.info("No contextual entities found")
            return
        
        logger.info(f"Extracted entities: {', '.join(list(entities)[:5])}...")
        self.harvest_stats['entities_extracted'] += len(entities)
        
        # Search for each entity
        for entity in list(entities)[:10]:  # Limit to top 10 entities
            logger.debug(f"Searching for entity: {entity}")
            entity_tracks = self._fetch_all_paginated(
                lambda offset: self.sc.search_tracks(entity, limit=20, offset=offset),
                max_results=50
            )
            
            for track in entity_tracks:
                self._cache_track_data(track)
            
            time.sleep(self.request_delay)
        
        logger.success(f"✓ Contextual Entity Depth: {len(entities)} entities processed")
    
    # ============= Helper Methods =============
    
    def _fetch_and_cache_track(self, track_id: int) -> Optional[Dict[str, Any]]:
        """Fetch track from API and cache it."""
        # Check cache first
        cached = self.cache.get_track(track_id)
        if cached and cached.get('raw_json'):
            return cached.get('raw_data')
        
        # Would need to fetch from API
        # For now, return None as direct track fetch isn't available in v1
        logger.warning(f"Track {track_id} not in cache and direct fetch not available")
        return None
    
    def _cache_track_data(self, track_data: Dict[str, Any]):
        """Cache track data and increment counter."""
        if track_data.get('id'):
            self.cache.cache_track(track_data)
            self.harvest_stats['tracks_collected'] += 1
            
            # Cache artist too
            if track_data.get('user'):
                self.cache.cache_user(track_data['user'])
    
    def _harvest_playlist_tracks(self, playlist_data: Dict[str, Any]):
        """Harvest all tracks from a playlist."""
        playlist_id = playlist_data.get('id')
        if not playlist_id:
            return
        
        # Cache playlist
        self.cache.cache_playlist(playlist_data)
        self.harvest_stats['playlists_collected'] += 1
        
        # Get tracks
        tracks = playlist_data.get('tracks', [])
        if tracks:
            for track in tracks:
                if track and track.get('id'):
                    self._cache_track_data(track)
            
            # Cache playlist-track relationships
            self.cache.cache_playlist_tracks(playlist_id, tracks)
    
    def _fetch_all_paginated(self, fetch_func, max_results: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch all pages of results up to max_results.
        
        Args:
            fetch_func: Function that takes offset and returns results
            max_results: Maximum total results to fetch
            
        Returns:
            List of all results
        """
        all_results = []
        offset = 0
        page_size = 50
        
        while len(all_results) < max_results:
            try:
                batch = fetch_func(offset)
                self.harvest_stats['api_requests'] += 1
                
                if not batch or len(batch) == 0:
                    break
                
                all_results.extend(batch)
                
                if len(batch) < page_size:
                    # Last page
                    break
                
                offset += page_size
                time.sleep(self.request_delay)
                
            except Exception as e:
                logger.error(f"Error fetching page at offset {offset}: {e}")
                break
        
        return all_results[:max_results]
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from text (remove stopwords)."""
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been'
        }
        
        # Split and clean
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        key_terms = [w for w in words if w not in stopwords and len(w) > 2]
        
        return key_terms
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings (0-1)."""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
