from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from sgr.clean.clean_tracks import parse_tags

def clean_users(in_path: Path) -> pd.DataFrame:
    rows = []
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            u = json.loads(line)
            rows.append(dict(
                user_id=u.get("id"),
                username=(u.get("username") or "").strip(),
                permalink_url=u.get("permalink_url"),
                followers_count=u.get("followers_count") or 0,
                followings_count=u.get("followings_count") or 0,
                verified=bool(u.get("verified") or False),
            ))
    return pd.DataFrame(rows)

def clean_playlists(in_path: Path) -> pd.DataFrame:
    rows = []
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            pl = json.loads(line)
            rows.append(dict(
                playlist_id=pl.get("id"),
                title=(pl.get("title") or "").strip(),
                description=(pl.get("description") or "")[:2000],
                creator_user_id=(pl.get("user") or {}).get("id"),
                genre=(pl.get("genre") or "").lower(),
                tag_list=(pl.get("tag_list") or ""),
                tags=",".join(parse_tags(pl.get("tag_list") or "")),
                created_at=pl.get("created_at"),
                track_count=len(pl.get("tracks") or []),
                permalink_url=pl.get("permalink_url"),
            ))
    return pd.DataFrame(rows)

def clean_playlist_tracks(in_path: Path) -> pd.DataFrame:
    rows = []
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)  # {"playlist_id":..., "track":{...}, "position":...}
            t = rec.get("track") or {}
            rows.append(dict(
                playlist_id=rec.get("playlist_id"),
                track_id=t.get("id"),
                position=rec.get("position"),
                # minimal denorm to ensure we have track/artist if missing
                artist_id=(t.get("user") or {}).get("id"),
                title=(t.get("title") or "").strip(),
                permalink_url=t.get("permalink_url"),
            ))
    return pd.DataFrame(rows)

if __name__ == "__main__":
    raw = Path("data/raw"); staging = Path("data/staging"); staging.mkdir(parents=True, exist_ok=True)
    # users
    for p in raw.glob("resolved_users.jsonl"):
        clean_users(p).to_parquet(staging / "users.parquet", index=False)
    # playlists
    for p in raw.glob("user_*_playlists.jsonl"):
        clean_playlists(p).to_parquet(staging / (p.stem + ".parquet"), index=False)
    # playlist tracks
    for p in raw.glob("user_*_playlist_tracks.jsonl"):
        clean_playlist_tracks(p).to_parquet(staging / (p.stem + ".parquet"), index=False)
