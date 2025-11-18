# 🎵 SoundGraph

**SoundGraph** is a data-driven music discovery engine that builds knowledge graphs from SoundCloud metadata to uncover hidden relationships between tracks, artists, and users.

## 🎯 **What Does SoundGraph Do?**

SoundGraph goes **beyond SoundCloud's built-in recommendations** by creating a comprehensive knowledge graph that reveals:

- **📊 Track Relationships**: Which songs appear together in playlists (co-occurrence analysis)
- **🎤 Artist Connections**: How artists are linked through collaborations, shared playlists, and fan overlap
- **👥 User Similarity**: Find users with similar music taste based on their likes and playlists
- **🔍 Deep Discovery**: Get recommendations based on complex relationship patterns, not just individual track similarity

### **Why Build This?**
SoundCloud's algorithm is a "black box" - you can't see WHY you got a recommendation. SoundGraph creates a **transparent, queryable music knowledge graph** where you can:
- Input a track and see exactly WHY certain tracks are related
- Find the "missing links" between two different songs/artists
- Discover music through community behavior patterns (what do people who like X also like?)
- Build custom recommendation models on top of rich relational data

---

## 🏗️ **How SoundGraph Works**

### **The Knowledge Graph Approach**
1. **Data Collection**: Fetches public metadata from SoundCloud (tracks, playlists, users, interactions)
2. **Relationship Extraction**: Builds a graph where edges represent relationships:
   - Track ↔ Track (co-occurrence in playlists)
   - User ↔ Track (likes, reposts)
   - User ↔ User (similar taste patterns)
   - Artist ↔ Artist (collaboration networks)
3. **Query Engine**: Provides APIs to query relationships and find recommendations
4. **ML Ready**: Exports graph data for training recommendation models

### **Key Innovation: Co-occurrence Analysis**
Instead of just analyzing individual track features, SoundGraph looks at **behavioral patterns**:
- If tracks A and B appear in many playlists together → they're related
- If users who like track X also like track Y → similarity signal
- If user P and user Q have 70% playlist overlap → similar taste

---

## 🚀 **Quick Start**

### **Prerequisites**
- Python 3.11+
- PostgreSQL (local installation)
- SoundCloud API access (OAuth token preferred)

### **Installation**
```bash
git clone https://github.com/your-username/soundgraph.git
cd soundgraph

# Setup environment
conda create -y -n sgr python=3.11
conda activate sgr
pip install -r requirements.txt
pip install -e .
```

### **Configuration**
Create `.env` file:
```env
# SoundCloud API
SOUNDCLOUD_ACCESS_TOKEN=your_oauth_token_here
SOUNDCLOUD_CLIENT_ID=your_client_id_here

# PostgreSQL Database
PGHOST=localhost
PGPORT=5432
PGUSER=sgr
PGPASSWORD=your_password
PGDATABASE=sgr

# Sample data
SAMPLE_QUERY=lofi
```

---

## 📋 **Complete Workflow Guide**

### **Phase 1: Data Collection & Setup**

#### **Step 1: Initialize Database**
```bash
# Ensure PostgreSQL is running
sudo systemctl start postgresql

# Create database and user (run once)
sudo -u postgres psql
CREATE DATABASE sgr;
CREATE USER sgr WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE sgr TO sgr;
\q
```

#### **Step 2: Collect Sample Data**
```bash
# Fetch tracks by search query
SAMPLE_QUERY="lofi hip hop" python scripts/ingest_sample.py
```
**What this does**: Searches SoundCloud for tracks matching your query and saves raw JSON data to `data/raw/tracks_search_*.jsonl`

**Expected output**: `Found 50 tracks for query 'lofi hip hop', saved to data/raw/tracks_search_lofi_hip_hop_20250909.jsonl`

#### **Step 3: Clean and Normalize Data**
```bash
# Process raw JSON into structured data
python -m sgr.clean.clean_tracks
```
**What this does**: Converts raw JSON to structured parquet files with engagement scores, normalized tags, and clean metadata.

**Expected output**: `wrote data/staging/tracks_search_lofi_hip_hop_20250909.parquet 50`

#### **Step 4: Load into Database**
```bash
# Create schema and load tracks + artists
python -m sgr.db.load_tracks
```
**What this does**: Creates database tables and loads artists + tracks with proper relationships.

