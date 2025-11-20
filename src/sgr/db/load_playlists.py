# src/sgr/db/load_playlists.py
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv
from pathlib import Path
import yaml

from .load_tracks import engine_from_env


def upsert_batch(conn, sql, rows: pd.DataFrame):
    """Execute an INSERT ... ON CONFLICT for a DataFrame in a single executemany."""
    if rows.empty:
        return

    def _sanitize_record(r: dict):
        import pandas as pd

        out = {}
        for k, v in r.items():
            if pd.isna(v):
                out[k] = None
                continue

            # common array fields: tag_list, tags
            if k in ("tag_list", "tags"):
                if isinstance(v, (list, tuple)):
                    out[k] = [str(i) for i in v]
                elif isinstance(v, str):
                    out[k] = [v]
                else:
                    try:
                        out[k] = list(v)
                    except Exception:
                        out[k] = [v]
            else:
                out[k] = v
        return out

    records = [_sanitize_record(r) for r in rows.to_dict(orient="records")]
    conn.execute(sql, records)


if __name__ == "__main__":
    load_dotenv(".env")
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    staging = Path("data/staging")

    with eng.begin() as cx:
        # ---------- USERS ----------
        p_users = staging / "users.parquet"
        if p_users.exists():
            users = pd.read_parquet(p_users)
            sql_users = text(
                """
                INSERT INTO sc_users (
                    user_id, username, permalink_url, followers_count, 
                    followings_count, verified
                )
                VALUES (
                    :user_id, :username, :permalink_url, :followers_count, 
                    :followings_count, :verified
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    username         = EXCLUDED.username,
                    permalink_url    = EXCLUDED.permalink_url,
                    followers_count  = EXCLUDED.followers_count,
                    followings_count = EXCLUDED.followings_count,
                    verified         = EXCLUDED.verified;
                """
            )
            upsert_batch(cx, sql_users, users)

        # ---------- PLAYLISTS ----------
        for pq in staging.glob("user_*_playlists.parquet"):
            pls = pd.read_parquet(pq)
            if pls.empty:
                continue

            sql_pl = text(
                """
                INSERT INTO playlists (
                    playlist_id, title, description, creator_user_id, 
                    genre, tag_list, created_at, track_count, permalink_url
                )
                VALUES (
                    :playlist_id, :title, :description, :creator_user_id, 
                    :genre, :tag_list, :created_at, :track_count, :permalink_url
                )
                ON CONFLICT (playlist_id) DO UPDATE SET
                    title          = EXCLUDED.title,
                    description    = EXCLUDED.description,
                    creator_user_id= EXCLUDED.creator_user_id,
                    genre          = EXCLUDED.genre,
                    tag_list       = EXCLUDED.tag_list,
                    created_at     = EXCLUDED.created_at,
                    track_count    = EXCLUDED.track_count,
                    permalink_url  = EXCLUDED.permalink_url;
                """
            )
            upsert_batch(cx, sql_pl, pls)

        # ---------- PLAYLIST_TRACKS (+ soft artists/tracks) ----------
        for pq in staging.glob("user_*_playlist_tracks.parquet"):
            ptx = pd.read_parquet(pq)
            if ptx.empty:
                continue

            # Ensure minimal artists exist
            artists = (
                ptx[["artist_id"]]
                .dropna()
                .drop_duplicates()
                .rename(columns={"artist_id": "artist_id"})
            )
            if not artists.empty:
                artists["username"] = None
                sql_art = text(
                    """
                    INSERT INTO artists (artist_id, username)
                    VALUES (:artist_id, :username)
                    ON CONFLICT (artist_id) DO NOTHING;
                    """
                )
                upsert_batch(cx, sql_art, artists)

            # Ensure minimal tracks exist
            soft_tracks = (
                ptx[["track_id", "artist_id", "title", "permalink_url"]]
                .dropna(subset=["track_id"])
                .drop_duplicates()
            )
            if not soft_tracks.empty:
                soft_tracks["genre"] = None
                soft_tracks["tags"] = None
                soft_tracks["created_at"] = None
                soft_tracks["duration_ms"] = None
                soft_tracks["bpm"] = None
                soft_tracks["musical_key"] = None
                soft_tracks["playback_count"] = 0
                soft_tracks["like_count"] = 0
                soft_tracks["repost_count"] = 0
                soft_tracks["streamable"] = False

                sql_tr = text(
                    """
                    INSERT INTO tracks (
                        track_id, artist_id, title, description, genre, tags, 
                        created_at, duration_ms, bpm, musical_key,
                        playback_count, like_count, repost_count,
                        permalink_url, streamable
                    )
                    VALUES (
                        :track_id, :artist_id, :title, NULL, :genre, :tags,
                        :created_at, :duration_ms, :bpm, :musical_key,
                        :playback_count, :like_count, :repost_count,
                        :permalink_url, :streamable
                    )
                    ON CONFLICT (track_id) DO NOTHING;
                    """
                )
                upsert_batch(cx, sql_tr, soft_tracks)

            # Playlist ↔ track bridge
            bridge = (
                ptx[["playlist_id", "track_id", "position"]]
                .dropna(subset=["track_id"])
                .drop_duplicates()
            )
            if not bridge.empty:
                sql_br = text(
                    """
                    INSERT INTO playlist_tracks (playlist_id, track_id, position)
                    VALUES (:playlist_id, :track_id, :position)
                    ON CONFLICT (playlist_id, track_id) DO UPDATE SET
                        position = EXCLUDED.position;
                    """
                )
                upsert_batch(cx, sql_br, bridge)

