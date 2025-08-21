CREATE TABLE IF NOT EXISTS artists (
  artist_id BIGINT PRIMARY KEY,
  username TEXT,
  verified BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS tracks (
  track_id BIGINT PRIMARY KEY,
  artist_id BIGINT,
  title TEXT,
  description TEXT,
  genre TEXT,
  tags TEXT,
  created_at TIMESTAMPTZ NULL,
  duration_ms INT,
  bpm NUMERIC NULL,
  musical_key TEXT NULL,
  playback_count BIGINT DEFAULT 0,
  like_count BIGINT DEFAULT 0,
  repost_count BIGINT DEFAULT 0,
  permalink_url TEXT,
  streamable BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (artist_id) REFERENCES artists(artist_id)
);

CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_playback ON tracks(playback_count DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_created ON tracks(created_at DESC);


-- USERS (listeners or artists; we keep artists separately for clarity)
CREATE TABLE IF NOT EXISTS sc_users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  permalink_url TEXT,
  followers_count BIGINT DEFAULT 0,
  followings_count BIGINT DEFAULT 0,
  verified BOOLEAN DEFAULT FALSE
);

-- PLAYLISTS
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

-- BRIDGE: playlist <-> tracks
CREATE TABLE IF NOT EXISTS playlist_tracks (
  playlist_id BIGINT,
  track_id BIGINT,
  position INT,
  PRIMARY KEY (playlist_id, track_id),
  FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

-- OPTIONAL INTERACTIONS (only if available via public endpoints in your region):
CREATE TABLE IF NOT EXISTS likes (
  user_id BIGINT,
  track_id BIGINT,
  liked_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id),
  FOREIGN KEY (user_id) REFERENCES sc_users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

CREATE TABLE IF NOT EXISTS reposts (
  user_id BIGINT,
  track_id BIGINT,
  reposted_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id),
  FOREIGN KEY (user_id) REFERENCES sc_users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);

CREATE TABLE IF NOT EXISTS comments (
  comment_id BIGINT PRIMARY KEY,
  track_id BIGINT,
  user_id BIGINT,
  body TEXT,
  created_at TIMESTAMPTZ NULL,
  FOREIGN KEY (track_id) REFERENCES tracks(track_id),
  FOREIGN KEY (user_id) REFERENCES sc_users(user_id)
);

-- helpful indexes
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks(track_id);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks(playlist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_tags_gin ON tracks USING GIN (to_tsvector('simple', tags));
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);

-- simple co-occurrence materialized view (recompute on demand)
CREATE MATERIALIZED VIEW IF NOT EXISTS track_cooccurrence AS
SELECT a.track_id AS track_id_a, b.track_id AS track_id_b, COUNT(*) AS together
FROM playlist_tracks a
JOIN playlist_tracks b
  ON a.playlist_id = b.playlist_id AND a.track_id <> b.track_id
GROUP BY 1,2;

CREATE INDEX IF NOT EXISTS idx_cooccur_a ON track_cooccurrence(track_id_a, together DESC);


-- Users already exist as sc_users

CREATE TABLE IF NOT EXISTS likes (
  user_id   BIGINT NOT NULL,
  track_id  BIGINT NOT NULL,
  created_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id),
  FOREIGN KEY (user_id)  REFERENCES sc_users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);
CREATE INDEX IF NOT EXISTS idx_likes_track ON likes(track_id);

CREATE TABLE IF NOT EXISTS reposts (
  user_id   BIGINT NOT NULL,
  track_id  BIGINT NOT NULL,
  created_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id),
  FOREIGN KEY (user_id)  REFERENCES sc_users(user_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);
CREATE INDEX IF NOT EXISTS idx_reposts_track ON reposts(track_id);
