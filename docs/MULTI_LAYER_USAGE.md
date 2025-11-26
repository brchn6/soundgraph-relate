# Multi-Layer Relationship System - Usage Guide

This guide demonstrates how to use the new multi-layer relationship system in SoundGraph-Relate.

## Overview

The multi-layer system extends SoundGraph from a single-layer playlist co-occurrence system to a rich 4-layer music relationship graph:

- **Layer 1**: Track-to-Track (playlist co-occurrence) - *existing*
- **Layer 2**: User-to-Track (likes, reposts, plays) - *new*
- **Layer 3**: User-to-User (taste similarity, follows) - *new*
- **Layer 4**: Artist-to-Artist (collaborations, co-library) - *new*

## Configuration

### Enable Multi-Layer Collection

Edit `configs/config.yaml`:

```yaml
multi_layer:
  enabled_layers:
    layer1_playlist_cooccurrence: true
    layer2_user_engagement: true
    layer3_user_similarity: true
    layer4_artist_collaboration: true
  
  layer2:
    max_likers_per_track: 50
    max_tracks_per_user: 100
    min_likes_threshold: 10
  
  layer3:
    min_common_tracks: 3
    min_similarity_score: 0.1
  
  layer4:
    min_collaboration_evidence: 2
```

## Basic Usage

### 1. Layer 1 Only (Backward Compatible)

```python
from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache.track_cache import TrackCache
from sgr.collectors.smart_expansion import SmartExpander
from sgr.graph.personal_graph import PersonalGraph

# Initialize
sc_client = make_client_from_env()
cache = TrackCache("data/cache/tracks.db")

# Expand with Layer 1 only (existing behavior)
expander = SmartExpander(sc_client, cache)
results = expander.expand_from_url(
    "https://soundcloud.com/artist/track",
    depth=1,
    max_tracks=500
)

# Build graph (Layer 1 only)
graph = PersonalGraph(cache)
stats = graph.build_from_seed(results["seed_track_id"], max_depth=2)
print(f"Built graph: {stats['nodes']} nodes, {stats['edges']} edges")
```

### 2. Multi-Layer Collection

```python
import yaml
from sgr.collectors.smart_expansion import SmartExpander

# Load multi-layer config
config = yaml.safe_load(open("configs/config.yaml"))
ml_config = config.get("multi_layer", {})

# Initialize with multi-layer support
expander = SmartExpander(
    sc_client, cache,
    multi_layer_config=ml_config
)

# Expand (will collect all enabled layers)
results = expander.expand_from_url(
    "https://soundcloud.com/chillhop/lofi-beats",
    depth=1,
    max_tracks=500
)

# Check multi-layer results
if "multi_layer" in results:
    ml = results["multi_layer"]
    print(f"Layer 2: {ml['layer2']['total_engagements']} engagements")
    print(f"Layer 3: {ml['layer3']['total_similarities']} similarities")
    print(f"Layer 4: {ml['layer4']['relationships_created']} artist relationships")
```

### 3. Multi-Layer Graph Building

```python
# Build graph with all layers
graph = PersonalGraph(cache, enable_multi_layer=True)

# Specify which layers to include
stats = graph.build_from_seed(
    seed_track_id=12345,
    max_depth=2,
    layers={1, 2, 3, 4}  # All layers
)

print(f"Track nodes: {stats['track_nodes']}")
print(f"User nodes: {stats['user_nodes']}")
print(f"Artist nodes: {stats['artist_nodes']}")

if 'layer1_edges' in stats:
    print(f"Layer 1 edges: {stats['layer1_edges']}")
    print(f"Layer 2 edges: {stats['layer2_edges']}")
    print(f"Layer 3 edges: {stats['layer3_edges']}")
    print(f"Layer 4 edges: {stats['layer4_edges']}")
```

## Advanced Queries

### Layer 2: Find Tracks via User Engagement

```python
# Find tracks that users who liked this track also liked
track_id = 12345
related_via_users = graph.get_track_via_user_path(track_id, limit=10)

for track in related_via_users:
    print(f"{track['title']} by {track['artist_name']}")
    print(f"  Via user: {track['via_user']}")
```

### Layer 3: Find Similar Users

