# Graph Database Migration Guide

This document outlines the migration path from SQLite to a proper graph database (Neo4j or JanusGraph) for the multi-layer music relationship system.

## Why Migrate to a Graph Database?

### Current Limitations (SQLite)
- Complex multi-hop queries require multiple JOIN operations
- Path finding queries are inefficient
- No native graph algorithms (PageRank, community detection, etc.)
- Limited support for graph-specific optimizations

### Benefits of Graph Database
- Native support for relationship traversal
- Efficient multi-hop queries (Cypher/Gremlin)
- Built-in graph algorithms
- Better performance for relationship-heavy queries
- Native support for path finding and pattern matching

## Schema Design for Neo4j

### Node Labels

```cypher
// Track nodes
(:Track {
    track_id: int,
    title: string,
    artist_id: int,
    artist_name: string,
    genre: string,
    playback_count: int,
    like_count: int,
    permalink_url: string
})

// User nodes
(:User {
    user_id: int,
    username: string,
    followers_count: int,
    permalink_url: string
})

// Artist nodes (subset of Users)
(:Artist:User {
    user_id: int,
    username: string,
    verified: boolean
})
```

### Relationship Types

```cypher
// Layer 1: Track-to-Track relationships
(:Track)-[:CO_OCCURS_IN_PLAYLIST {
    weight: float,
    playlist_count: int
}]->(:Track)

// Layer 2: User-to-Track engagement
(:User)-[:LIKES {
    liked_at: datetime
}]->(:Track)

(:User)-[:REPOSTS {
    reposted_at: datetime
}]->(:Track)

// Layer 3: User-to-User relationships
(:User)-[:SIMILAR_TO {
    similarity_type: string,  // 'jaccard_likes', 'cosine_taste'
    score: float,
    common_tracks: int
}]->(:User)

(:User)-[:FOLLOWS {
    followed_at: datetime
}]->(:User)

// Layer 4: Artist-to-Artist relationships
(:Artist)-[:COLLABORATES_WITH {
    strength: float,
    evidence_count: int,
    metadata: map
}]->(:Artist)

(:Artist)-[:CO_LIBRARY {
    strength: float,
    evidence_count: int
}]->(:Artist)
```

## Migration Process

### Step 1: Export Data from SQLite

```python
# export_to_neo4j.py
import sqlite3
import json
from pathlib import Path

def export_nodes_and_relationships(cache_path: str, output_dir: str):
    """Export SQLite data to CSV files for Neo4j import."""
    conn = sqlite3.connect(cache_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Export tracks
    cursor.execute("SELECT * FROM tracks")
    with open(output_path / "tracks.csv", "w") as f:
        f.write("track_id:ID,title,artist_id:int,artist_name,genre,playback_count:int,like_count:int,permalink_url\n")
        for row in cursor.fetchall():
            f.write(f"{row['track_id']},{row['title']},{row['artist_id']},{row['artist_name']},{row['genre']},{row['playback_count']},{row['like_count']},{row['permalink_url']}\n")
    
    # Export users
    cursor.execute("SELECT * FROM users")
    with open(output_path / "users.csv", "w") as f:
        f.write("user_id:ID,username,followers_count:int,permalink_url\n")
        for row in cursor.fetchall():
            f.write(f"{row['user_id']},{row['username']},{row['followers_count']},{row['permalink_url']}\n")
    
    # Export Layer 1: Track relationships
    cursor.execute("SELECT * FROM related_tracks WHERE relation_type = 'co_playlist'")
    with open(output_path / "track_cooccurs.csv", "w") as f:
        f.write(":START_ID,:END_ID,weight:float\n")
        for row in cursor.fetchall():
            f.write(f"{row['src_track_id']},{row['dst_track_id']},{row['weight']}\n")
    
    # Export Layer 2: User engagements
    cursor.execute("SELECT * FROM user_engagements WHERE engagement_type = 'like'")
    with open(output_path / "user_likes.csv", "w") as f:
        f.write(":START_ID,:END_ID,liked_at\n")
        for row in cursor.fetchall():
            f.write(f"{row['user_id']},{row['track_id']},{row['engaged_at']}\n")
    
    # Export Layer 3: User similarities
    cursor.execute("SELECT * FROM user_similarity")
    with open(output_path / "user_similarities.csv", "w") as f:
        f.write(":START_ID,:END_ID,similarity_type,score:float,common_tracks:int\n")
        for row in cursor.fetchall():
            f.write(f"{row['user_id_a']},{row['user_id_b']},{row['similarity_type']},{row['similarity_score']},{row['common_tracks']}\n")
    
    # Export Layer 4: Artist relationships
    cursor.execute("SELECT * FROM artist_relationships")
    with open(output_path / "artist_relationships.csv", "w") as f:
        f.write(":START_ID,:END_ID,relationship_type,strength:float,evidence_count:int\n")
        for row in cursor.fetchall():
            f.write(f"{row['artist_id_a']},{row['artist_id_b']},{row['relationship_type']},{row['strength']},{row['evidence_count']}\n")
    
    conn.close()
```

