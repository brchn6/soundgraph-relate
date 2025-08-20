from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

def clean_user_list(jsonl_path: Path) -> pd.DataFrame:
    rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            u = json.loads(line)
            rows.append(dict(
                user_id=u.get("id"),
                username=(u.get("username") or ""),
                permalink_url=u.get("permalink_url"),
                followers_count=u.get("followers_count") or 0,
                followings_count=u.get("followings_count") or 0,
                verified=bool(u.get("verified"))
            ))
    return pd.DataFrame(rows).drop_duplicates("user_id")

def clean_userlikes_expanded(jsonl_path: Path) -> pd.DataFrame:
    rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)  # {"user_id":..., "track": {...}}
            t = rec.get("track") or {}
            rows.append(dict(
                user_id=rec.get("user_id"),
                track_id=t.get("id"),
                created_at=t.get("created_at")  # not true like time; placeholder
            ))
    return pd.DataFrame(rows).dropna(subset=["user_id","track_id"]).drop_duplicates(["user_id","track_id"])
