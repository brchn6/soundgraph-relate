from __future__ import annotations
import yaml, sqlalchemy as sa
from dotenv import load_dotenv
from sgr.db.load_tracks import engine_from_env

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    with eng.begin() as cx:
        # CONCURRENTLY needs an index and a separate tx; simple refresh is fine here
        cx.execute(sa.text("REFRESH MATERIALIZED VIEW track_cooccurrence;"))
    print("Refreshed track_cooccurrence.")