**Expected output**: Database tables created, artists and tracks inserted.

### **Phase 2: Build Knowledge Graph**

#### **Step 5: Crawl Track Neighborhood**
```bash
# Deep-dive into a specific track's ecosystem
TRACK_URL="https://soundcloud.com/artist/track-name" python scripts/resolve_and_crawl.py
```
**What this does**: Takes a track URL and crawls the artist's entire playlist ecosystem, collecting:
- All playlists by that artist
- All tracks in those playlists
- User interactions (likes, if available)

**Expected output**: 
```
INFO: resolve: https://soundcloud.com/artist/track-name
INFO: track_id=123456 by user_id=789
INFO: playlists fetched: 15
INFO: playlist track entries: 342
SUCCESS: crawl complete
```

#### **Step 6: Process Playlists & Users**
```bash
# Clean and load playlist data
python -m sgr.clean.clean_playlists
python -m sgr.db.load_playlists
```
**What this does**: Normalizes playlist data and loads users, playlists, and playlist_tracks relationships.

#### **Step 7: Build Co-occurrence Analysis**
```bash
# Create advanced schema with materialized views
python scripts/create_schema_extras.py

# Build track co-occurrence matrix
python scripts/refresh_cooccur.py
```
**What this does**: Creates a materialized view that calculates how often tracks appear together in playlists - the core of the knowledge graph.

### **Phase 3: Query & Discover**

#### **Step 8: Unveil Relationships**
```bash
# Analyze a track's complete relationship network
TRACK_URL="https://soundcloud.com/artist/track-name" python scripts/unveil.py
```
**What this does**: Shows the complete "relationship profile" of a track:
- Basic track info
- Playlists containing it
- Related tracks (by co-occurrence)
- Related tracks (by tag similarity)
- Artist connections
- Engagement patterns

**Expected output**:
```
=== TRACK SUMMARY ===
Track: "Chill Lo-Fi Beats" by LoFiArtist
Genre: Hip Hop, Plays: 50,431, Likes: 1,203

=== PLAYLISTS CONTAINING THIS TRACK ===
- "Study Vibes" (15 tracks)
- "Late Night Coding" (23 tracks)

=== RELATED TRACKS (CO-OCCURRENCE) ===
1. "Midnight Study Session" - appeared together 8 times
2. "Coffee Shop Ambience" - appeared together 6 times

=== RELATED TRACKS (TAG SIMILARITY) ===
1. "Dreamy Loops" - 85% tag overlap
2. "Focus Beats" - 72% tag overlap
```

---

## 🔧 **Script Reference & Validation**

### **Core Scripts** ✅

| Script | Purpose | Input | Output | Validation |
|--------|---------|-------|--------|------------|
| `ingest_sample.py` | Fetch SoundCloud data | Search query | Raw JSONL files | Check `data/raw/` for new files |
| `clean_tracks.py` | Normalize track data | Raw JSONL | Structured parquet | Check `data/staging/` for parquet files |
| `load_tracks.py` | Load to database | Parquet files | DB records | `SELECT COUNT(*) FROM tracks;` |
| `resolve_and_crawl.py` | Deep crawl track ecosystem | Track URL | Playlist/user data | Check for new user_*_playlists.jsonl files |
| `clean_playlists.py` | Normalize playlist data | Raw playlist JSONL | Structured parquet | Check `data/staging/` for playlist parquets |
| `load_playlists.py` | Load playlists to DB | Playlist parquets | DB records | `SELECT COUNT(*) FROM playlists;` |
| `create_schema_extras.py` | Advanced DB schema | None | Enhanced tables | Check for `track_cooccurrence` view |
| `refresh_cooccur.py` | Update relationships | Existing data | Updated view | `SELECT COUNT(*) FROM track_cooccurrence;` |
| `unveil.py` | Query relationships | Track URL/ID | Relationship report | Visual relationship output |

### **Quick Validation Commands**
```bash
# Check data pipeline health
make test  # Run basic API tests

# Check database content
psql -h localhost -U sgr -d sgr -c "
  SELECT 
    (SELECT COUNT(*) FROM artists) as artists,
    (SELECT COUNT(*) FROM tracks) as tracks,
    (SELECT COUNT(*) FROM playlists) as playlists,
    (SELECT COUNT(*) FROM track_cooccurrence) as relationships;
"

# Validate knowledge graph
psql -h localhost -U sgr -d sgr -c "
  SELECT track_id_a, track_id_b, together 
  FROM track_cooccurrence 
  ORDER BY together DESC 
  LIMIT 10;
"
```