```python
# Find users with similar taste based on a track
similar_users = graph.get_similar_users_for_track(track_id, limit=10)

for user in similar_users:
    print(f"{user['username']}")
    print(f"  Similarity score: {user['similarity_score']:.2f}")
    print(f"  Common tracks: {user['common_tracks']}")
```

### Layer 4: Find Artist Collaborations

```python
# Find artists related to the track's artist
collaborations = graph.get_artist_collaborations(track_id)

for collab in collaborations:
    print(f"{collab['artist_name']}")
    print(f"  Relationship: {collab['relationship_type']}")
    print(f"  Strength: {collab['strength']:.2f}")
```

### Multi-Layer Path Finding

```python
# Find path between two tracks through any relationship type
path = graph.get_multi_layer_path(
    src_id=track_id_1,
    dst_id=track_id_2,
    max_length=5
)

if path:
    for node_id, relation in path:
        print(f"{node_id} --[{relation}]-->")
```

### Filter by Layer

```python
# Get only Layer 2 neighbors (users who engaged)
user_neighbors = graph.get_neighbors(track_id, limit=10, layer=2)

for neighbor in user_neighbors:
    if neighbor['node_type'] == 'user':
        print(f"User: {neighbor['username']}")
        print(f"  Relation: {neighbor['relation']}")
```

## Direct Database Queries

### Query User Engagements

```python
from sgr.cache.track_cache import TrackCache

cache = TrackCache("data/cache/tracks.db")

# Get all users who liked a track
likers = cache.get_track_engagers(track_id, engagement_type="like", limit=50)
print(f"Found {len(likers)} users who liked this track")

# Get all tracks a user liked
user_id = 12345
liked_tracks = cache.get_user_liked_tracks(user_id, limit=100)
print(f"User liked {len(liked_tracks)} tracks")
```

### Query User Similarities

```python
# Find similar users
similar = cache.get_similar_users(
    user_id,
    similarity_type="jaccard_likes",
    min_score=0.3,
    limit=20
)

for user in similar:
    print(f"{user['username']}: {user['similarity_score']:.2f}")
```

### Query Artist Relationships

```python
# Get related artists
artist_id = 67890
related = cache.get_related_artists(
    artist_id,
    relationship_type="co_library",
    min_strength=0.5,
    limit=20
)

for artist in related:
    print(f"Artist {artist['related_artist_id']}")
    print(f"  Strength: {artist['strength']:.2f}")
    print(f"  Evidence: {artist['evidence_count']}")
```

## Programmatic Layer Control

### Collect Specific Layers Only

```python
from sgr.collectors.multi_layer_collector import (
    Layer2Collector,
    Layer3Collector,
    Layer4Collector
)

# Configure Layer 2 only
layer2_config = {
    "max_likers_per_track": 50,
    "max_tracks_per_user": 100,
    "min_likes_threshold": 10,
    "collect_reposts": True
}

layer2 = Layer2Collector(sc_client, cache, layer2_config)

# Collect engagements for a specific track
stats = layer2.collect_track_engagers(track_id)
print(f"Collected {stats['likers_collected']} likers")
print(f"Collected {stats['reposters_collected']} reposters")
```

### Calculate User Similarity

```python
# Layer 3: Calculate similarity between specific users
layer3_config = {
    "min_common_tracks": 3,
    "min_similarity_score": 0.1
}

layer3 = Layer3Collector(sc_client, cache, layer3_config)

# Find similar users for a track
stats = layer3.find_similar_users_for_track(track_id)
print(f"Computed {stats['similarities_computed']} similarities")
```

### Detect Artist Relationships

```python
# Layer 4: Detect artist relationships
layer4_config = {
    "min_collaboration_evidence": 2
}

layer4 = Layer4Collector(sc_client, cache, layer4_config)

# Detect co-occurrence in playlists
track_ids = [1001, 1002, 1003, 1004]
stats = layer4.detect_artist_cooccurrence(track_ids)
print(f"Found {stats['artist_pairs_found']} artist pairs")
print(f"Created {stats['relationships_created']} relationships")
```

## Complete Example: Multi-Layer Discovery

