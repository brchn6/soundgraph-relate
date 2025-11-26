#!/usr/bin/env python
"""
Deep Harvest Script - High-Performance Data Ingestion Engine

This script performs aggressive, recursive data collection from SoundCloud,
starting with a seed track URL. It prioritizes maximum data density and
volume over speed, ingesting all available social graph data into a local
SQLite database.

Philosophy: Build a solid data foundation by harvesting everything first,
then build relationships and analytics later.

Usage:
    python scripts/harvest.py <SOUNDCLOUD_URL>
    
Example:
    python scripts/harvest.py https://soundcloud.com/artist/track-name
"""

from __future__ import annotations
import sys
import time
import argparse
from pathlib import Path
from typing import Set, List, Dict, Any
from dotenv import load_dotenv
from loguru import logger

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sgr.io.soundcloud_client import make_client_from_env, SoundCloudError
from src.sgr.cache.track_cache import TrackCache


class DeepHarvestEngine:
    """
    High-performance deep harvest engine for SoundCloud data collection.
    
    Performs a three-phase recursive crawl:
    1. Seed Phase: Resolve track and fetch artist details
    2. Social Spill Phase: Fetch ALL users who liked/reposted the track
    3. User Depth Phase: For each user, fetch their complete liked tracks
    """
    
    def __init__(self, sc_client, cache: TrackCache, 
                 request_delay: float = 0.5,
                 max_users: int = 1000,
                 max_user_likes: int = 500):
        """
        Initialize the harvest engine.
        
        Args:
            sc_client: SoundCloud API client
            cache: SQLite database cache
            request_delay: Delay between API requests (seconds)
            max_users: Maximum users to fetch per track
            max_user_likes: Maximum likes to fetch per user
        """
        self.sc = sc_client
        self.cache = cache
        self.request_delay = request_delay
        self.max_users = max_users
        self.max_user_likes = max_user_likes
        
        # Tracking
        self.stats = {
            'tracks_collected': 0,
            'users_collected': 0,
            'likes_collected': 0,
            'reposts_collected': 0,
            'api_calls': 0,
        }
        self.processed_users: Set[int] = set()
        self.processed_tracks: Set[int] = set()
    
    def _rate_limit_sleep(self):
        """Sleep to respect API rate limits."""
        time.sleep(self.request_delay)
    
    def _paginate_all(self, fetch_func, *args, max_items: int = None, **kwargs) -> List[Any]:
        """
        Fetch all items from a paginated endpoint.
        
        Args:
            fetch_func: Function to call for fetching (e.g., sc.track_favoriters)
            max_items: Maximum items to fetch (None = unlimited)
            *args, **kwargs: Arguments to pass to fetch_func
            
        Returns:
            List of all fetched items
        """
        all_items = []
        offset = 0
        limit = 50  # SoundCloud API default
        
        while True:
            try:
                # Fetch page
                items = fetch_func(*args, limit=limit, offset=offset, **kwargs)
                self.stats['api_calls'] += 1
                
                if not items or len(items) == 0:
                    break
                
                all_items.extend(items)
                logger.debug(f"Fetched {len(items)} items (total: {len(all_items)})")
                
                # Check limits
                if max_items and len(all_items) >= max_items:
                    all_items = all_items[:max_items]
                    logger.debug(f"Reached max_items limit: {max_items}")
                    break
                
                # Check if we got fewer items than requested (last page)
                if len(items) < limit:
                    break
                
                offset += limit
                self._rate_limit_sleep()
                
            except Exception as e:
                logger.warning(f"Error during pagination at offset {offset}: {e}")
                break
        
        return all_items
    
    def harvest(self, track_url: str) -> Dict[str, Any]:
        """
        Execute the deep harvest for a given track URL.
        
        This is the main entry point that orchestrates the three-phase crawl.
        
        Args:
            track_url: SoundCloud track URL to start from
            
        Returns:
            Dictionary of harvest statistics
        """
        logger.info("=" * 80)
        logger.info("🌊 DEEP HARVEST ENGINE - STARTING")
        logger.info("=" * 80)
        logger.info(f"Seed URL: {track_url}")
        logger.info(f"Max Users: {self.max_users}")
        logger.info(f"Max User Likes: {self.max_user_likes}")
        logger.info(f"Request Delay: {self.request_delay}s")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        # === PHASE 1: SEED ===
        logger.info("\n📍 PHASE 1: SEED - Resolving track metadata")
        logger.info("-" * 80)
        
        try:
            track_data = self.sc.resolve(track_url)
            self.stats['api_calls'] += 1
        except Exception as e:
            logger.error(f"Failed to resolve track URL: {e}")
            raise
        
        track_id = track_data.get('id')
        if not track_id:
            raise ValueError("Could not extract track ID from resolved data")
        
        # Cache seed track
        self.cache.cache_track(track_data)
        self.processed_tracks.add(track_id)
        self.stats['tracks_collected'] += 1
        
        artist = track_data.get('user', {})
        artist_id = artist.get('id')
        artist_name = artist.get('username', 'Unknown')
        
        logger.success(f"✓ Resolved: '{track_data.get('title')}' by {artist_name}")
        logger.info(f"  Track ID: {track_id}")
        logger.info(f"  Artist ID: {artist_id}")
        logger.info(f"  Likes: {track_data.get('likes_count', 0):,}")
        logger.info(f"  Plays: {track_data.get('playback_count', 0):,}")
        
        # Cache artist
        if artist_id:
            self.cache.cache_user(artist)
            self.processed_users.add(artist_id)
            self.stats['users_collected'] += 1
        
        # === PHASE 2: SOCIAL SPILL ===
        logger.info("\n👥 PHASE 2: SOCIAL SPILL - Fetching all user interactions")
        logger.info("-" * 80)
        
        # Fetch all users who liked the track
        logger.info("Fetching users who liked the track...")
        likers = self._paginate_all(
            self.sc.track_favoriters,
            track_id,
            max_items=self.max_users
        )
        
        logger.success(f"✓ Found {len(likers)} users who liked this track")
        
        # Fetch all users who reposted the track
        logger.info("Fetching users who reposted the track...")
        reposters = self._paginate_all(
            self.sc.track_reposters,
            track_id,
            max_items=self.max_users
        )
        
        logger.success(f"✓ Found {len(reposters)} users who reposted this track")
        
        # Combine and deduplicate users
        all_users = {}
        for user in likers:
            user_id = user.get('id')
            if user_id:
                all_users[user_id] = user
                # Record the engagement
                self.cache.cache_user(user)
                self.cache.add_user_engagement(user_id, track_id, 'like')
                self.stats['likes_collected'] += 1
        
        for user in reposters:
            user_id = user.get('id')
            if user_id:
                if user_id not in all_users:
                    all_users[user_id] = user
                    self.cache.cache_user(user)
                # Record the engagement
                self.cache.add_user_engagement(user_id, track_id, 'repost')
                self.stats['reposts_collected'] += 1
        
        unique_users = list(all_users.values())
        logger.info(f"Total unique users: {len(unique_users)}")
        self.stats['users_collected'] += len(unique_users)
        
        # === PHASE 3: USER DEPTH ===
        logger.info("\n🔍 PHASE 3: USER DEPTH - Fetching user libraries")
        logger.info("-" * 80)
        logger.info(f"Processing {len(unique_users)} users...")
        
        for i, user in enumerate(unique_users, 1):
            user_id = user.get('id')
            username = user.get('username', 'Unknown')
            
            if user_id in self.processed_users:
                continue
            
            self.processed_users.add(user_id)
            
            logger.info(f"[{i}/{len(unique_users)}] Processing user: {username} (ID: {user_id})")
            
            # Fetch user's liked tracks
            try:
                user_likes = self._paginate_all(
                    self.sc.user_likes,
                    user_id,
                    max_items=self.max_user_likes
                )
                
                logger.info(f"  ✓ Found {len(user_likes)} liked tracks")
                
                # Cache all liked tracks
                for liked_track in user_likes:
                    if isinstance(liked_track, dict):
                        liked_track_id = liked_track.get('id')
                        if liked_track_id and liked_track_id not in self.processed_tracks:
                            self.cache.cache_track(liked_track)
                            self.processed_tracks.add(liked_track_id)
                            self.stats['tracks_collected'] += 1
                        
                        # Record the like engagement
                        if liked_track_id:
                            self.cache.add_user_engagement(user_id, liked_track_id, 'like')
                
            except Exception as e:
                logger.warning(f"  ✗ Error fetching likes for user {user_id}: {e}")
            
            # Small delay between users to avoid rate limiting
            if i < len(unique_users):
                self._rate_limit_sleep()
        
        # === COMPLETION ===
        elapsed = time.time() - start_time
        
        logger.info("\n" + "=" * 80)
        logger.success("🎉 DEEP HARVEST COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"Total Time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        logger.info(f"Tracks Collected: {self.stats['tracks_collected']:,}")
        logger.info(f"Users Collected: {self.stats['users_collected']:,}")
        logger.info(f"Likes Collected: {self.stats['likes_collected']:,}")
        logger.info(f"Reposts Collected: {self.stats['reposts_collected']:,}")
        logger.info(f"API Calls: {self.stats['api_calls']:,}")
        logger.info(f"Data Density: {self.stats['tracks_collected'] / max(elapsed, 1):.2f} tracks/sec")
        logger.info("=" * 80)
        
        # Show cache stats
        cache_stats = self.cache.get_cache_stats()
        logger.info("\n📊 DATABASE STATISTICS:")
        logger.info("-" * 80)
        for key, value in cache_stats.items():
            logger.info(f"{key:30s}: {value:,}")
        logger.info("=" * 80)
        
        return self.stats


def main():
    """Main entry point."""
    load_dotenv()
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Deep Harvest Engine - Aggressive SoundCloud Data Ingestion',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python scripts/harvest.py https://soundcloud.com/artist/track-name
  python scripts/harvest.py https://soundcloud.com/artist/track --max-users 500
  python scripts/harvest.py https://soundcloud.com/artist/track --delay 1.0
        '''
    )
    
    parser.add_argument(
        'url',
        help='SoundCloud track URL to start harvesting from'
    )
    
    parser.add_argument(
        '--cache-path',
        default='data/cache/tracks.db',
        help='Path to SQLite cache database (default: data/cache/tracks.db)'
    )
    
    parser.add_argument(
        '--max-users',
        type=int,
        default=1000,
        help='Maximum users to fetch per track (default: 1000)'
    )
    
    parser.add_argument(
        '--max-user-likes',
        type=int,
        default=500,
        help='Maximum likes to fetch per user (default: 500)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between API requests in seconds (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    # Initialize components
    logger.info("Initializing SoundCloud client...")
    try:
        sc_client = make_client_from_env()
    except Exception as e:
        logger.error(f"Failed to initialize SoundCloud client: {e}")
        logger.error("Make sure SOUNDCLOUD_ACCESS_TOKEN is set in your .env file")
        sys.exit(1)
    
    logger.info(f"Initializing cache at: {args.cache_path}")
    cache = TrackCache(args.cache_path)
    
    # Create engine
    engine = DeepHarvestEngine(
        sc_client,
        cache,
        request_delay=args.delay,
        max_users=args.max_users,
        max_user_likes=args.max_user_likes
    )
    
    # Run harvest
    try:
        stats = engine.harvest(args.url)
        logger.success("\n✅ Harvest completed successfully!")
        logger.info(f"Database saved to: {args.cache_path}")
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Harvest interrupted by user")
        logger.info("Partial data has been saved to cache")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"\n❌ Harvest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        cache.close()


if __name__ == '__main__':
    main()
