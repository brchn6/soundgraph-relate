# scripts/ingest_sample.py
from __future__ import annotations
import os, json, time, urllib.parse
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
import yaml, requests
from datetime import datetime, timedelta

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

def fetch_tracks(q: str, limit=500, created_from=None, created_to=None, cap=20000):
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

def ingest_rolling_window(q: str, out_path: Path, days_back=365, step_days=7, cap=20000):
    """
    Splits the search into small weekly chunks to bypass API depth limits.
    """
    total_collected = 0
    
    # Search backwards from today
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    current_start = start_date
    
    logger.info(f"Starting Rolling Window Ingest: {days_back} days history, {step_days} day steps")

    while current_start < end_date and total_collected < cap:
        # Define window: current to current + step
        current_end = min(current_start + timedelta(days=step_days), end_date)
        
        # SoundCloud API format: YYYY-MM-DD HH:MM:SS
        fmt = "%Y-%m-%d %H:%M:%S"
        s_str = current_start.strftime(fmt)
        e_str = current_end.strftime(fmt)
        
        logger.info(f"  [Window] {s_str} ... {e_str}")
        
        # Fetch for just this narrow window
        # Note: We reset the batch cap so we get all results for this specific week
        window_hits = 0
        for batch in fetch_tracks(q, limit=200, created_from=s_str, created_to=e_str, cap=2000):
            if not batch: continue
            write_jsonl(out_path, batch)
            window_hits += len(batch)
            total_collected += len(batch)
        
        logger.info(f"    -> Found {window_hits} tracks (Total: {total_collected})")
        
        # Move to next window
        current_start = current_end

    logger.success(f"Rolling ingest complete. Total: {total_collected}")


def main():
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    raw_dir = Path(cfg["store"]["raw_dir"]); raw_dir.mkdir(parents=True, exist_ok=True)
    
    q = os.getenv("SAMPLE_QUERY", "lofi")
    out = raw_dir / f"tracks_search_{q}.jsonl"
    cap = int(os.getenv("CAP", "20000"))
    
    # --- NEW LOGIC STARTS HERE ---
    # If user provides explicit dates, use the old simple method (single fetch)
    if os.getenv("CREATED_FROM") or os.getenv("CREATED_TO"):
        created_from = os.getenv("CREATED_FROM")
        created_to   = os.getenv("CREATED_TO")
        logger.info(f"Manual date range provided: {created_from} -> {created_to}")
        
        total = 0
        for batch in fetch_tracks(q, limit=200, created_from=created_from, created_to=created_to, cap=cap):
            write_jsonl(out, batch)
            total += len(batch)
        logger.success(f"Manual fetch done: {total}")
        
    else:
        # Otherwise, use the automated rolling window to get MAXIMUM tracks
        ingest_rolling_window(q, out, days_back=365, step_days=14, cap=cap)

        
if __name__ == "__main__":
    main()
