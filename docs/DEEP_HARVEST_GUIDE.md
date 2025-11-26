# Deep Harvest Engine - Complete Guide

## Overview

The **Deep Harvest Engine** is a complete rearchitecture of SoundGraph-Relate's data collection system. It solves the fundamental problem of **data sparsity** by implementing an aggressive "spill-first" approach: exhaustive data collection precedes relationship building.

## Philosophy: "Spill-First, Connect Later"

### The Problem with Traditional Approaches

The original multi-layer system had limitations:
- **Shallow data collection**: Limited to 50 likers, 100 tracks per user
- **On-the-fly processing**: Attempted to build relationships during collection
- **Artificial constraints**: Hard-coded limits prevented complete data capture
- **Sparse graphs**: Insufficient data led to poor relationship quality

### The Deep Harvest Solution

**Priority: Data Density Over Speed**

1. **Exhaustive Collection**: Fetch ALL available data (up to 500 users, 500 tracks each)
2. **Immediate Persistence**: "Spill" everything to database before processing
3. **Deferred Relationships**: Build connections only after data lake is complete
4. **ML-Ready Output**: Dense data suitable for embeddings and vectors

## Architecture

```
Seed Track → Deep Harvest Engine → Dense Data Lake → Post-Ingestion Processor → Relationships & Vectors
```

### Phase 1: Deep Harvest (Data Collection)

The Deep Harvest Engine performs 7 types of exhaustive crawls:

#### 1. User Depth Harvest
**Goal**: Capture complete user engagement ecosystem

**What it does**:
- Fetches ALL users who liked the track (up to 500)
- Fetches ALL users who reposted the track (up to 500)
- For EACH user, fetches their ENTIRE library of likes (up to 500 tracks)
- Creates user engagement records in database

**Why it matters**:
- Solves "sparse user data" problem
- Captures complete taste profiles
- Enables accurate user similarity calculations

**Example**:
```
Track has 100 likers → Fetch all 100 users
Each user has 200 liked tracks → Fetch 200 × 100 = 20,000 track records
Result: Dense user-track interaction matrix
```

#### 2. Playlist Depth Harvest
**Goal**: Discover ALL playlists containing the track

**What it does**:
- Searches artist's playlists
- Checks top likers' playlists
- Harvests ALL tracks from each playlist (up to 500 per playlist)
- Creates playlist-track relationship records

**Why it matters**:
- Traditional co-occurrence data
- Captures curator taste patterns
- Enables playlist-based recommendations

#### 3. Artist Depth Harvest
**Goal**: Complete discography of track creator

**What it does**:
- Identifies track's artist
- Searches for ALL tracks by this artist (up to 1,000)
- Includes remixes and features
- Captures complete creative output

**Why it matters**:
- Artist similarity and style analysis
- Fan discovery patterns
- Cross-track recommendations

#### 4. Semantic Depth Harvest
**Goal**: Find semantically similar tracks via fuzzy name matching

**What it does**:
- Extracts key terms from track title
- Searches for tracks with similar names
- Uses fuzzy string matching (60% similarity threshold)
- Captures remixes, covers, variations

**Example**:
```
Seed: "Lofi Beats to Study To"
Finds: "Lofi Study Beats", "Study Music Lofi", "Lofi Beats Mix"
```

**Why it matters**:
- Catches tracks missed by other methods
- Discovers semantic relationships
- Improves recall for similar content

#### 5. Commentary Layer (High-Engagement Users)
**Goal**: Identify super-fans through comments

**What it does**:
- Fetches users who commented on track (when API allows)
- Commenters = high-engagement users
- Harvests their complete libraries

**Why it matters**:
- Comments indicate deep engagement
- Super-fans have valuable taste data
- Better quality recommendations

**Status**: Limited by SoundCloud API v1 availability

#### 6. Label/Network Layer
**Goal**: Discover and harvest entire label/collective catalogs

**What it does**:
- Detects labels from:
  - Official label field
  - Description parsing (regex patterns)
  - Publisher metadata
- Searches for entire label catalog (up to 200 tracks per label)

**Example**:
```
Track mentions "Released by Chillhop Records"
→ Searches "Chillhop Records"
→ Harvests their entire catalog
→ Establishes "scene" baseline
```

