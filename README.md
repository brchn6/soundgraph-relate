# 🌊 SoundGraph-Relate: Deep Harvest Engine

A high-performance data ingestion engine for SoundCloud. This tool performs aggressive, recursive data collection to build a comprehensive local database of tracks, users, and interactions.

## Philosophy

**"Deep Harvest First, Analyze Later"**

Instead of trying to build relationships and graphs on-the-fly, we focus on one thing: **maximum data density**. Harvest everything available from a seed track, store it in a local SQLite database, then build analytics later when you have a solid foundation.

## What It Does

Starting from a single SoundCloud track URL, the Deep Harvest Engine:

1. **Seed Phase**: Resolves the track and fetches artist details
2. **Social Spill Phase**: Fetches ALL users who liked or reposted the track (handles pagination automatically)
3. **User Depth Phase**: For each discovered user, fetches their complete library of liked tracks

Everything is immediately written to a local SQLite database for persistent storage.

## Quick Start

### Prerequisites

- Python 3.11+
- SoundCloud OAuth Access Token

### Installation

```bash
git clone https://github.com/brchn6/soundgraph-relate.git
cd soundgraph-relate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the root directory:

```env
SOUNDCLOUD_ACCESS_TOKEN=your_oauth_token_here
SOUNDCLOUD_CLIENT_ID=your_client_id_here
SOUNDCLOUD_REFRESH_TOKEN=your_refresh_token_here  # optional
SOUNDCLOUD_CLIENT_SECRET=your_client_secret_here  # optional
```

### Usage

```bash
# Basic usage
python scripts/harvest.py https://soundcloud.com/artist/track-name

# With custom parameters
python scripts/harvest.py https://soundcloud.com/artist/track-name \
    --max-users 2000 \
    --max-user-likes 1000 \
    --delay 1.0

# Custom cache location
python scripts/harvest.py https://soundcloud.com/artist/track-name \
    --cache-path /path/to/my/database.db
```

### Parameters

- `url` (required): SoundCloud track URL to start harvesting from
- `--cache-path`: Path to SQLite database (default: `data/cache/tracks.db`)
- `--max-users`: Maximum users to fetch per track (default: 1000)
- `--max-user-likes`: Maximum likes to fetch per user (default: 500)
- `--delay`: Delay between API requests in seconds (default: 0.5)

## How It Works

### Three-Phase Crawl

```
Phase 1: Seed
    ↓
    Resolve Track URL → Get Track Metadata
    Cache Track + Artist
    
Phase 2: Social Spill
    ↓
    Fetch ALL Likers (paginated)
    Fetch ALL Reposters (paginated)
    Cache All Users
    Record Engagements
    
Phase 3: User Depth
    ↓
    For Each User:
        Fetch ALL Liked Tracks (paginated)
        Cache All Tracks
        Record Engagements
```

### Database Schema

The SQLite database (`data/cache/tracks.db`) contains:

- **tracks**: Track metadata (title, artist, genre, tags, plays, likes, etc.)
- **users**: User profiles (username, followers, etc.)
- **user_engagements**: Who liked/reposted what track
- **playlists**: Playlist metadata
- **playlist_tracks**: Track-to-playlist relationships
- **related_tracks**: Track-to-track relationships
- **user_similarity**: User similarity scores
- **artist_relationships**: Artist collaboration networks

### Safety & Rate Limiting

- Built-in retry mechanism with exponential backoff
- Configurable delay between API requests
- Automatic pagination handling
- Graceful error handling (continues on failures)
- OAuth token auto-refresh support
- Resumable (all data written immediately to database)

## Output

After running the harvest, you'll see:

```
🎉 DEEP HARVEST COMPLETE!
================================================================================
Total Time: 145.2s (2.4 minutes)
Tracks Collected: 15,234
Users Collected: 987
Likes Collected: 987
Reposts Collected: 234
API Calls: 456
Data Density: 104.89 tracks/sec
================================================================================

📊 DATABASE STATISTICS:
--------------------------------------------------------------------------------
tracks                        : 15,234
users                         : 987
playlists                     : 0
relationships                 : 0
user_engagements              : 1,221
user_similarities             : 0
artist_relationships          : 0
user_follows                  : 0
================================================================================
```

## Project Structure

```
soundgraph-relate/
├── scripts/
│   └── harvest.py           # Main deep harvest script
├── src/sgr/
│   ├── io/
│   │   └── soundcloud_client.py    # SoundCloud API client
│   └── cache/
│       └── track_cache.py          # SQLite database cache
├── data/
│   └── cache/
│       └── tracks.db        # SQLite database (created on first run)
├── requirements.txt         # Python dependencies
├── .env                     # Configuration (create this)
└── README.md               # This file
```

## Next Steps

Once you have harvested data:

1. **Query the database** - Use any SQLite client to explore the data
2. **Build relationships** - Analyze co-occurrence patterns, user similarity, etc.
3. **Create embeddings** - Generate vectors from the dense metadata
4. **Train models** - Use the data for recommendation systems, clustering, etc.

## Performance Tips

- **Start small**: Test with `--max-users 100` first
- **Increase delay**: Use `--delay 1.0` or higher if you hit rate limits
- **Batch processing**: Harvest multiple seed tracks into the same database
- **Monitor progress**: The script logs progress for every user processed

## Troubleshooting

### "Missing env var: SOUNDCLOUD_ACCESS_TOKEN"

Make sure you have created a `.env` file with your SoundCloud credentials.

### Rate Limiting / 429 Errors

Increase the `--delay` parameter to slow down requests:
```bash
python scripts/harvest.py <URL> --delay 2.0
```

### Database Locked

Make sure only one harvest script is running at a time. Close any SQLite connections to the database.

## License

MIT License

---

**Built for maximum data density and ingestion speed.**
