#!/usr/bin/env python
"""
Build a personal music knowledge graph from a seed track.

This script demonstrates the new user-driven architecture:
1. User provides a seed track URL
2. Smart expansion collects related tracks via playlists
3. Data is cached locally in SQLite
4. Personal graph is built using NetworkX
5. User can query, visualize, and get recommendations

Usage:
    # Basic usage - build graph from a track
    TRACK_URL="https://soundcloud.com/artist/track" python scripts/build_personal_graph.py
    
    # With custom depth and max tracks
    TRACK_URL="https://soundcloud.com/artist/track" DEPTH=2 MAX_TRACKS=1000 python scripts/build_personal_graph.py
    
    # Visualize the graph
    TRACK_URL="https://soundcloud.com/artist/track" VISUALIZE=true python scripts/build_personal_graph.py
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml
import json

from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache.track_cache import TrackCache
from sgr.collectors.smart_expansion import SmartExpander
from sgr.graph.personal_graph import PersonalGraph


def main():
    """Main entry point for building personal graphs."""
    load_dotenv()
    
    # Load configuration
    cfg = yaml.safe_load(open("configs/config.yaml"))
    
    # Get parameters from environment
    track_url = os.getenv("TRACK_URL")
    if not track_url:
        logger.error("TRACK_URL environment variable is required")
        print("\nUsage:")
        print('  TRACK_URL="https://soundcloud.com/artist/track" python scripts/build_personal_graph.py')
        print("\nOptional parameters:")
        print("  DEPTH=2              # Expansion depth (default: 1)")
        print("  MAX_TRACKS=500       # Maximum tracks to collect (default: 500)")
        print("  VISUALIZE=true       # Create visualization (default: false)")
        print("  CACHE_PATH=path      # Custom cache path (default: data/cache/tracks.db)")
        sys.exit(1)
    
    depth = int(os.getenv("DEPTH", "1"))
    max_tracks = int(os.getenv("MAX_TRACKS", "500"))
    visualize = os.getenv("VISUALIZE", "").lower() in ("true", "1", "yes")
    cache_path = os.getenv("CACHE_PATH", "data/cache/tracks.db")
    
    logger.info("=" * 60)
    logger.info("🎵 Building Personal Music Graph")
    logger.info("=" * 60)
    logger.info(f"Seed Track: {track_url}")
    logger.info(f"Expansion Depth: {depth}")
    logger.info(f"Max Tracks: {max_tracks}")
    logger.info(f"Cache Path: {cache_path}")
    logger.info("=" * 60)
    
    # Initialize components
    sc_client = make_client_from_env()
    cache = TrackCache(cache_path)
    expander = SmartExpander(
        sc_client, 
        cache,
        max_playlists_per_artist=20,
        max_tracks_per_playlist=100,
        min_playback_count=1000  # Only include tracks with at least 1k plays
    )
    
    # Step 1: Expand the graph
    logger.info("\n📊 Step 1: Expanding graph from seed track...")
    try:
        expansion_result = expander.expand_from_url(track_url, depth=depth, max_tracks=max_tracks)
        
        logger.success("✅ Expansion complete!")
        logger.info(f"  • Tracks collected: {expansion_result['tracks_collected']}")
        logger.info(f"  • Playlists processed: {expansion_result['playlists_processed']}")
        logger.info(f"  • Relationships created: {expansion_result['relationships_created']}")
        logger.info(f"  • Artists visited: {expansion_result['artists_visited']}")
        
    except Exception as e:
        logger.error(f"Error during expansion: {e}")
        sys.exit(1)
    
    # Step 2: Build NetworkX graph
    logger.info("\n🕸️  Step 2: Building NetworkX graph...")
    personal_graph = PersonalGraph(cache)
    
    seed_track_id = expansion_result["seed_track_id"]
    graph_stats = personal_graph.build_from_seed(seed_track_id, max_depth=depth)
    
    logger.success("✅ Graph built!")
    logger.info(f"  • Nodes: {graph_stats['nodes']}")
    logger.info(f"  • Edges: {graph_stats['edges']}")
    
    # Step 3: Get cache statistics
    cache_stats = cache.get_cache_stats()
    logger.info("\n💾 Cache Statistics:")
    logger.info(f"  • Tracks: {cache_stats['tracks']}")
    logger.info(f"  • Users: {cache_stats['users']}")
    logger.info(f"  • Playlists: {cache_stats['playlists']}")
    logger.info(f"  • Relationships: {cache_stats['relationships']}")
    
    # Step 4: Get recommendations
    logger.info("\n🎯 Top Recommendations:")
    recommendations = personal_graph.get_recommendations(seed_track_id, limit=10)
    
    if recommendations:
        for i, rec in enumerate(recommendations[:5], 1):
            logger.info(f"  {i}. {rec['title']} by {rec['artist_name']}")
            logger.info(f"     Score: {rec['score']:.2f}, Common neighbors: {rec['common_neighbors']}")
    else:
        logger.info("  No recommendations available (graph may be too small)")
    
    # Step 5: Get direct neighbors
    logger.info("\n🔗 Direct Neighbors:")
    neighbors = personal_graph.get_neighbors(seed_track_id, limit=5)
    
    if neighbors:
        for i, neighbor in enumerate(neighbors, 1):
            logger.info(f"  {i}. {neighbor['title']} by {neighbor['artist_name']}")
            logger.info(f"     Relation: {neighbor['relation']}, Weight: {neighbor['weight']:.3f}")
    else:
        logger.info("  No direct neighbors found")
    
    # Step 6: Export graph to JSON
    output_dir = Path("data/graphs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a safe filename from track URL
    safe_name = track_url.split("/")[-1][:50]  # Last part of URL
    json_path = output_dir / f"graph_{safe_name}_{seed_track_id}.json"
    
    personal_graph.export_to_json(json_path)
    logger.info(f"\n💾 Graph exported to: {json_path}")
    
    # Step 7: Visualize (optional)
    if visualize:
        logger.info("\n🎨 Creating visualization...")
        viz_path = output_dir / f"graph_{safe_name}_{seed_track_id}.png"
        try:
            personal_graph.visualize(viz_path, highlight_nodes={seed_track_id})
            logger.success(f"✅ Visualization saved to: {viz_path}")
        except Exception as e:
            logger.error(f"Error creating visualization: {e}")
    
    # Step 8: Summary
    logger.info("\n" + "=" * 60)
    logger.info("✨ Personal Graph Build Complete!")
    logger.info("=" * 60)
    logger.info(f"Seed Track ID: {seed_track_id}")
    logger.info(f"Graph Size: {graph_stats['nodes']} nodes, {graph_stats['edges']} edges")
    logger.info(f"Cache Location: {cache_path}")
    logger.info(f"Graph Export: {json_path}")
    
    if recommendations:
        logger.info(f"\n🎵 Try these tracks:")
        for rec in recommendations[:3]:
            if rec.get("permalink_url"):
                logger.info(f"  • {rec['permalink_url']}")
    
    logger.info("\n💡 Next steps:")
    logger.info("  • Run again with DEPTH=2 for deeper exploration")
    logger.info("  • Use VISUALIZE=true to see the graph")
    logger.info("  • Explore the cache database at " + cache_path)
    logger.info("=" * 60)
    
    cache.close()


if __name__ == "__main__":
    main()
