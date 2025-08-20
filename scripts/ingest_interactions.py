from __future__ import annotations
import os, json, time, yaml
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from sgr.io.soundcloud_client import make_client_from_env

def write_jsonl(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    load_dotenv()
    sc = make_client_from_env()
    raw_dir = Path(yaml.safe_load(open("configs/config.yaml"))["store"]["raw_dir"])

    track_id = os.getenv("TRACK_ID")
    track_url = os.getenv("TRACK_URL")

    if track_url and not track_id:
        obj = sc.resolve(track_url)
        if obj.get("kind") != "track":
            raise SystemExit(f"Resolved kind={obj.get('kind')}")
        track_id = obj["id"]
    if not track_id:
        raise SystemExit("Set TRACK_ID or TRACK_URL")

    logger.info(f"seed track_id={track_id}")

    # 1) pull favoriters / reposters
    favs, reps = [], []
    for kind, fn in [("favoriters", sc.track_favoriters), ("reposters", sc.track_reposters)]:
        offset, limit = 0, 200
        while True:
            batch = fn(int(track_id), limit=limit, offset=offset) or []
            if not batch: break
            if kind == "favoriters": favs.extend(batch)
            else: reps.extend(batch)
            if len(batch) < limit: break
            offset += limit; time.sleep(0.2)

    write_jsonl(raw_dir / f"track_{track_id}_favoriters.jsonl", favs)
    write_jsonl(raw_dir / f"track_{track_id}_reposters.jsonl", reps)
    logger.info(f"favoriters={len(favs)} reposters={len(reps)}")

    # 2) optional: expand to their likes (2-hop signal)
    expand = os.getenv("EXPAND_USER_LIKES", "1") == "1"
    if expand:
        all_users = {u["id"] for u in favs if u.get("id")} | {u["id"] for u in reps if u.get("id")}
        liked_entries = []
        for uid in list(all_users)[:1000]:  # cap for sanity
            offset, limit = 0, 200
            while True:
                likes = sc.user_likes(uid, limit=limit, offset=offset) or []
                if not likes: break
                for tr in likes:
                    liked_entries.append({"user_id": uid, "track": tr})
                if len(likes) < limit: break
                offset += limit; time.sleep(0.2)
        write_jsonl(raw_dir / f"track_{track_id}_userlikes_expanded.jsonl", liked_entries)
        logger.info(f"expanded likes rows={len(liked_entries)}")

    logger.success("interactions ingest complete")