```python
import yaml
from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache.track_cache import TrackCache
from sgr.collectors.smart_expansion import SmartExpander
from sgr.graph.personal_graph import PersonalGraph

# 1. Setup
sc_client = make_client_from_env()
cache = TrackCache("data/cache/tracks.db")
config = yaml.safe_load(open("configs/config.yaml"))

# 2. Expand with all layers
expander = SmartExpander(
    sc_client, cache,
    multi_layer_config=config.get("multi_layer", {})
)

results = expander.expand_from_url(
    "https://soundcloud.com/lofi/chill-beats",
    depth=1,
    max_tracks=500
)

seed_track_id = results["seed_track_id"]

# 3. Build multi-layer graph
graph = PersonalGraph(cache, enable_multi_layer=True)
stats = graph.build_from_seed(seed_track_id, max_depth=2, layers={1, 2, 3, 4})

# 4. Query all layers
print("\n=== Layer 1: Related Tracks ===")
related_tracks = graph.get_neighbors(seed_track_id, layer=1, limit=5)
for track in related_tracks:
    if track['node_type'] == 'track':
        print(f"  {track['title']} (weight: {track['weight']:.2f})")

print("\n=== Layer 2: Tracks via Users ===")
user_tracks = graph.get_track_via_user_path(seed_track_id, limit=5)
for track in user_tracks:
    print(f"  {track['title']} (via {track['via_user']})")

print("\n=== Layer 3: Similar Users ===")
similar_users = graph.get_similar_users_for_track(seed_track_id, limit=5)
for user in similar_users:
    print(f"  {user['username']} (score: {user['similarity_score']:.2f})")

print("\n=== Layer 4: Artist Collaborations ===")
collaborations = graph.get_artist_collaborations(seed_track_id)
for collab in collaborations:
    print(f"  {collab['artist_name']} ({collab['relationship_type']})")

# 5. Export graph
graph.export_to_json(f"data/graphs/multi_layer_{seed_track_id}.json")

# 6. Get comprehensive stats
stats = graph.get_graph_stats()
print(f"\n=== Graph Statistics ===")
print(f"Total nodes: {stats['nodes']}")
print(f"  - Tracks: {stats['track_nodes']}")
print(f"  - Users: {stats['user_nodes']}")
print(f"  - Artists: {stats['artist_nodes']}")
print(f"Total edges: {stats['edges']}")
if 'layer1_edges' in stats:
    print(f"  - Layer 1: {stats['layer1_edges']}")
    print(f"  - Layer 2: {stats['layer2_edges']}")
    print(f"  - Layer 3: {stats['layer3_edges']}")
    print(f"  - Layer 4: {stats['layer4_edges']}")

cache.close()
```

## Performance Tips

### 1. Disable Unused Layers

If you don't need all layers, disable them in config:

```yaml
multi_layer:
  enabled_layers:
    layer1_playlist_cooccurrence: true
    layer2_user_engagement: false  # Disable
    layer3_user_similarity: false  # Disable
    layer4_artist_collaboration: true
```

### 2. Adjust Collection Limits

Reduce API calls by lowering limits:

```yaml
layer2:
  max_likers_per_track: 20  # Lower from 50
  max_tracks_per_user: 50   # Lower from 100
```

### 3. Use Selective Layer Queries

Query specific layers instead of all:

```python
# Only get Layer 1 neighbors (fast)
neighbors = graph.get_neighbors(track_id, layer=1, limit=10)
```

### 4. Cache Statistics

Check what's already collected:

```python
stats = cache.get_cache_stats()
print(f"User engagements: {stats['user_engagements']}")
print(f"User similarities: {stats['user_similarities']}")
print(f"Artist relationships: {stats['artist_relationships']}")
```

## Troubleshooting

### "No multi-layer data found"

Make sure to:
1. Enable layers in config
2. Run expansion with `multi_layer_config`
3. Enable multi-layer in PersonalGraph: `PersonalGraph(cache, enable_multi_layer=True)`

### "Layer X edges: 0"

- Check if layer is enabled in config
- Verify minimum thresholds aren't too high
- Ensure API client has necessary permissions

### Performance Issues

- Reduce depth and max_tracks
- Disable unused layers
- Lower per-layer limits
- Use selective queries

## See Also

- [Graph Database Migration Guide](GRAPH_DATABASE_MIGRATION.md)
- [Configuration Reference](../configs/config.yaml)
- [API Documentation](../src/sgr/)