---

## 🎯 **Complete Pipeline Example**

Here's how to run the complete pipeline for a single track:

```bash
# 1. Collect general data about a genre
SAMPLE_QUERY="ambient electronic" python scripts/ingest_sample.py
python -m sgr.clean.clean_tracks
python -m sgr.db.load_tracks

# 2. Deep-dive into a specific track's ecosystem
TRACK_URL="https://soundcloud.com/ambient-artist/floating-dreams" python scripts/resolve_and_crawl.py
python -m sgr.clean.clean_playlists
python -m sgr.db.load_playlists

# 3. Build knowledge graph
python scripts/create_schema_extras.py
python scripts/refresh_cooccur.py

# 4. Query relationships
TRACK_URL="https://soundcloud.com/ambient-artist/floating-dreams" python scripts/unveil.py
```

**Or use the automated pipeline:**
```bash
make pipeline TRACK_URL="https://soundcloud.com/ambient-artist/floating-dreams"
```

---

## 📊 **Project Architecture**

```
soundgraph/
├── scripts/           # Main orchestration scripts
│   ├── ingest_sample.py       # SoundCloud API data collection
│   ├── resolve_and_crawl.py   # Deep ecosystem crawling
│   ├── create_schema_extras.py # Advanced database schema
│   ├── refresh_cooccur.py     # Knowledge graph updates
│   └── unveil.py             # Relationship query engine
├── src/sgr/          # Core library
│   ├── clean/         # Data normalization
│   ├── db/           # Database operations
│   └── io/           # SoundCloud API client
├── sql/schema.sql    # Database schema
├── data/
│   ├── raw/          # Raw JSON from API
│   └── staging/      # Processed parquet files
└── configs/          # Configuration files
```

---

## 🔮 **Future Development**

### **Phase 2: Backend API** (Next)
- REST API for querying relationships
- Real-time recommendation endpoints
- Graph visualization endpoints

### **Phase 3: Frontend Interface** (Later)
- Web interface for exploration
- Interactive graph visualization
- User recommendation interface

### **Phase 4: Machine Learning** (Advanced)
- Graph Neural Networks for recommendations
- Audio feature analysis integration
- Collaborative filtering enhancement

---

## 🤝 **Contributing**

This project is designed for community collaboration:

1. **Data Scientists**: Extend the knowledge graph algorithms
2. **Backend Developers**: Build the API layer
3. **Frontend Developers**: Create visualization interfaces
4. **ML Engineers**: Develop recommendation models

See `CONTRIBUTING.md` for guidelines.

---

## 📄 **License**

MIT License - Build amazing music discovery tools!










---
## 🔜 Next Steps

This roadmap layers a **knowledge-graph–enhanced, multi-task recommender** on top of SoundGraph, inspired by the MMSS\_MKR framework (multi-task, multi-channel, multi-loss) and its KG construction workflow. The goal: keep SoundGraph’s transparent co-occurrence engine, while adding **joint training with KG embeddings**, **cross-&-compression feature sharing**, and **clear evaluation/ablation**.

### 1) Expand the Knowledge Graph (KG)

* **Add item–attribute triples** beyond co-occurrence edges:

  * `Track —[has_genre]→ Genre`, `Track —[by_artist]→ Artist`, `Track —[in_playlist]→ Playlist`, `Artist —[collab_with]→ Artist`.
  * Where available, include `Track —[has_tag]→ Tag`, `Track —[released_on]→ Date`, `Track —[label]→ Label`.
* **Normalize and fuse entities** (dedupe artists, playlists, tags) with an entity alignment pass; keep provenance for transparency.
* **Export triples** to `data/graph/triples.parquet` with schema: `(head, relation, tail, weight, source)`.

> Why: The paper’s KG is built from structured + semi/ unstructured sources, then fused and cleaned into triples before embedding; mirroring that improves signal breadth.

### 2) Add a KG Embedding Module (KGE)