### Step 2: Import to Neo4j

```cypher
// Create constraints and indexes
CREATE CONSTRAINT track_id_unique IF NOT EXISTS
FOR (t:Track) REQUIRE t.track_id IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.user_id IS UNIQUE;

CREATE INDEX track_genre IF NOT EXISTS
FOR (t:Track) ON (t.genre);

CREATE INDEX user_username IF NOT EXISTS
FOR (u:User) ON (u.username);

// Import tracks
LOAD CSV WITH HEADERS FROM 'file:///tracks.csv' AS row
CREATE (:Track {
    track_id: toInteger(row.track_id),
    title: row.title,
    artist_id: toInteger(row.artist_id),
    artist_name: row.artist_name,
    genre: row.genre,
    playback_count: toInteger(row.playback_count),
    like_count: toInteger(row.like_count),
    permalink_url: row.permalink_url
});

// Import users
LOAD CSV WITH HEADERS FROM 'file:///users.csv' AS row
CREATE (:User {
    user_id: toInteger(row.user_id),
    username: row.username,
    followers_count: toInteger(row.followers_count),
    permalink_url: row.permalink_url
});

// Create Artist label for users who are artists
MATCH (u:User)
WHERE EXISTS {
    MATCH (t:Track {artist_id: u.user_id})
}
SET u:Artist;

// Layer 1: Import track co-occurrences
LOAD CSV WITH HEADERS FROM 'file:///track_cooccurs.csv' AS row
MATCH (t1:Track {track_id: toInteger(row.`:START_ID`)})
MATCH (t2:Track {track_id: toInteger(row.`:END_ID`)})
CREATE (t1)-[:CO_OCCURS_IN_PLAYLIST {
    weight: toFloat(row.weight)
}]->(t2);

// Layer 2: Import user likes
LOAD CSV WITH HEADERS FROM 'file:///user_likes.csv' AS row
MATCH (u:User {user_id: toInteger(row.`:START_ID`)})
MATCH (t:Track {track_id: toInteger(row.`:END_ID`)})
CREATE (u)-[:LIKES {
    liked_at: datetime(row.liked_at)
}]->(t);

// Layer 3: Import user similarities
LOAD CSV WITH HEADERS FROM 'file:///user_similarities.csv' AS row
MATCH (u1:User {user_id: toInteger(row.`:START_ID`)})
MATCH (u2:User {user_id: toInteger(row.`:END_ID`)})
CREATE (u1)-[:SIMILAR_TO {
    similarity_type: row.similarity_type,
    score: toFloat(row.score),
    common_tracks: toInteger(row.common_tracks)
}]->(u2);

// Layer 4: Import artist relationships
LOAD CSV WITH HEADERS FROM 'file:///artist_relationships.csv' AS row
MATCH (a1:Artist {user_id: toInteger(row.`:START_ID`)})
MATCH (a2:Artist {user_id: toInteger(row.`:END_ID`)})
CREATE (a1)-[:COLLABORATES_WITH {
    relationship_type: row.relationship_type,
    strength: toFloat(row.strength),
    evidence_count: toInteger(row.evidence_count)
}]->(a2);
```

