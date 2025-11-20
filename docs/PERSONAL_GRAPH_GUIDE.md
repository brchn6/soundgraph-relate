# Personal Graph Mode - User Guide

This guide shows you how to use SoundGraph's new Personal Graph Mode for on-demand music discovery.

## 🎯 Quick Overview

Personal Graph Mode lets you build your own music discovery network starting from any SoundCloud track. No database setup required!

## 📋 Prerequisites

1. Python 3.11+
2. SoundCloud API credentials (OAuth token)
3. That's it! No PostgreSQL needed.

## 🚀 Getting Started

### Step 1: Setup

```bash
# Clone and install
git clone https://github.com/your-username/soundgraph.git
cd soundgraph
pip install -r requirements.txt
pip install -e .

# Create .env file with your SoundCloud credentials
```

### Step 2: Build Your First Graph

```bash
# Find a track on SoundCloud you like
make build_graph TRACK_URL="https://soundcloud.com/chillhop/floating-away"
```

## 💡 Use Cases

### 1. Discover Similar Tracks
```bash
make build_graph TRACK_URL="https://soundcloud.com/artist/track"
```

### 2. Deep Exploration
```bash
make build_graph_deep TRACK_URL="https://soundcloud.com/artist/track"
```

### 3. With Visualization
```bash
make build_graph_viz TRACK_URL="https://soundcloud.com/artist/track"
```

## 🐍 Python API

```python
from sgr.io.soundcloud_client import make_client_from_env
from sgr.cache import TrackCache
from sgr.collectors import SmartExpander
from sgr.graph import PersonalGraph

# Initialize
sc_client = make_client_from_env()
cache = TrackCache()
expander = SmartExpander(sc_client, cache)

# Expand from URL
result = expander.expand_from_url(
    "https://soundcloud.com/artist/track",
    depth=2,
    max_tracks=1000
)

# Build and query graph
graph = PersonalGraph(cache)
graph.build_from_seed(result["seed_track_id"])
recs = graph.get_recommendations(result["seed_track_id"])
```

**Happy music discovering! 🎵**
