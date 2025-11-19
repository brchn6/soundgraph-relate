-- === EXTENSIONS =============================================================
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- === ENTITIES ===============================================================

CREATE TABLE IF NOT EXISTS artists (
  artist_id    BIGINT PRIMARY KEY,
  username     TEXT NOT NULL,
  verified     BOOLEAN DEFAULT FALSE,
  permalink_url TEXT,
  raw          JSONB,                 -- full API blob for provenance
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sc_users (
  user_id          BIGINT PRIMARY KEY,
  username         TEXT NOT NULL,
  permalink_url    TEXT,
  followers_count  BIGINT DEFAULT 0 CHECK (followers_count >= 0),
  followings_count BIGINT DEFAULT 0 CHECK (followings_count >= 0),
  verified         BOOLEAN DEFAULT FALSE,
  raw              JSONB,
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- optional: who-follows-who
CREATE TABLE IF NOT EXISTS user_follow (
  follower_id BIGINT NOT NULL REFERENCES sc_users(user_id) ON DELETE CASCADE,
  followee_id BIGINT NOT NULL REFERENCES sc_users(user_id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NULL,
  PRIMARY KEY (follower_id, followee_id)
);

CREATE TABLE IF NOT EXISTS tracks (
  track_id       BIGINT PRIMARY KEY,
  artist_id      BIGINT REFERENCES artists(artist_id) ON DELETE SET NULL,
  title          TEXT NOT NULL,
  description    TEXT,
  genre          TEXT,
  tags           TEXT[],             -- array of tags for fast membership ops
  created_at     TIMESTAMPTZ NULL,
  duration_ms    INT CHECK (duration_ms IS NULL OR duration_ms >= 0),
  bpm            NUMERIC NULL,
  musical_key    TEXT NULL,
  playback_count BIGINT DEFAULT 0 CHECK (playback_count >= 0),
  like_count     BIGINT DEFAULT 0 CHECK (like_count >= 0),
  repost_count   BIGINT DEFAULT 0 CHECK (repost_count >= 0),
  comment_count  BIGINT DEFAULT 0 CHECK (comment_count >= 0),
  license        TEXT,
  release_date   DATE,
  permalink_url  TEXT,
  streamable     BOOLEAN DEFAULT FALSE,
  raw            JSONB
  -- ,emb vector(384)            -- pgvector (enable after CREATE EXTENSION vector)
);

CREATE INDEX IF NOT EXISTS idx_tracks_genre          ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_playback_desc  ON tracks(playback_count DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_created_desc   ON tracks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_artist         ON tracks(artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_tags_gin       ON tracks USING GIN (tags);

CREATE TABLE IF NOT EXISTS playlists (
  playlist_id      BIGINT PRIMARY KEY,
  title            TEXT NOT NULL,
  description      TEXT,
  creator_user_id  BIGINT REFERENCES sc_users(user_id) ON DELETE SET NULL,
  genre            TEXT,
  tag_list         TEXT[],           -- normalized tags
  created_at       TIMESTAMPTZ NULL,
  track_count      INT DEFAULT 0 CHECK (track_count >= 0),
  permalink_url    TEXT,
  raw              JSONB
  -- ,emb vector(384)
);

CREATE INDEX IF NOT EXISTS idx_playlists_creator ON playlists(creator_user_id);
CREATE INDEX IF NOT EXISTS idx_playlists_tags_gin ON playlists USING GIN (tag_list);

-- === BRIDGES & INTERACTIONS ================================================

-- playlist membership (preserve order); CASCADE is safe for pure join tables
CREATE TABLE IF NOT EXISTS playlist_tracks (
  playlist_id BIGINT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
  track_id    BIGINT NOT NULL REFERENCES tracks(track_id)       ON DELETE CASCADE,
  position    INT,     -- 1-based ordering if available
  added_at    TIMESTAMPTZ NULL,
  PRIMARY KEY (playlist_id, track_id)
);

-- ensure no duplicate positions within a playlist
CREATE UNIQUE INDEX IF NOT EXISTS uniq_playlist_pos
  ON playlist_tracks(playlist_id, position)
  WHERE position IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track    ON playlist_tracks(track_id);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks(playlist_id);

-- likes
CREATE TABLE IF NOT EXISTS likes (
  user_id    BIGINT NOT NULL REFERENCES sc_users(user_id) ON DELETE CASCADE,
  track_id   BIGINT NOT NULL REFERENCES tracks(track_id)  ON DELETE CASCADE,
  liked_at   TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id)
);
CREATE INDEX IF NOT EXISTS idx_likes_track ON likes(track_id);
CREATE INDEX IF NOT EXISTS idx_likes_user  ON likes(user_id);

-- reposts (tracks)
CREATE TABLE IF NOT EXISTS reposts (
  user_id     BIGINT NOT NULL REFERENCES sc_users(user_id) ON DELETE CASCADE,
  track_id    BIGINT NOT NULL REFERENCES tracks(track_id)  ON DELETE CASCADE,
  reposted_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, track_id)
);
CREATE INDEX IF NOT EXISTS idx_reposts_track ON reposts(track_id);
CREATE INDEX IF NOT EXISTS idx_reposts_user  ON reposts(user_id);

-- reposts (playlists), handy for graph edges user→playlist
CREATE TABLE IF NOT EXISTS playlist_reposts (
  user_id     BIGINT NOT NULL REFERENCES sc_users(user_id)  ON DELETE CASCADE,
  playlist_id BIGINT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
  reposted_at TIMESTAMPTZ NULL,
  PRIMARY KEY (user_id, playlist_id)
);

-- comments
CREATE TABLE IF NOT EXISTS comments (
  comment_id BIGINT PRIMARY KEY,
  track_id   BIGINT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
  user_id    BIGINT NOT NULL REFERENCES sc_users(user_id) ON DELETE CASCADE,
  body       TEXT,
  created_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_track ON comments(track_id);
CREATE INDEX IF NOT EXISTS idx_comments_user  ON comments(user_id);

-- track→track related edges (from API or your mining)
CREATE TABLE IF NOT EXISTS related_tracks (
  src_track_id BIGINT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
  dst_track_id BIGINT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
  score        REAL,
  source       TEXT NOT NULL,     -- 'soundcloud' | 'co_playlist' | 'embedding' ...
  updated_at   TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (src_track_id, dst_track_id, source)
);
CREATE INDEX IF NOT EXISTS idx_related_src_score ON related_tracks(src_track_id, score DESC);

-- === CO-OCCURRENCE VIEW =====================================================

-- Weighted co-occurrence: inverse playlist size down-weights huge playlists
CREATE MATERIALIZED VIEW IF NOT EXISTS track_cooccurrence AS
WITH pl_sizes AS (
  SELECT playlist_id, COUNT(*)::REAL AS n
  FROM playlist_tracks
  GROUP BY 1
),
pairs AS (
  SELECT a.track_id AS track_id_a,
         b.track_id AS track_id_b,
         1.0 / NULLIF(ps.n, 0) AS w
  FROM playlist_tracks a
  JOIN playlist_tracks b
    ON a.playlist_id = b.playlist_id
   AND a.track_id <> b.track_id
  JOIN pl_sizes ps USING (playlist_id)
)
SELECT track_id_a, track_id_b,
       COUNT(*)        AS together,
       SUM(w)          AS weight
FROM pairs
GROUP BY 1,2;

CREATE INDEX IF NOT EXISTS idx_cooccur_a ON track_cooccurrence(track_id_a, weight DESC);

-- === OPTIONAL: pgvector setup ===============================================
-- CREATE INDEX IF NOT EXISTS idx_track_emb_ivf   ON tracks    USING ivfflat (emb vector_cosine) WITH (lists=100);
-- CREATE INDEX IF NOT EXISTS idx_pl_emb_ivf      ON playlists USING ivfflat (emb vector_cosine) WITH (lists=100);