* Implement a KGE trainer supporting **TransE / TransH / TransR** backends (start with TransE).
* Inputs: `triples.parquet`; Outputs: `embeddings/{entity}.npy`, `embeddings/{relation}.npy`.
* Provide a CLI:

  ```bash
  python -m sgr.kge.train --triples data/graph/triples.parquet --model transe --dim 128 --epochs 50
  ```
* Ship a **score function** helper that supports multiple activations (sigmoid / tanh / softsign / softplus) for robust triple scoring, as in the paper’s multi-calculation design.

### 3) Multi-Task Joint Training (MMSS-style)

* Create a **joint trainer** that optimizes:

  1. **Recommendation task** (predict user ↔ track interaction) using your co-occurrence features + track/artist embeddings,
  2. **KGE task** (true vs. corrupted triples).
* Bridge both with a **Cross & Compression Unit** to share interaction features between the rec module and KG module. Expose depth `L`/`H` as hyperparams.
* CLI:

  ```bash
  python -m sgr.train.joint \
    --rec-dim 128 --kge-dim 128 --cross-depth 1 --epochs 200 \
    --lr-rec 2e-5 --lr-kge 2e-5 --l2 2e-5 --kge-interval 64
  ```
* Loss = `L_rec + L_kge + λ‖w‖²`, with **multi-activation fusion** in the KGE score and **multi-prediction fusion** (dot-product then sigmoid/tanh/softsign) in the rec head, following the paper’s recipe.

### 4) Evaluation Suite (AUC/ACC + Ablations)

* Create a benchmark split (e.g., 60/20/20) over user–track interactions; report **AUC** and **Accuracy**.
* Add **ablation flags**:

  * `--no-cross` (remove Cross\&Compression),
  * `--single-activation` (disable multi-activation scoring),
  * `--single-pred` (disable multi-prediction head),
  * `--no-kge` (rec only).
* CLI:

  ```bash
  python -m sgr.eval.run --metrics auc,acc
  python -m sgr.eval.ablate --no-cross
  ```
* Document gains vs. baselines similar to the paper’s tables (AUC/ACC deltas).

### 5) Reproducible KG Build Pipeline

* Add a **KG build DAG** mirroring the paper’s stages:

  1. **Acquisition** (SoundCloud metadata),
  2. **Extraction** (entity/rel/tag parsing),
  3. **Fusion** (entity alignment + dedupe),
  4. **Triples** (graphization),
  5. **Cleaning** (QC, missing/invalid fix).
* Surface a single command:

  ```bash
  make build_kg   # runs ingest → clean → fuse → triples → validate
  ```
* Include a `KG_VALIDATION.md` with sanity checks (degree dist., top relations, duplicate rate).

### 6) API & Explainability Hooks

* Extend `unveil.py` to **explain recommendations** with:

  * Paths in the KG (e.g., `TrackA → in_playlist → P → in_playlist → TrackB`),
  * Contribution from **co-occurrence vs. KGE proximity vs. tag overlap**,
  * Confidence from the multi-prediction head.
* Provide an `/explanations` endpoint that returns **evidence triples** and normalized contributions.

### 7) Dataset Notes & Ethics

* The paper did **not** publish its KG; it shared **methodology** and used public datasets for evaluation. Follow that precedent—ship scripts/configs to **rebuild** the graph from public SoundCloud metadata you’re permitted to use, and clearly document rate limits and ToS.

### 8) What to Commit in This Repo

* `src/sgr/kge/` (TransE/H/R + trainers + negative sampling + multi-activation scoring).
* `src/sgr/model/cross_compress.py` (Cross & Compression unit).
* `src/sgr/train/joint.py` (multi-task loop, alternating updates; `--kge-interval`).
* `src/sgr/eval/` (AUC/ACC, ablations, hyperparam sweeps).
* `docs/MMSS_MKR_README.md` (math, symbols, and learning schedule overview; small diagrams of Fig.-style blocks).

---

### ✨ Deliverables Checklist

* [ ] KG triples export + validation report
* [ ] TransE baseline + embeddings artifact
* [ ] Cross\&Compression module integrated
* [ ] Joint training with multi-prediction & multi-activation scoring
* [ ] AUC/ACC metrics + ablation report
* [ ] `/explanations` API returning evidence paths

These steps keep SoundGraph’s transparency while adopting the **KG + multi-task learning** techniques that improved accuracy in the paper—giving you both **better recs** and **auditable reasons** for each suggestion.
