#!/usr/bin/env python
"""
Deep Harvest Script - Exhaustive Data Collection

This script runs the Deep Harvest Engine to perform aggressive,
multi-dimensional data collection for a seed track.

Usage:
    TRACK_URL="https://soundcloud.com/artist/track" python scripts/deep_harvest.py
    
    # Or with track ID
    TRACK_ID=12345 python scripts/deep_harvest.py
    
    # Custom configuration
    TRACK_URL="..." CONFIG_FILE=configs/harvest_config.yaml python scripts/deep_harvest.py
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml
import time

from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache.track_cache import TrackCache
from sgr.collectors.deep_harvest import DeepHarvestEngine


def main():
    """Main entry point for deep harvest."""
    load_dotenv()
    
    # Get track URL or ID
    track_url = os.getenv("TRACK_URL")
    track_id = os.getenv("TRACK_ID")
    
    if not track_url and not track_id:
        logger.error("TRACK_URL or TRACK_ID environment variable is required")
        print("\nUsage:")
        print('  TRACK_URL="https://soundcloud.com/artist/track" python scripts/deep_harvest.py')
        print('  TRACK_ID=12345 python scripts/deep_harvest.py')
        sys.exit(1)
    
    # Load configuration
    config_file = os.getenv("CONFIG_FILE", "configs/config.yaml")
    cfg = yaml.safe_load(open(config_file))
    
    cache_path = os.getenv("CACHE_PATH", cfg.get("cache", {}).get("default_path", "data/cache/tracks.db"))
    
    logger.info("=" * 80)
    logger.info("🌊 DEEP HARVEST ENGINE")
    logger.info("=" * 80)
    logger.info("Mode: Exhaustive Data Collection (Spill-First Architecture)")
    logger.info("Philosophy: Solve sparsity through aggressive crawling")
    logger.info("=" * 80)
    
    if track_url:
        logger.info(f"Seed Track URL: {track_url}")
    else:
        logger.info(f"Seed Track ID: {track_id}")
    
    logger.info(f"Cache Path: {cache_path}")
    logger.info(f"Config File: {config_file}")
    
    # Initialize components
    sc_client = make_client_from_env()
    cache = TrackCache(cache_path)
    
    # Get deep harvest config
    harvest_config = cfg.get("deep_harvest", {})
    
    if not harvest_config.get("enabled", True):
        logger.error("Deep Harvest is disabled in configuration!")
        sys.exit(1)
    
    # Initialize Deep Harvest Engine
    engine = DeepHarvestEngine(sc_client, cache, harvest_config)
    
    # Get track ID if URL provided
    if track_url and not track_id:
        logger.info("Resolving track URL...")
        try:
            resolved = sc_client.resolve(track_url)
            track_id = resolved.get("id")
            
            if not track_id:
                logger.error("Could not resolve track ID from URL")
                sys.exit(1)
            
            # Cache the resolved track
            cache.cache_track(resolved)
            logger.success(f"✓ Resolved to track ID: {track_id}")
            
        except Exception as e:
            logger.error(f"Error resolving track URL: {e}")
            sys.exit(1)
    
    track_id = int(track_id)
    
    # Display harvest configuration
    logger.info("\n" + "=" * 80)
    logger.info("HARVEST CONFIGURATION")
    logger.info("=" * 80)
    
    phases = [
        ("User Depth", "user_depth"),
        ("Playlist Depth", "playlist_depth"),
        ("Artist Depth", "artist_depth"),
        ("Semantic Depth", "semantic_depth"),
        ("Commentary Layer", "commentary_layer"),
        ("Label/Network Layer", "label_layer"),
        ("Contextual Entity Layer", "contextual_layer")
    ]
    
    for phase_name, config_key in phases:
        phase_config = harvest_config.get(config_key, {})
        enabled = phase_config.get("enabled", True)
        status = "✓ ENABLED" if enabled else "✗ DISABLED"
        logger.info(f"{phase_name:30s} {status}")
    
    logger.info("=" * 80)
    
    # Confirm before starting
    logger.warning("\n⚠️  IMPORTANT: This will perform exhaustive data collection!")
    logger.warning("This may take considerable time and make many API requests.")
    logger.warning("Press Ctrl+C within 5 seconds to cancel...")
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        logger.info("\nCancelled by user")
        sys.exit(0)
    
    # Start harvest
    start_time = time.time()
    
    try:
        stats = engine.deep_harvest(track_id)
        
        # Report final statistics
        elapsed = time.time() - start_time
        
        logger.info("\n" + "=" * 80)
        logger.success("🎉 DEEP HARVEST COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"Elapsed Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        logger.info(f"Cache Size: {cache.get_cache_stats()}")
        logger.info("=" * 80)
        
        logger.info("\n📊 HARVEST STATISTICS:")
        logger.info("-" * 80)
        for key, value in stats.items():
            logger.info(f"{key:30s}: {value:,}")
        logger.info("-" * 80)
        
        # Calculate density metrics
        total_items = (
            stats.get('tracks_collected', 0) +
            stats.get('users_collected', 0) +
            stats.get('playlists_collected', 0)
        )
        
        logger.info(f"\n{'Total Items Collected':30s}: {total_items:,}")
        logger.info(f"{'Items per API Request':30s}: {total_items / max(stats.get('api_requests', 1), 1):.2f}")
        logger.info(f"{'Data Density Score':30s}: {total_items / max(elapsed, 1):.2f} items/second")
        
        logger.info("\n" + "=" * 80)
        logger.success("✅ Data lake established - ready for relationship building!")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("  1. Review collected data in cache database")
        logger.info("  2. Build relationships using post-ingestion processing")
        logger.info("  3. Generate embeddings/vectors from dense data")
        logger.info("=" * 80)
        
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Harvest interrupted by user")
        logger.info("Partial data has been saved to cache")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"\n❌ Error during harvest: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        cache.close()


if __name__ == "__main__":
    main()
