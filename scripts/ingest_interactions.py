# scripts/ingest_interactions.py
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

def safe_extract_user_id(user_obj):
    """Safely extract user ID from various API response formats."""
    if isinstance(user_obj, dict):
        return user_obj.get("id")
    elif isinstance(user_obj, str):
        # Sometimes API returns just user ID as string
        try:
            return int(user_obj)
        except (ValueError, TypeError):
            return None
    elif isinstance(user_obj, (int, float)):
        return int(user_obj)
    else:
        logger.warning(f"Unexpected user object format: {type(user_obj)} - {user_obj}")
        return None

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
            try:
                batch = fn(int(track_id), limit=limit, offset=offset) or []
                if not batch: 
                    break
                
                # Debug: check what we got
                logger.debug(f"{kind} batch size: {len(batch)}, first item type: {type(batch[0]) if batch else 'empty'}")
                
                if kind == "favoriters": 
                    favs.extend(batch)
                else: 
                    reps.extend(batch)
                    
                if len(batch) < limit: 
                    break
                offset += limit
                time.sleep(0.2)
                
            except Exception as e:
                logger.warning(f"Error fetching {kind}: {e}")
                break

    # Clean and save favoriters/reposters
    write_jsonl(raw_dir / f"track_{track_id}_favoriters.jsonl", favs)
    write_jsonl(raw_dir / f"track_{track_id}_reposters.jsonl", reps)
    logger.info(f"favoriters={len(favs)} reposters={len(reps)}")

    # 2) optional: expand to their likes (2-hop signal)
    expand = os.getenv("EXPAND_USER_LIKES", "1") == "1"
    if expand:
        # Safely extract user IDs from both favoriters and reposters
        fav_user_ids = {safe_extract_user_id(u) for u in favs}
        rep_user_ids = {safe_extract_user_id(u) for u in reps}
        
        # Remove None values and combine
        all_user_ids = (fav_user_ids | rep_user_ids) - {None}
        
        logger.info(f"Found {len(all_user_ids)} unique users to expand likes for")
        
        if all_user_ids:
            liked_entries = []
            user_count = 0
            
            for uid in list(all_user_ids)[:1000]:  # cap for sanity
                if uid is None:
                    continue
                    
                user_count += 1
                offset, limit = 0, 200
                user_likes_count = 0
                
                while True:
                    try:
                        likes = sc.user_likes(uid, limit=limit, offset=offset) or []
                        if not likes: 
                            break
                            
                        for tr in likes:
                            if tr and tr.get("id"):  # Ensure track object is valid
                                liked_entries.append({"user_id": uid, "track": tr})
                                user_likes_count += 1
                                
                        if len(likes) < limit: 
                            break
                        offset += limit
                        time.sleep(0.2)
                        
                    except Exception as e:
                        logger.warning(f"Error fetching likes for user {uid}: {e}")
                        break
                
                if user_count % 10 == 0:
                    logger.info(f"Processed {user_count}/{len(all_user_ids)} users, total likes collected: {len(liked_entries)}")
                    
            write_jsonl(raw_dir / f"track_{track_id}_userlikes_expanded.jsonl", liked_entries)
            logger.info(f"expanded likes rows={len(liked_entries)}")
        else:
            logger.warning("No valid user IDs found for likes expansion")

    logger.success("interactions ingest complete")