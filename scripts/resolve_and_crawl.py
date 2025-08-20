# scripts/resolve_and_crawl.py
from __future__ import annotations
import json
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml, time
from sgr.io.soundcloud_client import make_client_from_env

def write_jsonl(path: Path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

def main():
    """
    Usage:
      TRACK_URL="https://soundcloud.com/artist/track-slug" python scripts/resolve_and_crawl.py
    """
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    raw_dir = Path(cfg["store"]["raw_dir"])
    sc = make_client_from_env()

    track_url = os.getenv("TRACK_URL")
    if not track_url:
        raise SystemExit("Set TRACK_URL env var to a public SoundCloud track URL")

    logger.info(f"resolve: {track_url}")
    obj = sc.resolve(track_url)
    if obj.get("kind") != "track":
        raise SystemExit(f"Resolved kind={obj.get('kind')} (expected track)")

    track = obj
    user = track.get("user") or {}
    user_id = user.get("id")
    track_id = track.get("id")
    logger.info(f"track_id={track_id} by user_id={user_id}")

    # write the track and user to raw files
    write_jsonl(raw_dir / "resolved_tracks.jsonl", [track])
    write_jsonl(raw_dir / "resolved_users.jsonl", [user])

    # pull user's playlists (public)
    playlists = []
    offset, limit = 0, 50
    while True:
        batch = sc.user_playlists(user_id, limit=limit, offset=offset) or []
        playlists.extend(batch)
        if len(batch) < limit: break
        offset += limit; time.sleep(0.2)
    write_jsonl(raw_dir / f"user_{user_id}_playlists.jsonl", playlists)
    logger.info(f"playlists fetched: {len(playlists)}")

    # collect tracks from those playlists
    playlist_tracks = []
    for pl in playlists:
        trks = (pl.get("tracks") or [])
        for pos, t in enumerate(trks):
            if t and t.get("id"):
                playlist_tracks.append({"playlist_id": pl.get("id"), "track": t, "position": pos})
    write_jsonl(raw_dir / f"user_{user_id}_playlist_tracks.jsonl", playlist_tracks)
    logger.info(f"playlist track entries: {len(playlist_tracks)}")

    # (optional) user likes (if endpoint available)
    likes = []
    try:
        offset = 0
        while True:
            batch = sc.user_likes(user_id, limit=limit, offset=offset) or []
            likes.extend(batch)
            if len(batch) < limit: break
            offset += limit
    except Exception:
        pass
    if likes:
        write_jsonl(raw_dir / f"user_{user_id}_likes.jsonl", likes)
        logger.info(f"user likes pulled: {len(likes)}")
    logger.success("crawl complete")

if __name__ == "__main__":
    import os
    main()
