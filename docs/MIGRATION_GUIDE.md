# Migration Guide: Bulk Mode → Personal Graph Mode

This guide helps existing SoundGraph users transition to the new Personal Graph Mode.

## 🔄 Overview

SoundGraph now offers two modes:
- **Personal Graph Mode** (NEW): On-demand, SQLite-based, no PostgreSQL required
- **Bulk Collection Mode** (LEGACY): PostgreSQL-based, for large-scale production use

## 🎯 Should You Migrate?

**Migrate to Personal Graph Mode if:**
- ✅ You're exploring music discovery for personal use
- ✅ You want faster iteration and simpler setup
- ✅ You don't need to store millions of tracks
- ✅ You prefer local caching over database management

**Stay with Bulk Collection Mode if:**
- ⚠️ You need PostgreSQL for other integrations
- ⚠️ You're building production recommendation systems
- ⚠️ You need to query across 100,000+ tracks
- ⚠️ You have existing PostgreSQL-based workflows

## 📋 Migration Steps

### Step 1: Try Personal Graph Mode

You don't need to migrate immediately. Try the new mode alongside the old:

```bash
# Old workflow (still works!)
SAMPLE_QUERY="lofi" python scripts/ingest_sample.py
python -m sgr.clean.clean_tracks
python -m sgr.db.load_tracks

# New workflow (try it!)
make build_graph TRACK_URL="https://soundcloud.com/lofi/track"
```

### Step 2: Understand the Differences

| Feature | Bulk Mode | Personal Graph Mode |
|---------|-----------|-------------------|
| Database | PostgreSQL | SQLite |
| Setup | Complex | Simple |
| Scale | 100,000+ tracks | 100-10,000 tracks |
| Speed | Slow bulk collection | Fast on-demand |
| Caching | Manual | Automatic |

### Step 3: Export Your PostgreSQL Data (Optional)

If you want to migrate existing PostgreSQL data to the new cache:

```python
# Export from PostgreSQL
import psycopg2
from sgr.cache import TrackCache

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    database="sgr",
    user="sgr",
    password="your_password"
)

# Initialize new cache
cache = TrackCache("data/cache/migrated.db")

# Export tracks
with conn.cursor() as cur:
    cur.execute("SELECT raw FROM tracks")
    for row in cur:
        track_data = row[0]  # Assuming JSONB
        cache.cache_track(track_data)

# Export relationships
with conn.cursor() as cur:
    cur.execute("""
        SELECT src_track_id, dst_track_id, score
        FROM related_tracks
        WHERE source = 'co_playlist'
    """)
    for row in cur:
        cache.add_related_track(row[0], row[1], "co_playlist", row[2])

cache.close()
```

### Step 4: Use Both Modes

You can use both modes simultaneously:

```bash
# Bulk mode for comprehensive data
SAMPLE_QUERY="ambient" python scripts/ingest_sample.py
# ... continue with PostgreSQL workflow

# Personal mode for quick exploration
make build_graph TRACK_URL="https://soundcloud.com/ambient/track"
```

## 🆕 What's New in Personal Graph Mode

### 1. No PostgreSQL Required
```bash
# Old: Setup PostgreSQL, create database, configure connection
# New: Just run!
make build_graph TRACK_URL="..."
```

### 2. Automatic Caching
```bash
# Old: Manually manage raw/staging directories
# New: Everything cached in SQLite automatically
```

### 3. Built-in Recommendations
```bash
# Old: Query PostgreSQL views manually
# New: Recommendations included in output
make build_graph TRACK_URL="..."
# Shows top recommendations automatically
```

### 4. Graph Visualization
```bash
# Old: Export data, use external tools
# New: Built-in visualization
make build_graph_viz TRACK_URL="..."
```

## 🔧 Command Equivalents

### Old Workflow → New Workflow

**Collect data about a track:**
```bash
# Old
TRACK_URL="..." python scripts/resolve_and_crawl.py
python -m sgr.clean.clean_playlists
python -m sgr.db.load_playlists

# New
make build_graph TRACK_URL="..."
```

**Find related tracks:**
```bash
# Old
psql -c "SELECT * FROM track_cooccurrence WHERE track_id_a = 123"

# New (automatic in output)
make build_graph TRACK_URL="..."
# Check "Top Recommendations" section
```

**Deep exploration:**
```bash
# Old (no direct equivalent)
# New
make build_graph_deep TRACK_URL="..."  # 2 hops instead of 1
```

## ❓ FAQ

### Can I use both modes?
Yes! They're completely independent. Use bulk mode for production, personal mode for exploration.

### Will bulk mode be deprecated?
No. It's still valuable for large-scale production use cases.

### How do I access my cache?
```python
from sgr.cache import TrackCache
cache = TrackCache("data/cache/tracks.db")
stats = cache.get_cache_stats()
```

### Can I export to PostgreSQL from cache?
Yes, but you'd need to write custom export logic. The cache schema is simpler than the full PostgreSQL schema.

### What about my existing scripts?
All existing scripts continue to work. This is an addition, not a replacement.

## 📚 Resources

- [Personal Graph Guide](PERSONAL_GRAPH_GUIDE.md)
- [README.md](../README.md) - Updated with both modes
- [Test Suite](../tests/test_user_driven_architecture.py) - Examples of API usage

## 🆘 Need Help?

If you encounter issues during migration:
1. Check the [Personal Graph Guide](PERSONAL_GRAPH_GUIDE.md)
2. Review the test suite for API examples
3. Open an issue on GitHub

---

**Remember:** You don't have to migrate! Both modes will continue to be supported.
