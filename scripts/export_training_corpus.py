from __future__ import annotations
import yaml, pandas as pd, sqlalchemy as sa
from dotenv import load_dotenv
from pathlib import Path
from sklearn.model_selection import train_test_split
from sgr.db.load_tracks import engine_from_env

OUT_DIR = Path("data/dl")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SQL = """
SELECT
  t.track_id::bigint,
  t.title,
  COALESCE(t.tags,'') AS tags,
  COALESCE(t.description,'') AS description,
  COALESCE(t.genre,'') AS genre,
  t.created_at,
  COALESCE(t.playback_count,0)::bigint AS playback_count,
  COALESCE(t.like_count,0)::bigint AS like_count,
  COALESCE(t.repost_count,0)::bigint AS repost_count,
  COALESCE(a.username, '') AS artist
FROM tracks t
LEFT JOIN artists a ON a.artist_id=t.artist_id
WHERE t.title IS NOT NULL
"""

def build_text(row):
    # compact multilingual text bundle; simple + robust
    parts = [row["title"]]
    if row["tags"]:
        parts.append(row["tags"].replace(",", " "))
    if row["genre"]:
        parts.append(f"genre:{row['genre']}")
    if row["description"]:
        parts.append(row["description"])
    return " ".join([p for p in parts if p]).strip()

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    df = pd.read_sql(SQL, eng)
    df["text"] = df.apply(build_text, axis=1)
    df = df.dropna(subset=["text"]).drop_duplicates(subset=["track_id"])
    # popularity proxy
    df["pop"] = (df["playback_count"].clip(lower=0) + 5*df["like_count"] + 3*df["repost_count"]).astype("int64")

    # chronological split for generalization (fallback to random if many nulls)
    if df["created_at"].notna().sum() > 100:
        df = df.sort_values("created_at")
        n = len(df)
        train = df.iloc[: int(0.8*n)]
        valid = df.iloc[int(0.8*n): int(0.9*n)]
        test  = df.iloc[int(0.9*n): ]
    else:
        train, rest = train_test_split(df, test_size=0.2, random_state=42)
        valid, test = train_test_split(rest, test_size=0.5, random_state=42)

    for name, split in [("train", train), ("valid", valid), ("test", test)]:
        split[["track_id","text","genre","pop","artist"]].to_parquet(OUT_DIR / f"corpus_{name}.parquet", index=False)

    print("wrote:", list(OUT_DIR.glob("corpus_*.parquet")))
