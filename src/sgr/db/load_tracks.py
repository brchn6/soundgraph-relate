from __future__ import annotations
import os
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv
import yaml
from pathlib import Path
from sqlalchemy import text

def engine_from_env(cfg) -> sa.Engine:
    host = os.getenv(cfg["db"]["host_env"])
    port = os.getenv(cfg["db"]["port_env"])
    user = os.getenv(cfg["db"]["user_env"])
    pwd = os.getenv(cfg["db"]["pwd_env"])
    db = os.getenv(cfg["db"]["db_env"])
    url = f"{cfg['db']['driver']}://{user}:{pwd}@{host}:{port}/{db}"
    return sa.create_engine(url, pool_pre_ping=True)


if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)

    # Ensure schema exists
    with eng.begin() as cx:
        sql = open("sql/schema.sql").read()
        cx.execute(sa.text(sql))

    staging = Path("data/staging")
    files = list(staging.glob("tracks_search_*.parquet"))
    if not files:
        raise SystemExit("No parquet files found. Run cleaning step first.")

    for pq in files:
        df = pd.read_parquet(pq)

        # artists (dedup)
        artists = df[["user_id", "username"]].dropna().drop_duplicates()
        artists.columns = ["artist_id", "username"]
        if not artists.empty:
            artists["artist_id"] = artists["artist_id"].astype("int64")
            
            # Insert artists first, ignore duplicates
            with eng.connect() as conn:
                for _, row in artists.iterrows():
                    query = text("""
                        INSERT INTO artists (artist_id, username)
                        VALUES (:artist_id, :username)
                        ON CONFLICT (artist_id) DO NOTHING;
                    """)
                    conn.execute(query, {"artist_id": row["artist_id"], "username": row["username"]})

        # Fetch the list of existing artist_ids from the database
        with eng.connect() as conn:
            result = conn.execute(text("SELECT artist_id FROM artists"))
            # Fix the issue here: Accessing the result properly
            existing_artist_ids = {row[0] for row in result}  # Use index for tuple-based access

        # Filter out tracks with artist_id not present in the existing artist list
        tracks = pd.DataFrame(
            {
                "track_id": df["track_id"].astype("int64"),
                "artist_id": df["user_id"].astype("Int64"),
                "title": df["title"],
                "description": df["description"],
                "genre": df["genre"],
                "tags": df["tags"],
                "created_at": pd.to_datetime(df["created_at"], errors="coerce", utc=True),
                "duration_ms": df["duration"],
                "bpm": df["bpm"],
                "musical_key": df["key"],
                "playback_count": df["playback_count"],
                "like_count": df["like_count"],
                "repost_count": df["repost_count"],
                "permalink_url": df["permalink_url"],
                "streamable": df["streamable"].astype(bool),
            }
        )

        # Filter tracks to only include those with an existing artist_id
        tracks = tracks[tracks["artist_id"].isin(existing_artist_ids)]

        # Insert tracks and skip duplicates
        with eng.connect() as conn:
            for _, row in tracks.iterrows():
                query = text("""
                    INSERT INTO tracks (track_id, artist_id, title, description, genre, tags, created_at, 
                    duration_ms, bpm, musical_key, playback_count, like_count, repost_count, permalink_url, streamable)
                    VALUES (:track_id, :artist_id, :title, :description, :genre, :tags, :created_at, :duration_ms, 
                    :bpm, :musical_key, :playback_count, :like_count, :repost_count, :permalink_url, :streamable)
                    ON CONFLICT (track_id) DO UPDATE SET 
                        artist_id = EXCLUDED.artist_id,
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        genre = EXCLUDED.genre,
                        tags = EXCLUDED.tags,
                        created_at = EXCLUDED.created_at,
                        duration_ms = EXCLUDED.duration_ms,
                        bpm = EXCLUDED.bpm,
                        musical_key = EXCLUDED.musical_key,
                        playback_count = EXCLUDED.playback_count,
                        like_count = EXCLUDED.like_count,
                        repost_count = EXCLUDED.repost_count,
                        permalink_url = EXCLUDED.permalink_url,
                        streamable = EXCLUDED.streamable;
                """)
                conn.execute(query, {
                    "track_id": row["track_id"], 
                    "artist_id": row["artist_id"],
                    "title": row["title"],
                    "description": row["description"],
                    "genre": row["genre"],
                    "tags": row["tags"],
                    "created_at": row["created_at"],
                    "duration_ms": row["duration_ms"],
                    "bpm": row["bpm"],
                    "musical_key": row["musical_key"],
                    "playback_count": row["playback_count"],
                    "like_count": row["like_count"],
                    "repost_count": row["repost_count"],
                    "permalink_url": row["permalink_url"],
                    "streamable": row["streamable"]
                })

        print("loaded", pq)
