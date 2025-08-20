from __future__ import annotations
import yaml, torch, pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import sqlalchemy as sa
from sgr.db.load_tracks import engine_from_env

OUT_DIR = Path("data/gnn"); OUT_DIR.mkdir(parents=True, exist_ok=True)

SQL_TRACKS = """
SELECT t.track_id::bigint AS track_id,
       COALESCE(t.genre,'') AS genre,
       COALESCE(t.playback_count,0)::bigint AS playback_count,
       COALESCE(t.like_count,0)::bigint AS like_count,
       COALESCE(t.repost_count,0)::bigint AS repost_count
FROM tracks t
"""

SQL_EDGES = """
SELECT c.track_id_a::bigint AS a, c.track_id_b::bigint AS b, c.together
FROM track_cooccurrence c
WHERE c.together >= :min_together
"""

def numerics(df):
    import numpy as np
    x = pd.DataFrame({
        "pop": (df["playback_count"] + 5*df["like_count"] + 3*df["repost_count"]).astype("float32")
    })
    x["pop"] = np.log1p(x["pop"])
    # simple normalization
    x = (x - x.mean()) / (x.std() + 1e-6)
    return torch.tensor(x.values, dtype=torch.float32)

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)

    tracks = pd.read_sql(SQL_TRACKS, eng).drop_duplicates("track_id").reset_index(drop=True)
    id2idx = {tid:i for i,tid in enumerate(tracks["track_id"].tolist())}

    edges = pd.read_sql(sa.text(SQL_EDGES), eng, params={"min_together": 2})
    edges = edges[edges["a"].isin(id2idx) & edges["b"].isin(id2idx)]
    src = edges["a"].map(id2idx).astype("int64").values
    dst = edges["b"].map(id2idx).astype("int64").values

    # undirected graph
    import numpy as np
    src = np.concatenate([src, dst]); dst = np.concatenate([dst, src[:len(dst)]])
    edge_index = torch.tensor([src, dst], dtype=torch.long)

    x = numerics(tracks)
    torch.save({"edge_index": edge_index,
                "x": x,
                "track_ids": torch.tensor(tracks["track_id"].values, dtype=torch.long)}, OUT_DIR/"track_graph.pt")
    print("wrote", OUT_DIR/"track_graph.pt", "nodes:", x.shape[0], "edges:", edge_index.shape[1])
