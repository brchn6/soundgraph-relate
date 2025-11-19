from __future__ import annotations
import json
import re
from pathlib import Path
import pandas as pd

HASHTAG = re.compile(r"#(\w+)")

# Function to parse tags
def parse_tags(text: str) -> list[str]:
    if not text:
        return []
    raw = str(text)
    parts = re.split(r"[;,/]", raw)  # Split based on common separators
    tags = {p.strip().lower() for p in parts if p.strip()}
    tags |= {m.group(1).lower() for m in HASHTAG.finditer(raw)}  # Add hashtags
    return sorted(tags)[:20]

# New function to calculate track engagement score
def calculate_engagement_score(playback_count: int, like_count: int, repost_count: int,
                               max_playback: float, max_like: float, max_repost: float) -> float:
    # Normalize each metric to a 0-1 range
    playback_norm = min(playback_count / max_playback, 1.0)
    like_norm = min(like_count / max_like, 1.0)
    repost_norm = min(repost_count / max_repost, 1.0)
    
    # Assign weights to each feature (optional, you can tune this)
    weights = {"playback": 0.5, "like": 0.3, "repost": 0.2}
    
    # Calculate a weighted average for the engagement score
    engagement_score = (playback_norm * weights["playback"] + 
                        like_norm * weights["like"] + 
                        repost_norm * weights["repost"])
    
    return engagement_score

# Function to clean and transform the raw data into DataFrame
def clean_file(in_path: Path) -> pd.DataFrame:
    rows = []
    playback_counts = []
    like_counts = []
    repost_counts = []
    
    # Read the file and extract the counts for normalization
    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            user = obj.get("user") or {}
            
            # Extract relevant features from the raw data
            playback_count = obj.get("playback_count") or 0
            like_count = obj.get("favoritings_count") or 0
            repost_count = obj.get("reposts_count") or 0
            
            # Collect counts for calculating max values
            playback_counts.append(playback_count)
            like_counts.append(like_count)
            repost_counts.append(repost_count)
            
            rows.append(
                dict(
                    track_id=obj.get("id"),
                    title=(obj.get("title") or "").strip(),
                    description=(obj.get("description") or "")[:2000],
                    tag_list=obj.get("tag_list") or "",
                    # CHANGED: Return list for TEXT[] mapping
                    tags=list(parse_tags(obj.get("tag_list") or "")),
                    genre=(obj.get("genre") or "").lower(),
                    user_id=user.get("id"),
                    username=user.get("username"),
                    created_at=obj.get("created_at"),
                    duration=obj.get("duration"),
                    bpm=obj.get("bpm"),
                    key=obj.get("key_signature") or None,
                    playback_count=playback_count,
                    like_count=like_count,
                    repost_count=repost_count,
                    permalink_url=obj.get("permalink_url"),
                    streamable=bool(obj.get("streamable")),
                )
            )

    # Calculate the max values for normalization based on the data
    max_playback = max(playback_counts) if playback_counts else 1
    max_like = max(like_counts) if like_counts else 1
    max_repost = max(repost_counts) if repost_counts else 1

    # Add engagement score to each track
    for row in rows:
        row["engagement_score"] = calculate_engagement_score(
            row["playback_count"], row["like_count"], row["repost_count"],
            max_playback, max_like, max_repost
        )
    
    # Convert to DataFrame
    return pd.DataFrame(rows)

# Main block to process files and save the cleaned data
if __name__ == "__main__":
    raw = Path("data/raw")
    staging = Path("data/staging")
    staging.mkdir(parents=True, exist_ok=True)
    
    # Find raw files
    files = list(raw.glob("tracks_search_*.jsonl"))
    if not files:
        print("No raw files found in data/raw. Run scripts/ingest_sample.py first.")
    
    # Process each file
    for p in files:
        df = clean_file(p)
        out = staging / (p.stem + ".parquet")
        df.to_parquet(out, index=False)
        print("wrote", out, len(df))