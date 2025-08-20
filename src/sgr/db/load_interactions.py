from __future__ import annotations
import yaml, pandas as pd, sqlalchemy as sa
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import text
from sgr.db.load_tracks import engine_from_env

def upsert(conn, sql, df):
    if df is None or df.empty: return
    conn.execute(text(sql), df.to_dict(orient="records"))

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    raw = Path(cfg["store"]["raw_dir"])
    staging = Path("data/staging"); staging.mkdir(parents=True, exist_ok=True)

    # Collect any favoriters/reposters files
    fav_users = []; rep_users = []
    for p in raw.glob("track_*_favoriters.jsonl"):
        dfu = pd.read_json(p, lines=True)
        fav_users.append(dfu)
    for p in raw.glob("track_*_reposters.jsonl"):
        dfu = pd.read_json(p, lines=True)
        rep_users.append(dfu)

    users_df = pd.concat(fav_users + rep_users, ignore_index=True) if (fav_users or rep_users) else pd.DataFrame()
    if not users_df.empty:
        users = users_df[["id","username","permalink_url","followers_count","followings_count","verified"]].drop_duplicates("id")
        users.columns = ["user_id","username","permalink_url","followers_count","followings_count","verified"]

    # Expanded likes → likes table
    like_rows = []
    for p in raw.glob("track_*_userlikes_expanded.jsonl"):
        df = pd.read_json(p, lines=True)
        # normalize nested track object
        df["track_id"] = df["track"].apply(lambda t: (t or {}).get("id"))
        df["created_at"] = df["track"].apply(lambda t: (t or {}).get("created_at"))
        df = df[["user_id","track_id","created_at"]].dropna().drop_duplicates()
        like_rows.append(df)
    likes = pd.concat(like_rows, ignore_index=True) if like_rows else pd.DataFrame()

    with eng.begin() as cx:
        if not users_df.empty:
            upsert(cx, """
              INSERT INTO sc_users (user_id, username, permalink_url, followers_count, followings_count, verified)
              VALUES (:user_id, :username, :permalink_url, :followers_count, :followings_count, :verified)
              ON CONFLICT (user_id) DO UPDATE SET
                username=EXCLUDED.username, permalink_url=EXCLUDED.permalink_url,
                followers_count=EXCLUDED.followers_count, followings_count=EXCLUDED.followings_count,
                verified=EXCLUDED.verified
            """, users)

        if not likes.empty:
            upsert(cx, """
              INSERT INTO likes (user_id, track_id, created_at)
              VALUES (:user_id, :track_id, :created_at)
              ON CONFLICT (user_id, track_id) DO NOTHING
            """, likes)

    print("loaded interactions: users=", 0 if users_df.empty else len(users),
          "likes=", 0 if likes.empty else len(likes))