## Sample Cypher Queries

### Multi-Hop Track Discovery

```cypher
// Find tracks connected via users (Layer 1 + 2)
MATCH path = (seed:Track {track_id: $seed_track_id})
             -[:CO_OCCURS_IN_PLAYLIST]->(intermediate:Track)
             <-[:LIKES]-(u:User)
             -[:LIKES]->(recommended:Track)
WHERE recommended <> seed
  AND NOT (seed)-[:CO_OCCURS_IN_PLAYLIST]-(recommended)
RETURN DISTINCT recommended.track_id, recommended.title, 
       recommended.artist_name, count(*) as strength
ORDER BY strength DESC
LIMIT 10;
```

### User Taste Communities

```cypher
// Find user communities based on similar taste (Layer 3)
MATCH (seed:User {user_id: $user_id})
      -[:SIMILAR_TO*1..2]-(similar:User)
WHERE similar <> seed
RETURN similar.user_id, similar.username, 
       count(DISTINCT similar) as connection_strength
ORDER BY connection_strength DESC
LIMIT 20;
```

### Artist Collaboration Network

```cypher
// Find collaboration networks (Layer 4)
MATCH path = (seed:Artist {user_id: $artist_id})
             -[:COLLABORATES_WITH*1..3]-(related:Artist)
WHERE related <> seed
RETURN DISTINCT related.user_id, related.username,
       length(path) as degrees_of_separation,
       relationships(path)[0].strength as direct_strength
ORDER BY degrees_of_separation, direct_strength DESC
LIMIT 15;
```

### Cross-Layer Discovery

```cypher
// Find tracks via user similarity and artist collaboration
MATCH (seed:Track {track_id: $seed_track_id})
      <-[:LIKES]-(user1:User)
      -[:SIMILAR_TO]->(user2:User)
      -[:LIKES]->(track2:Track)
      <-[:CREATED_BY]-(artist:Artist)
      -[:COLLABORATES_WITH]->(collaborator:Artist)
      -[:CREATED_BY]->(recommended:Track)
WHERE recommended <> seed
RETURN DISTINCT recommended.track_id, recommended.title,
       artist.username as original_artist,
       collaborator.username as collaborator_artist,
       count(*) as discovery_paths
ORDER BY discovery_paths DESC
LIMIT 10;
```

### Recommendation with Explanation

```cypher
// Get recommendations with explanation paths
MATCH path = (seed:Track {track_id: $seed_track_id})
             -[*1..4]-(recommended:Track)
WHERE recommended <> seed
  AND recommended.playback_count > 1000
WITH recommended, collect(path) as paths, 
     [r in relationships(path) | type(r)] as rel_types
RETURN recommended.track_id, recommended.title, recommended.artist_name,
       length(paths) as connection_strength,
       rel_types[0..3] as explanation_path
ORDER BY connection_strength DESC
LIMIT 10;
```

## Advanced Graph Algorithms

### PageRank for Track Importance

```cypher
// Run PageRank on track co-occurrence network
CALL gds.pageRank.stream({
    nodeProjection: 'Track',
    relationshipProjection: {
        CO_OCCURS_IN_PLAYLIST: {
            properties: 'weight'
        }
    },
    relationshipWeightProperty: 'weight'
})
YIELD nodeId, score
MATCH (t:Track) WHERE id(t) = nodeId
RETURN t.track_id, t.title, t.artist_name, score
ORDER BY score DESC
LIMIT 20;
```

### Community Detection on Users

