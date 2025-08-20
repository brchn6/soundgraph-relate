from __future__ import annotations
import os, sqlalchemy as sa, pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv
import yaml
from sgr.db.load_tracks import engine_from_env

def q(cx, sql, **kw):
    return pd.read_sql(text(sql), cx, params=kw)

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)

    # either supply TRACK_ID or TRACK_URL (when URL provided, resolve in DB by permalink)
    track_id = os.getenv("TRACK_ID")
    track_url = os.getenv("TRACK_URL")

    with eng.connect() as cx:
        if track_url and not track_id:
            df = q(cx, "SELECT track_id FROM tracks WHERE permalink_url=:u LIMIT 1", u=track_url)
            if not df.empty: track_id = int(df.iloc[0]["track_id"])
        if not track_id: raise SystemExit("Set TRACK_ID or TRACK_URL to a track known in DB")

        print("\n=== TRACK ===")
        print(q(cx, """
            SELECT t.track_id, t.title, a.artist_id, a.username AS artist, t.genre, t.tags, t.playback_count, t.like_count, t.repost_count
            FROM tracks t LEFT JOIN artists a ON t.artist_id=a.artist_id
            WHERE t.track_id=:tid
        """, tid=track_id))

        print("\n=== PLAYLISTS CONTAINING TRACK ===")
        pls = q(cx, """
            SELECT p.playlist_id, p.title, p.permalink_url
            FROM playlist_tracks pt JOIN playlists p ON pt.playlist_id=p.playlist_id
            WHERE pt.track_id=:tid ORDER BY p.track_count DESC
        """, tid=track_id)
        print(pls.head(20))

        print("\n=== RELATED TRACKS (co-playlist) ===")
        rel = q(cx, """
            SELECT b.track_id AS neighbor_id, t.title, a.username AS artist, c.together
            FROM track_cooccurrence c
            JOIN tracks t ON t.track_id = c.track_id_b
            LEFT JOIN artists a ON a.artist_id = t.artist_id
            WHERE c.track_id_a=:tid
            ORDER BY c.together DESC
            LIMIT 20
        """, tid=track_id)
        print(rel)

        print("\n=== RELATED (tag overlap) ===")
        tagrel = q(cx, """
            WITH seeds AS (
              SELECT unnest(string_to_array(coalesce(tags,''), ',')) AS tag FROM tracks WHERE track_id=:tid
            )
            SELECT t.track_id, t.title, a.username AS artist,
                   (SELECT COUNT(*) FROM seeds s WHERE s.tag<>'' AND position(s.tag in coalesce(t.tags,''))>0) AS tag_hits
            FROM tracks t
            LEFT JOIN artists a ON a.artist_id=t.artist_id
            WHERE t.track_id<>:tid
            ORDER BY tag_hits DESC NULLS LAST, t.playback_count DESC
            LIMIT 20
        """, tid=track_id)
        print(tagrel)

        print("\n=== ARTIST CONNECTIONS (same playlists, simple) ===")
        arts = q(cx, """
            SELECT a2.artist_id, a2.username, COUNT(*) AS shared_playlists
            FROM playlist_tracks pt1
            JOIN tracks t2 ON t2.track_id=pt1.track_id
            JOIN artists a2 ON a2.artist_id=t2.artist_id
            WHERE pt1.playlist_id IN (SELECT playlist_id FROM playlist_tracks WHERE track_id=:tid)
              AND t2.track_id<>:tid
            GROUP BY a2.artist_id, a2.username
            ORDER BY shared_playlists DESC
            LIMIT 20
        """, tid=track_id)
        print(arts)

        # Engagement (only if you've ingested likes/reposts/comments)
        print("\n=== USER ENGAGEMENT (if available) ===")
        try:
            print(q(cx, """
                SELECT 'likes' AS kind, COUNT(*) AS n FROM likes WHERE track_id=:tid
                UNION ALL
                SELECT 'reposts', COUNT(*) FROM reposts WHERE track_id=:tid
                UNION ALL
                SELECT 'comments', COUNT(*) FROM comments WHERE track_id=:tid
            """, tid=track_id))
        except Exception:
            print("likes/reposts/comments not yet ingested")