**Why it matters**:
- Captures genre/style communities
- Label artists often collaborate
- Establishes musical "scenes"

#### 7. Contextual Entity Layer
**Goal**: Extract and crawl mentioned artists/collaborators

**What it does**:
- Parses description and title for:
  - @mentions (@username)
  - Featured artists ("feat.", "ft.", "featuring")
  - Remixers ("remix by", "remixed by")
  - Producers ("prod. by", "produced by")
- Treats each entity as new seed point
- Harvests tracks for each entity (up to 50 per entity)

**Example**:
```
Title: "Summer Vibes (feat. Artist X) [Remix by DJ Y]"
Extracts: ["Artist X", "DJ Y"]
Searches and harvests tracks for both
```

**Why it matters**:
- Discovers collaboration networks
- Captures creative relationships
- Expands graph organically

### Phase 2: Post-Ingestion Processing (Relationship Building)

After harvest is complete, the Post-Ingestion Processor builds relationships from the dense data:

#### 1. User-User Similarities
- Computes Jaccard similarity for all user pairs
- Based on shared liked tracks
- Formula: `similarity = |shared tracks| / |total unique tracks|`
- Stores only meaningful similarities (>= 0.1)

#### 2. Track-Track Co-occurrence
- Counts how often tracks appear together in playlists
- Creates weighted relationships
- Weight normalized by frequency

#### 3. Artist-Artist Relationships
- Analyzes co-occurrence in user libraries
- "Artists whose tracks appear together in fan libraries are related"
- Strength based on evidence count

## Configuration

### Deep Harvest Configuration

```yaml
deep_harvest:
  enabled: true
  request_delay: 0.3  # Slower but safer
  
  user_depth:
    max_users_per_track: 500      # 10x increase from 50
    max_tracks_per_user: 500      # 5x increase from 100
    include_reposters: true
  
  playlist_depth:
    max_playlists: 200            # 10x increase from 20
    max_tracks_per_playlist: 500  # 5x increase from 100
  
  artist_depth:
    max_artist_tracks: 1000       # Complete discography
  
  semantic_depth:
    fuzzy_search_limit: 100
    name_similarity_threshold: 0.6
  
  label_layer:
    max_labels_per_track: 3
    max_catalog_size: 200
  
  contextual_layer:
    max_entities: 10
    max_tracks_per_entity: 50
```

## Usage

### Basic Usage

```bash
# Run deep harvest on a track
TRACK_URL="https://soundcloud.com/artist/track" python scripts/deep_harvest.py

# Or with track ID
TRACK_ID=12345 python scripts/deep_harvest.py
```

### With Custom Configuration

```bash
# Use custom config file
TRACK_URL="..." CONFIG_FILE=configs/harvest_config.yaml python scripts/deep_harvest.py

# Custom cache path
TRACK_URL="..." CACHE_PATH=data/my_cache.db python scripts/deep_harvest.py
```

### Complete Workflow

```python
from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache.track_cache import TrackCache
from sgr.collectors.deep_harvest import DeepHarvestEngine
from sgr.processors.post_ingestion import PostIngestionProcessor
import yaml

# 1. Setup
sc_client = make_client_from_env()
cache = TrackCache("data/cache/tracks.db")
config = yaml.safe_load(open("configs/config.yaml"))

# 2. Initialize Deep Harvest Engine
harvest_config = config["deep_harvest"]
engine = DeepHarvestEngine(sc_client, cache, harvest_config)

# 3. Run exhaustive data collection
stats = engine.deep_harvest(track_id=12345)

print(f"Collected:")
print(f"  - {stats['tracks_collected']:,} tracks")
print(f"  - {stats['users_collected']:,} users")
print(f"  - {stats['playlists_collected']:,} playlists")

# 4. Build relationships from collected data
processor = PostIngestionProcessor(cache)
relationship_stats = processor.process_all(seed_track_id=12345)

print(f"Relationships:")
print(f"  - {relationship_stats['user_similarities']:,} user similarities")
print(f"  - {relationship_stats['track_relationships']:,} track relationships")
print(f"  - {relationship_stats['artist_relationships']:,} artist relationships")

# 5. Data is now ready for ML/embeddings
ml_data = processor.prepare_for_embeddings()
```

