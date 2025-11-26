.PHONY: env deps ingest clean db up load fmt refresh_and_request test doctor schema_extras cooccur pipeline_url playlists_clean playlists_load unveil build_graph

# Create and activate Conda environment, install dependencies
env:
	conda create -y -n sgr python=3.11 || true
	@echo "Run: conda activate sgr && pip install -r requirements.txt"

# Install dependencies from requirements.txt
deps:
	pip install -r requirements.txt
	pip install networkx matplotlib  # For personal graph functionality
	python -m ipykernel install --user --name sgr --display-name "Python (sgr)" || true
	pip install -e . || true

# Ingest sample data from SoundCloud and save to a file
ingest:
	python scripts/ingest_sample.py

# Clean the ingested data
clean:
	python -m sgr.clean.clean_tracks

# PostgreSQL - No Docker version, connect directly to local PostgreSQL
db:
	@echo "Make sure your PostgreSQL server is running locally on port 5432 with the correct database settings."
	@echo "For example: sudo systemctl start postgresql"

# Ensure PostgreSQL is up (this is just a placeholder for local setups)
up: db
	@echo "DB up. Make sure PostgreSQL is running."

# Load the cleaned data into the PostgreSQL database
load:
	python -m sgr.db.load_tracks

# Resolve a track URL (ensure TRACK_URL is passed as an argument)
resolve:
	@if [ -z "$(TRACK_URL)" ]; then echo "Usage: make resolve TRACK_URL=..."; exit 1; fi
	TRACK_URL=$(TRACK_URL) python scripts/resolve_and_crawl.py

# Clean playlists
playlists_clean:
	python -m sgr.clean.clean_playlists

# Load playlists data into PostgreSQL
playlists_load:
	python -m sgr.db.load_playlists

# Unveil track data (either TRACK_ID or TRACK_URL must be provided)
unveil:
	@if [ -z "$(TRACK_ID)" ] && [ -z "$(TRACK_URL)" ]; then echo "Usage: make unveil TRACK_ID=... (or TRACK_URL=...)"; exit 1; fi
	TRACK_ID=$(TRACK_ID) TRACK_URL=$(TRACK_URL) python scripts/unveil.py

# Format code using ruff and black
fmt:
	ruff check src --fix || true
	black src scripts || true

# Refresh the token and make an API request
refresh_and_request:
	python utils/refresh_and_request.py

# Test /home/barc/dev/soundgraph-relate/tests/test_soundcloud_api.py
test:
	python  tests/test_soundcloud_api.py

# Doctor script for checking the system health
doctor:
	python utils/doctor.py

# Create schema extras
schema_extras:
	python scripts/create_schema_extras.py

# Refresh co-occurrence data
cooccur:
	python scripts/refresh_cooccur.py

# Run the pipeline with a track URL
pipeline_url:
	@if [ -z "$(TRACK_URL)" ]; then echo "Usage: make pipeline_url TRACK_URL=..."; exit 1; fi
	TRACK_URL=$(TRACK_URL) python scripts/resolve_and_crawl.py
	python -m sgr.clean.clean_playlists
	python -m sgr.db.load_playlists
	$(MAKE) cooccur
	TRACK_URL=$(TRACK_URL) python scripts/unveil.py

export_corpus:
	python scripts/export_training_corpus.py
export_pairs:
	python scripts/export_pairs.py

# ===== NEW: User-Driven Architecture =====

# Build a personal graph from a seed track (new architecture)
build_graph:
	@if [ -z "$(TRACK_URL)" ]; then echo "Usage: make build_graph TRACK_URL=..."; exit 1; fi
	TRACK_URL=$(TRACK_URL) python scripts/build_personal_graph.py

# Build with custom depth
build_graph_deep:
	@if [ -z "$(TRACK_URL)" ]; then echo "Usage: make build_graph_deep TRACK_URL=..."; exit 1; fi
	TRACK_URL=$(TRACK_URL) DEPTH=2 MAX_TRACKS=1000 python scripts/build_personal_graph.py

# Build and visualize
build_graph_viz:
	@if [ -z "$(TRACK_URL)" ]; then echo "Usage: make build_graph_viz TRACK_URL=..."; exit 1; fi
	TRACK_URL=$(TRACK_URL) VISUALIZE=true python scripts/build_personal_graph.py