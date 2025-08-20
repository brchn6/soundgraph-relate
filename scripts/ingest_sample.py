from __future__ import annotations
import os, json
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml
from sgr.io.soundcloud_client import make_client_from_env

def main():
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    raw_dir = Path(cfg["store"]["raw_dir"]); raw_dir.mkdir(parents=True, exist_ok=True)
    sc = make_client_from_env()

    query = os.getenv("SAMPLE_QUERY", "lofi")
    out = raw_dir / f"tracks_search_{query}.jsonl"
    logger.info(f"search '{query}' -> {out}")

    total, offset, limit, cap = 0, 0, 50, 1000
    mode = "a" if out.exists() else "w"
    with out.open(mode, encoding="utf-8") as f:
        while total < cap:
            batch = []
            # Prefer v1 + Bearer (works in your env)
            try:
                batch = sc.search_tracks(q=query, limit=limit, offset=offset)
            except Exception as e1:
                logger.warning(f"v1 /tracks failed: {e1}. Trying v2 /search/tracks ...")
                try:
                    batch = sc.search_tracks_v2(q=query, limit=limit, offset=offset)
                except Exception as e2:
                    logger.error(f"v2 also failed: {e2}")
                    break

            batch = batch or []
            if not batch:
                logger.info("No more results.")
                break

            for item in batch:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

            total += len(batch)
            offset += limit
            logger.info(f"fetched {total}")

    logger.success(f"done: {total} rows -> {out}")

if __name__ == "__main__":
    main()