## Performance Characteristics

### API Requests

For a single seed track with 100 likers:

- **User Depth**: ~100 (users) + ~100 × 10 (user libraries) = ~1,100 requests
- **Playlist Depth**: ~50 (playlists)
- **Artist Depth**: ~20 (discography searches)
- **Semantic Depth**: ~3 (key term searches)
- **Label Layer**: ~3 (label catalog searches)
- **Contextual Layer**: ~10 (entity searches)

**Total**: ~1,186 API requests per seed track

### Rate Limiting

- Default: 0.3 seconds between requests
- Total time: ~1,186 × 0.3s = ~6 minutes for complete harvest
- Configurable via `request_delay` parameter

### Data Volume

Expected data for typical track:

- **Tracks**: 5,000-20,000 track records
- **Users**: 100-500 user records
- **Playlists**: 50-200 playlist records
- **Engagements**: 10,000-50,000 engagement records

## Comparison: Deep Harvest vs. Multi-Layer

| Aspect | Multi-Layer (Old) | Deep Harvest (New) |
|--------|------------------|-------------------|
| **Philosophy** | Build relationships during collection | Collect first, connect later |
| **Users per track** | 50 | 500 (10x) |
| **Tracks per user** | 100 | 500 (5x) |
| **Artist tracks** | Limited | 1,000 (complete) |
| **Semantic search** | No | Yes (fuzzy matching) |
| **Label catalogs** | No | Yes (entire catalogs) |
| **Entity extraction** | No | Yes (collaborators) |
| **Processing** | Real-time | Post-ingestion |
| **Data density** | Sparse | Dense |
| **ML readiness** | Limited | High |

## Benefits

### 1. Solves Sparsity Problem

**Before**: 50 users × 100 tracks = 5,000 data points
**After**: 500 users × 500 tracks = 250,000 data points (50x increase)

### 2. Better Relationship Quality

More data → More overlap → Higher confidence similarities

### 3. ML/Embedding Ready

Dense interaction matrices suitable for:
- Matrix factorization
- Graph neural networks
- Word2Vec-style embeddings
- Collaborative filtering

### 4. Transparent & Auditable

All data persisted to database:
- Can inspect what was collected
- Can reprocess relationships without re-fetching
- Can experiment with different similarity metrics

### 5. Incremental Processing

- Fetch once, process many times
- Can add new relationship types without re-fetching
- Can tune thresholds without re-crawling

## Limitations & Future Work

### Current Limitations

1. **API Rate Limits**: Aggressive fetching may hit limits
2. **Storage**: Dense data requires more disk space
3. **Processing Time**: Post-ingestion can be slow for large datasets
4. **Comment API**: Limited by SoundCloud v1 API availability

### Future Enhancements

1. **Parallel Processing**: Multi-threaded harvesting
2. **Incremental Updates**: Smart delta updates
3. **Distributed Crawling**: Multiple API keys for faster collection
4. **Advanced Embeddings**: Graph neural network integration
5. **Real-time Mode**: Stream processing for live updates

## Troubleshooting

### "Too many API requests"

- Increase `request_delay` in config
- Reduce max limits (e.g., `max_users_per_track`)
- Use API key rotation

### "Out of disk space"

- Enable selective harvesting (disable some layers)
- Implement data retention policies
- Use database compression

### "Processing too slow"

- Reduce similarity computation scope
- Use sampling for large user bases
- Implement parallel processing

## Migration from Multi-Layer

To migrate from the old multi-layer system:

1. **Keep both systems**: Deep Harvest doesn't replace multi-layer
2. **Use for new seeds**: Start using Deep Harvest for new tracks
3. **Gradual adoption**: Enable layers one at a time
4. **Compare results**: Validate relationship quality improvements

## Conclusion

The Deep Harvest Engine represents a paradigm shift from "smart sampling" to "exhaustive collection". By prioritizing data density and deferring relationship building, it creates a rich, ML-ready dataset that solves the fundamental sparsity problem plaguing music recommendation systems.

**Key Takeaway**: Get ALL the data first, then make sense of it.