```cypher
// Find user taste communities using Louvain
CALL gds.louvain.stream({
    nodeProjection: 'User',
    relationshipProjection: {
        SIMILAR_TO: {
            properties: 'score'
        }
    },
    relationshipWeightProperty: 'score'
})
YIELD nodeId, communityId
MATCH (u:User) WHERE id(u) = nodeId
RETURN communityId, collect(u.username) as users, count(*) as size
ORDER BY size DESC
LIMIT 10;
```

### Shortest Path with Relationship Types

```cypher
// Find shortest path between tracks considering multiple relationship types
MATCH path = shortestPath(
    (t1:Track {track_id: $track_id_1})
    -[*..5]-(t2:Track {track_id: $track_id_2})
)
RETURN [node in nodes(path) | 
    CASE 
        WHEN 'Track' IN labels(node) THEN node.title
        WHEN 'User' IN labels(node) THEN node.username
        WHEN 'Artist' IN labels(node) THEN node.username
    END
] as path_nodes,
[rel in relationships(path) | type(rel)] as path_relationships;
```

## Performance Considerations

### Indexes to Create

```cypher
// Track indexes
CREATE INDEX track_artist_id IF NOT EXISTS
FOR (t:Track) ON (t.artist_id);

CREATE INDEX track_genre_playback IF NOT EXISTS
FOR (t:Track) ON (t.genre, t.playback_count);

// User indexes
CREATE INDEX user_followers IF NOT EXISTS
FOR (u:User) ON (u.followers_count);

// Relationship indexes (for path finding)
CREATE INDEX rel_cooccurs_weight IF NOT EXISTS
FOR ()-[r:CO_OCCURS_IN_PLAYLIST]-() ON (r.weight);

CREATE INDEX rel_similarity_score IF NOT EXISTS
FOR ()-[r:SIMILAR_TO]-() ON (r.score);
```

### Query Optimization Tips

1. **Use PROFILE/EXPLAIN**: Always profile complex queries
2. **Limit depth**: Multi-hop queries should limit path length
3. **Filter early**: Apply WHERE clauses as early as possible
4. **Use indexes**: Ensure frequently queried properties are indexed
5. **Batch operations**: Use APOC for large imports/updates

## Incremental Updates

Instead of full rebuilds, use incremental updates:

```cypher
// Add new track with relationships
MERGE (t:Track {track_id: $track_id})
SET t.title = $title,
    t.artist_name = $artist_name,
    t.genre = $genre

WITH t
UNWIND $related_tracks as rel
MATCH (related:Track {track_id: rel.track_id})
MERGE (t)-[r:CO_OCCURS_IN_PLAYLIST]->(related)
SET r.weight = rel.weight;

// Update user engagement
MATCH (u:User {user_id: $user_id})
MATCH (t:Track {track_id: $track_id})
MERGE (u)-[r:LIKES]->(t)
SET r.liked_at = datetime();
```

## Migration Checklist

- [ ] Export all data from SQLite to CSV
- [ ] Set up Neo4j instance (local or cloud)
- [ ] Create constraints and indexes
- [ ] Import nodes (tracks, users)
- [ ] Import Layer 1 relationships (track co-occurrence)
- [ ] Import Layer 2 relationships (user engagements)
- [ ] Import Layer 3 relationships (user similarities)
- [ ] Import Layer 4 relationships (artist collaborations)
- [ ] Verify data integrity
- [ ] Test sample queries
- [ ] Set up incremental update process
- [ ] Update application to use Neo4j driver
- [ ] Performance testing and optimization

## Future Enhancements

1. **Real-time Updates**: Use Neo4j change data capture for real-time sync
2. **Graph Embeddings**: Use Graph Data Science library for node embeddings
3. **ML Integration**: Train recommendation models on graph structure
4. **Graph Visualization**: Use Neo4j Bloom or custom visualizations
5. **Multi-database**: Keep SQLite for caching, Neo4j for queries
