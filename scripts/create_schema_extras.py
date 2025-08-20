from __future__ import annotations
import os, yaml, sqlalchemy as sa
from dotenv import load_dotenv
from sgr.db.load_tracks import engine_from_env

EXTRA_SQL = """
CREATE TABLE IF NOT EXISTS sc_users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  permalink_url TEXT,
  followers_count BIGINT DEFAULT 0,
  followings_count BIGINT DEFAULT 0,
  verified BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS playlists (
  playlist_id BIGINT PRIMARY KEY,
  title TEXT,
  description TEXT,
  creator_user_id BIGINT,
  genre TEXT,
  tag_list TEXT,
  created_at TIMESTAMPTZ NULL,
  track_count INT DEFAULT 0,
  permalink_url TEXT,
  FOREIGN KEY (creator_user_id) REFERENCES sc_users(user_id)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
  playlist_id BIGINT,
  track_id BIGINT,
  position INT,
  PRIMARY KEY (playlist_id, track_id),
  FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

-- Co-occurrence MV
CREATE MATERIALIZED VIEW IF NOT EXISTS track_cooccurrence AS
SELECT a.track_id AS track_id_a, b.track_id AS track_id_b, COUNT(*) AS together
FROM playlist_tracks a
JOIN playlist_tracks b
  ON a.playlist_id = b.playlist_id AND a.track_id <> b.track_id
GROUP BY 1,2;

CREATE INDEX IF NOT EXISTS idx_cooccur_a ON track_cooccurrence(track_id_a, together DESC);
"""

if __name__ == "__main__":
    load_dotenv()
    cfg = yaml.safe_load(open("configs/config.yaml"))
    eng = engine_from_env(cfg)
    with eng.begin() as cx:
        cx.execute(sa.text(EXTRA_SQL))
    print("Extra schema ensured (users/playlists/playlist_tracks + cooccurrence MV).")
