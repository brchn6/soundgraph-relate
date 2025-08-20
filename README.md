# SoundGraph Relate

**SoundGraph Relate** is a Python-based project that builds a **community tool for discovering related tracks** using SoundCloud public metadata.
It supports:

* fetching SoundCloud track/playlist/user data,
* cleaning + storing in a relational DB,
* unveiling hidden layers (related tracks, playlists, artist connections),
* preparing large datasets,
* and training machine learning / neural network models on audio + text + graph signals.

---

## Why This Exists

Music discovery is siloed and often opaque. This project aims to **empower researchers and communities** to:

* **Unveil Hidden Layers** around a given track:

  * **Related Tracks** — similarity by co-playlist, tags, genre, artist collaborations.
  * **User Engagement** — likes, reposts, comments (when available).
  * **Playlists** — playlists containing the track and contextual co-occurrences.
  * **Artist Connections** — shared playlists, collaborations, follower networks.

* **Build Datasets** — a structured, extensible SQL + parquet layer for MIR research.

* **Train Models** — downstream deep learning on text, tags, and (if permitted) audio previews.

---

## Requirements

* Python 3.11+
* PostgreSQL (local or remote)
* Conda (recommended)
* Dependencies in `requirements.txt`

---

## Installation

```bash
git clone https://github.com/your-username/soundgraph-relate.git
cd soundgraph-relate

# set up env
conda create -y -n sgr python=3.11
conda activate sgr
pip install -r requirements.txt
```

Set environment variables in `.env`:

```dotenv
# OAuth (preferred)
SOUNDCLOUD_ACCESS_TOKEN=...

# (optional) fallback
SOUNDCLOUD_CLIENT_ID=...

# Postgres
PGHOST=localhost
PGPORT=5432
PGUSER=sgr
PGPASSWORD=sgr_password
PGDATABASE=sgr

# sample query
SAMPLE_QUERY=lofi
```

---

## Usage: Script by Script

### 1. Ingest data

`scripts/ingest_sample.py`
Fetches track metadata from SoundCloud API (OAuth preferred).

```bash
SAMPLE_QUERY="lofi" python scripts/ingest_sample.py
```

→ saves raw JSONL to `data/raw/`.

---

### 2. Clean data

`sgr.clean.clean_tracks`
Normalizes raw JSONL → parquet, adds engagement score.

```bash
python -m sgr.clean.clean_tracks
```

→ saves parquet to `data/staging/`.

---

### 3. Load into Postgres

`sgr.db.load_tracks`
Creates schema (if not exists) and upserts artists + tracks.

```bash
python -m sgr.db.load_tracks
```

---

### 4. Resolve & crawl a track

`scripts/resolve_and_crawl.py`
Given a track URL, pulls its owner’s playlists + tracks in those playlists.

```bash
TRACK_URL="https://soundcloud.com/artist/track" python scripts/resolve_and_crawl.py
```

---

### 5. Clean + load playlists

`sgr.clean.clean_playlists` → parquet
`sgr.db.load_playlists` → Postgres

```bash
python -m sgr.clean.clean_playlists
python -m sgr.db.load_playlists
```

---

### 6. Build co-occurrence view

`scripts/create_schema_extras.py` adds playlists/users tables + materialized view.
`scripts/refresh_cooccur.py` refreshes the view.

```bash
python scripts/create_schema_extras.py
python scripts/refresh_cooccur.py
```

---

### 7. Unveil hidden layers

`scripts/unveil.py`
Given a track id or URL, prints:

* track summary
* playlists containing it
* related tracks (co-playlist)
* related tracks (tag overlap)
* artist connections
* engagement (if available)

```bash
TRACK_URL="https://soundcloud.com/artist/track" python scripts/unveil.py
```

---

## Project Structure

```
.
├── configs/              # config.yaml + .env
├── data/raw              # raw jsonl
├── data/staging          # cleaned parquet
├── sql/schema.sql        # base schema
├── scripts/              # orchestration scripts
├── src/sgr/              # library code (clean, db, io, utils)
└── tests/                # pytest-based tests
```

---

## Large Dataset Instructions

When scaling beyond small samples:

1. **Batch ingestion**
   Use multiple queries (`hiphop`, `techno`, `ambient`) or crawl curator accounts.
   Example:

   ```bash
   for q in "lofi" "house" "techno"; do SAMPLE_QUERY="$q" python scripts/ingest_sample.py; done
   ```

2. **Incremental updates**
   Each JSONL is append-only. Cleaning + loading scripts handle deduplication/upserts.

3. **Database performance**

   * Create indexes (already in schema).
   * Use `REFRESH MATERIALIZED VIEW CONCURRENTLY track_cooccurrence;` for large DBs.

4. **Storage**

   * Expect \~1–2 KB per track JSON.
   * 1M tracks → \~2 GB raw JSON.
   * Use parquet + Postgres for efficient access.

---

## Training Neural Networks

Once you’ve built a dataset, you can train models for **track embeddings**:

1. **Text embeddings**
   Use `sentence-transformers` on titles + tags + descriptions.

   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer("all-mpnet-base-v2")
   emb = model.encode(["dreamy lofi beats"])
   ```

2. **Graph embeddings**
   Export playlist/track/artist edges to PyTorch Geometric.

   ```python
   from torch_geometric.data import Data
   # build edge_index from playlist_tracks
   ```

3. **Audio embeddings**
   If SoundCloud preview streams are allowed in your app context, extract CLAP/OpenL3 embeddings with `torchaudio`.

4. **Fusion + training**
   Train a neural net (e.g. contrastive multi-view) combining modalities.

   ```python
   # pseudo-code
   z_text = text_encoder(title+tags)
   z_audio = audio_encoder(waveform)
   z_graph = gnn(node_features, edge_index)
   z_fused = fusion([z_text, z_audio, z_graph])
   ```

5. **Objectives**

   * **Contrastive** (align tracks co-occurring in playlists)
   * **Ranking** (BPR on co-listens)
   * **Classification** (predict genre/tags)

6. **Evaluation**
   Use held-out playlists for Recall\@K, NDCG\@K.

---

## Example Pipeline (end-to-end)

```bash
# 1. ingest a query
SAMPLE_QUERY="lofi" python scripts/ingest_sample.py

# 2. clean
python -m sgr.clean.clean_tracks

# 3. load
python -m sgr.db.load_tracks

# 4. crawl neighborhood of a track
TRACK_URL="https://soundcloud.com/artist/track" python scripts/resolve_and_crawl.py
python -m sgr.clean.clean_playlists
python -m sgr.db.load_playlists

# 5. refresh cooccurrence view
python scripts/refresh_cooccur.py

# 6. unveil
TRACK_URL="https://soundcloud.com/artist/track" python scripts/unveil.py
```

---

## Testing

```bash
pytest tests/
```

---

## Next Steps

* Add batch crawlers for popular playlists to enrich co-occurrence graph.
* Extend cleaning scripts to handle likes/reposts/comments.
* Train first baseline **text-only related track model**.
* Add Streamlit/Gradio frontend to demo.


