# scripts/ingest_sample.py
from __future__ import annotations
import os, json, time, urllib.parse
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml, requests

BASE = os.getenv("SC_BASE_URL", "https://api.soundcloud.com")

def write_jsonl(path: Path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

def bearer_headers():
    tok = os.getenv("SOUNDCLOUD_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}

def get(url, params=None):
    r = requests.get(url, headers=bearer_headers(), params=params or {}, timeout=30)
    if r.status_code == 429:
        time.sleep(60)
    r.raise_for_status()
    return r.json()

def fetch_tracks(q: str, limit=200, created_from=None, created_to=None, cap=20000):
    """
    Cursor-first pagination. Falls back to offset if API returns a list.
    """
    base_url = f"{BASE}/tracks"
    params = {"q": q, "limit": limit, "linked_partitioning": 1}
    if created_from: params["created_at[from]"] = created_from
    if created_to:   params["created_at[to]"]   = created_to

    total = 0
    # first call
    payload = get(base_url, params)
    # Case A: cursor style (object with 'collection')
    if isinstance(payload, dict) and "collection" in payload:
        while True and total < cap:
            batch = payload.get("collection") or []
            if not batch: break
            yield batch; total += len(batch)
            next_href = payload.get("next_href")
            if not next_href: break
            # next_href already contains query; call directly
            payload = get(next_href)
            time.sleep(0.15)
        return

    # Case B: list style (offset)
    if isinstance(payload, list):
        # re-do with offset loop
        offset = 0
        while total < cap:
            page = get(base_url, {"q": q, "limit": limit, "offset": offset}) or []
            if not page: break
            yield page; total += len(page)
            offset += limit
            time.sleep(0.15)
        return

    # Fallback: nothing
    return

def main():
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    raw_dir = Path(cfg["store"]["raw_dir"]); raw_dir.mkdir(parents=True, exist_ok=True)
    q = os.getenv("SAMPLE_QUERY", "lofi")
    out = raw_dir / f"tracks_search_{q}.jsonl"
    cap = int(os.getenv("CAP", "20000"))
    created_from = os.getenv("CREATED_FROM")  # e.g., "2023-01-01 00:00:00"
    created_to   = os.getenv("CREATED_TO")    # e.g., "2023-12-31 23:59:59"

    logger.info(f"search '{q}' -> {out} (cap={cap}, from={created_from}, to={created_to})")
    total = 0
    for batch in fetch_tracks(q, limit=200, created_from=created_from, created_to=created_to, cap=cap):
        write_jsonl(out, batch)
        total += len(batch)
        logger.info(f"fetched {total}")
    logger.success(f"done: {total} rows -> {out}")

if __name__ == "__main__":
    main()
