from __future__ import annotations
import yaml, pandas as pd, sqlalchemy as sa
from dotenv import load_dotenv
from pathlib import Path
from sgr.db.load_tracks import engine_from_env

OUT_DIR = Path("data/dl"); OUT_DIR.mkdir(parents=True, exist_ok=True)

SQL_POS = """
SELECT c.track_id_a::bigint AS a, c.track_id_b::bigint AS b, c.together
FROM track_cooccurrence c
WHERE c.together >= :min_together
"""

SQL_TAGS = """
SELECT track_id::bigint, COALESCE(tags,'') AS tags, COALESCE(genre,'') AS genre,
       COALESCE(artist_id,0)::bigint AS artist_id
FROM tracks
"""

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    pos = pd.read_sql(sa.text(SQL_POS), eng, params={"min_together": 2})
    meta = pd.read_sql(SQL_TAGS, eng)

    # Build tag sets for overlap / negatives
    meta["tagset"] = meta["tags"].fillna("").apply(lambda s: set([t for t in s.split(",") if t]))
    meta = meta.drop(columns=["tags"])
    meta = meta.set_index("track_id")

    # compute a lightweight tag overlap score for positives (for sampling weight)
    def tag_overlap(a,b):
        A = meta.at[a,"tagset"] if a in meta.index else set()
        B = meta.at[b,"tagset"] if b in meta.index else set()
        return len(A & B)

    pos["tag_overlap"] = pos.apply(lambda r: tag_overlap(r["a"], r["b"]), axis=1)
    pos.to_parquet(OUT_DIR/"pairs_positive.parquet", index=False)

    # sample hard negatives: same popularity range / different artist / low tag overlap
    # (simple but effective; better: in-batch hard negatives during training)
    import numpy as np
    tracks = meta.index.values
    neg_rows = []
    rng = np.random.default_rng(42)
    for _, r in pos.sample(min(100000, len(pos)), random_state=42).iterrows():
        a = int(r["a"])
        # sample up to 3 negatives per a
        for _ in range(3):
            b = int(rng.choice(tracks))
            if b == a: continue
            # different artist
            if meta.get("artist_id") is not None:
                if (a in meta.index) and (b in meta.index):
                    if meta.at[a,"artist_id"] == meta.at[b,"artist_id"]:
                        continue
            # low tag overlap
            if tag_overlap(a,b) > 0: 
                continue
            neg_rows.append((a,b))

    pd.DataFrame(neg_rows, columns=["a","b"]).drop_duplicates().to_parquet(OUT_DIR/"pairs_negative.parquet", index=False)
    print("wrote pairs:", list(OUT_DIR.glob("pairs_*.parquet")))
