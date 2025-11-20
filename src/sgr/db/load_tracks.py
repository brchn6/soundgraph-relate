# src/sgr/db/load_tracks.py
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text
from dotenv import load_dotenv
import yaml


def engine_from_env(cfg) -> sa.Engine:
    """
    Build a SQLAlchemy engine from env variables pointed to by configs/config.yaml.

    config.yaml:
      db:
        driver: postgresql+psycopg2
        host_env: PGHOST
        port_env: PGPORT
        user_env: PGUSER
        pwd_env:  PGPASSWORD
        db_env:   PGDATABASE
    """
    host = os.getenv(cfg["db"]["host_env"])
    port = os.getenv(cfg["db"]["port_env"])
    user = os.getenv(cfg["db"]["user_env"])
    pwd = os.getenv(cfg["db"]["pwd_env"])
    db = os.getenv(cfg["db"]["db_env"])

    url = f"{cfg['db']['driver']}://{user}:{pwd}@{host}:{port}/{db}"
    return sa.create_engine(url, pool_pre_ping=True)


def _ensure_list(x):
    """Normalize tag-like fields to plain Python lists or None."""
    import numpy as np
    from pandas import Series

    if x is None:
        return None

    # Array-like
    if isinstance(x, (list, tuple, Series)) or (
        hasattr(x, "__array_interface__") or isinstance(x, np.ndarray)
    ):
        try:
            return [str(i) for i in list(x)]
        except Exception:
            return None

    # Scalars / NaN
    if pd.isna(x):
        return None

    # Single string
    if isinstance(x, str):
        return [x]

    # Fallback: wrap
    return [x]


if __name__ == "__main__":
    # Load env + config
    load_dotenv(".env")
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)

    # Ensure schema exists (idempotent)
    with eng.begin() as cx:
        sql = open("sql/schema.sql").read()
        cx.execute(sa.text(sql))

    staging = Path("data/staging")
    files = list(staging.glob("tracks_search_*.parquet"))
    if not files:
        raise SystemExit("No parquet files found. Run cleaning step first.")

    for pq in files:
        df = pd.read_parquet(pq)

        # ---------- ARTISTS ----------
        artists = df[["user_id", "username"]].dropna().drop_duplicates()
        artists.columns = ["artist_id", "username"]

        if not artists.empty:
            artists["artist_id"] = artists["artist_id"].astype("int64")

            # Insert artists first, ignore duplicates, COMMIT the transaction
            with eng.begin() as conn:
                for _, row in artists.iterrows():
                    query = text(
                        """
                        INSERT INTO artists (artist_id, username)
                        VALUES (:artist_id, :username)
                        ON CONFLICT (artist_id) DO NOTHING;
                        """
                    )
                    conn.execute(
                        query,
                        {
                            "artist_id": int(row["artist_id"]),
                            "username": row["username"],
                        },
                    )

        # Fetch existing artists
        with eng.connect() as conn:
            result = conn.execute(text("SELECT artist_id FROM artists"))
            existing_artist_ids = {row[0] for row in result}

        # ---------- TRACKS ----------
        # Normalize tags
        df["tags"] = df["tags"].apply(_ensure_list)

        tracks = pd.DataFrame(
            {
                "track_id": df["track_id"].astype("int64"),
                "artist_id": df["user_id"].astype("Int64"),
                "title": df["title"],
                "description": df["description"],
                "genre": df["genre"],
                "tags": df["tags"],
                "created_at": pd.to_datetime(
                    df["created_at"], errors="coerce", utc=True
                ),
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

        # Normalize artist_id -> int / None and filter to known artists
        tracks["artist_id"] = tracks["artist_id"].apply(
            lambda v: int(v) if (not pd.isna(v)) else None
        )
        tracks = tracks[tracks["artist_id"].isin(existing_artist_ids)]

        if tracks.empty:
            print("no tracks to load from", pq)
            continue

        # Insert tracks (upsert), COMMIT the transaction
        with eng.begin() as conn:
            for _, row in tracks.iterrows():
                query = text(
                    """
                    INSERT INTO tracks (
                        track_id, artist_id, title, description, genre, tags, created_at, 
                        duration_ms, bpm, musical_key, playback_count, like_count, repost_count, 
                        permalink_url, streamable
                    )
                    VALUES (
                        :track_id, :artist_id, :title, :description, :genre, :tags, :created_at, 
                        :duration_ms, :bpm, :musical_key, :playback_count, :like_count, :repost_count, 
                        :permalink_url, :streamable
                    )
                    ON CONFLICT (track_id) DO UPDATE SET 
                        artist_id      = EXCLUDED.artist_id,
                        title          = EXCLUDED.title,
                        description    = EXCLUDED.description,
                        genre          = EXCLUDED.genre,
                        tags           = EXCLUDED.tags,
                        created_at     = EXCLUDED.created_at,
                        duration_ms    = EXCLUDED.duration_ms,
                        bpm            = EXCLUDED.bpm,
                        musical_key    = EXCLUDED.musical_key,
                        playback_count = EXCLUDED.playback_count,
                        like_count     = EXCLUDED.like_count,
                        repost_count   = EXCLUDED.repost_count,
                        permalink_url  = EXCLUDED.permalink_url,
                        streamable     = EXCLUDED.streamable;
                    """
                )

                params = {
                    "track_id": int(row["track_id"])
                    if not pd.isna(row["track_id"])
                    else None,
                    "artist_id": int(row["artist_id"])
                    if row["artist_id"] is not None
                    else None,
                    "title": row["title"],
                    "description": row["description"],
                    "genre": row["genre"],
                    "tags": row["tags"],
                    "created_at": row["created_at"],
                    "duration_ms": int(row["duration_ms"])
                    if not pd.isna(row["duration_ms"])
                    else None,
                    "bpm": row["bpm"],
                    "musical_key": row["musical_key"],
                    "playback_count": int(row["playback_count"])
                    if not pd.isna(row["playback_count"])
                    else 0,
                    "like_count": int(row["like_count"])
                    if not pd.isna(row["like_count"])
                    else 0,
                    "repost_count": int(row["repost_count"])
                    if not pd.isna(row["repost_count"])
                    else 0,
                    "permalink_url": row["permalink_url"],
                    "streamable": bool(row["streamable"])
                    if not pd.isna(row["streamable"])
                    else False,
                }

                conn.execute(query, params)

        print("loaded", pq)
