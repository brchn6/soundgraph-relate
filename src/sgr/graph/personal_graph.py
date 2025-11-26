"""
Personal music graph representation using NetworkX.

This module provides a graph-based view of music relationships,
built from cached track data.

Supports multi-layer relationships:
- Layer 1: Track-to-Track (playlist co-occurrence)
- Layer 2: User-to-Track (likes, reposts)
- Layer 3: User-to-User (taste similarity)
- Layer 4: Artist-to-Artist (collaborations)
"""

from __future__ import annotations
import networkx as nx
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path
import json
from loguru import logger
import collections

from sgr.cache.track_cache import TrackCache


class PersonalGraph:
    """
    NetworkX-based representation of a personal music knowledge graph.
    
    Nodes represent:
    - Tracks (with metadata like title, artist, genre)
    - Users (with engagement data)
    - Artists (with relationship data)
    
    Edges represent:
    - Layer 1: Track-to-Track (co-occurrence in playlists)
    - Layer 2: User-to-Track (likes, reposts)
    - Layer 3: User-to-User (taste similarity, follows)
    - Layer 4: Artist-to-Artist (collaborations, co-library)
    """
    
    def __init__(self, cache: TrackCache, enable_multi_layer: bool = False):
        """
        Initialize a personal graph.
        
        Args:
            cache: Track cache instance to load data from
            enable_multi_layer: Enable multi-layer relationship loading
        """
        self.cache = cache
        self.graph = nx.MultiDiGraph()
        self._track_nodes = set()
        self._user_nodes = set()
        self._artist_nodes = set()
        self.enable_multi_layer = enable_multi_layer
    
    def build_from_seed(self, seed_track_id: int, max_depth: int = 2, 
                       layers: Optional[Set[int]] = None,
                       batch_size: int = 50) -> Dict[str, Any]:
        """
        Build the graph starting from a seed track.
        
        Uses BFS to expand from the seed track through related tracks.
        Optionally includes multi-layer relationships (users, artist connections).
        
        Args:
            seed_track_id: The starting track ID
            max_depth: Maximum depth to expand (number of hops)
            layers: Set of layers to include (1, 2, 3, 4). None = Layer 1 only.
            batch_size: Number of tracks to process in each batch for better performance
            
        Returns:
            Statistics about the built graph
        """
        if layers is None:
            layers = {1}  # Default to Layer 1 only (backward compatible)
        
        logger.info(f"Building graph from seed track {seed_track_id}, max_depth={max_depth}, layers={layers}")
        
        visited = set()
        queue = collections.deque([(seed_track_id, 0)])
        
        while queue:
            current_batch = []
            # Collect batch of tracks to process
            while queue and len(current_batch) < batch_size:
                track_id, depth = queue.popleft()
                if track_id not in visited and depth <= max_depth:
                    current_batch.append((track_id, depth))
                    visited.add(track_id)
            
            if not current_batch:
                break
            
            # Process batch
            for track_id, depth in current_batch:
                track_data = self.cache.get_track(track_id)
                if not track_data:
                    continue
                
                self._add_track_node(track_id, track_data)
                
                # Layer 1: Track-to-Track relationships
                if 1 in layers and depth < max_depth:
                    related = self.cache.get_related_tracks(track_id, limit=20)
                    for rel in related:
                        rel_track_id = rel["track_id"]
                        weight = rel.get("weight", 1.0)
                        relation_type = rel.get("relation_type", "related")
                        
                        # Add edge
                        self.graph.add_edge(
                            track_id, 
                            rel_track_id,
                            weight=weight,
                            relation=relation_type,
                            layer=1
                        )
                        
                        # Queue for expansion
                        if rel_track_id not in visited:
                            queue.append((rel_track_id, depth + 1))
                
                # Layer 2: User-to-Track relationships
                if 2 in layers and self.enable_multi_layer:
                    self._add_layer2_relationships(track_id)
                
                # Layer 4: Artist relationships
                if 4 in layers and self.enable_multi_layer:
                    artist_id = track_data.get("artist_id")
                    if artist_id:
                        self._add_layer4_relationships(artist_id)
        
        # Layer 3: User-to-User relationships (process after all users are added)
        if 3 in layers and self.enable_multi_layer:
            self._add_layer3_relationships()
        
        stats = {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "track_nodes": len(self._track_nodes),
            "user_nodes": len(self._user_nodes),
            "artist_nodes": len(self._artist_nodes),
            "seed_track_id": seed_track_id,
            "max_depth": max_depth,
            "layers_included": list(layers)
        }
        
        logger.success(f"Graph built: {stats['nodes']} nodes, {stats['edges']} edges, layers={layers}")
        return stats
    
    def _add_track_node(self, track_id: int, track_data: Dict[str, Any]):
        """Add a track as a node to the graph."""
        if track_id in self._track_nodes:
            return
        
        self.graph.add_node(
            track_id,
            node_type="track",
            title=track_data.get("title", "Untitled"),
            artist_name=track_data.get("artist_name", "Unknown"),
            artist_id=track_data.get("artist_id"),
            genre=track_data.get("genre"),
            playback_count=track_data.get("playback_count", 0),
            like_count=track_data.get("like_count", 0),
            permalink_url=track_data.get("permalink_url")
        )
        
        self._track_nodes.add(track_id)
    
    def _add_user_node(self, user_id: int, user_data: Optional[Dict[str, Any]] = None):
        """Add a user as a node to the graph."""
        if user_id in self._user_nodes:
            return
        
        if user_data is None:
            # Try to get from cache
            cursor = self.cache.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                user_data = dict(row)
        
        username = user_data.get("username", f"User {user_id}") if user_data else f"User {user_id}"
        followers = user_data.get("followers_count", 0) if user_data else 0
        
        self.graph.add_node(
            f"user_{user_id}",  # Prefix to avoid ID conflicts with tracks
            node_type="user",
            user_id=user_id,
            username=username,
            followers_count=followers
        )
        
        self._user_nodes.add(user_id)
    
    def _add_artist_node(self, artist_id: int):
        """Add an artist as a node to the graph."""
        if artist_id in self._artist_nodes:
            return
        
        # Get artist info from users table (artists are users in SoundCloud)
        cursor = self.cache.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (artist_id,))
        row = cursor.fetchone()
        
        artist_name = f"Artist {artist_id}"
        if row:
            artist_data = dict(row)
            artist_name = artist_data.get("username", artist_name)
        
        self.graph.add_node(
            f"artist_{artist_id}",  # Prefix to avoid conflicts
            node_type="artist",
            artist_id=artist_id,
            artist_name=artist_name
        )
        
        self._artist_nodes.add(artist_id)
    
    def _add_layer2_relationships(self, track_id: int):
        """Add Layer 2: User-to-Track engagement relationships."""
        # Get users who engaged with this track
        engagers = self.cache.get_track_engagers(track_id, limit=50)
        
        for engager in engagers:
            user_id = engager.get("user_id")
            if not user_id:
                continue
            
            # Add user node
            self._add_user_node(user_id, engager)
            
            # Add edge from user to track
            self.graph.add_edge(
                f"user_{user_id}",
                track_id,
                relation=engager.get("engagement_type", "engagement"),
                layer=2,
                weight=1.0
            )
    
    def _add_layer3_relationships(self):
        """Add Layer 3: User-to-User similarity relationships."""
        # For all users in the graph, add similarity edges
        for user_id in list(self._user_nodes):
            similar_users = self.cache.get_similar_users(user_id, min_score=0.2, limit=20)
            
            for similar in similar_users:
                similar_user_id = similar.get("similar_user_id")
                if not similar_user_id:
                    continue
                
                # Add similar user node if not already present
                self._add_user_node(similar_user_id)
                
                # Add bidirectional similarity edge
                score = similar.get("similarity_score", 0.5)
                self.graph.add_edge(
                    f"user_{user_id}",
                    f"user_{similar_user_id}",
                    relation=similar.get("similarity_type", "similar"),
                    layer=3,
                    weight=score,
                    common_tracks=similar.get("common_tracks", 0)
                )
    
    def _add_layer4_relationships(self, artist_id: int):
        """Add Layer 4: Artist-to-Artist relationships."""
        # Add artist node
        self._add_artist_node(artist_id)
        
        # Get related artists
        related_artists = self.cache.get_related_artists(artist_id, min_strength=0.3, limit=20)
        
        for related in related_artists:
            related_artist_id = related.get("related_artist_id")
            if not related_artist_id:
                continue
            
            # Add related artist node
            self._add_artist_node(related_artist_id)
            
            # Add edge
            strength = related.get("strength", 0.5)
            self.graph.add_edge(
                f"artist_{artist_id}",
                f"artist_{related_artist_id}",
                relation=related.get("relationship_type", "related"),
                layer=4,
                weight=strength,
                evidence_count=related.get("evidence_count", 1)
            )
    
    def get_neighbors(self, track_id: int, limit: int = 10, layer: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes in the graph.
        
        Args:
            track_id: The track ID
            limit: Maximum neighbors to return
            layer: Filter by layer (None for all layers)
            
        Returns:
            List of neighbor dicts with edge weights
        """
        if track_id not in self.graph:
            return []
        
        neighbors = []
        for neighbor_id in self.graph.neighbors(track_id):
            # MultiDiGraph can have multiple edges
            edges = self.graph[track_id][neighbor_id]
            
            # Handle both single edge and multiple edges
            if isinstance(edges, dict):
                edges = {0: edges}  # Convert to dict format
            
            for edge_key, edge_data in edges.items():
                edge_layer = edge_data.get("layer", 1)
                
                # Filter by layer if specified
                if layer is not None and edge_layer != layer:
                    continue
                
                node_data = self.graph.nodes[neighbor_id]
                node_type = node_data.get("node_type", "track")
                
                neighbor_info = {
                    "node_id": neighbor_id,
                    "node_type": node_type,
                    "weight": edge_data.get("weight", 1.0),
                    "relation": edge_data.get("relation", "related"),
                    "layer": edge_layer
                }
                
                # Add type-specific fields
                if node_type == "track":
                    neighbor_info.update({
                        "track_id": neighbor_id,
                        "title": node_data.get("title"),
                        "artist_name": node_data.get("artist_name")
                    })
                elif node_type == "user":
                    neighbor_info.update({
                        "user_id": node_data.get("user_id"),
                        "username": node_data.get("username")
                    })
                elif node_type == "artist":
                    neighbor_info.update({
                        "artist_id": node_data.get("artist_id"),
                        "artist_name": node_data.get("artist_name")
                    })
                
                neighbors.append(neighbor_info)
        
        # Sort by weight descending
        neighbors.sort(key=lambda x: x["weight"], reverse=True)
        return neighbors[:limit]
    
    def get_multi_layer_path(self, src_id: Any, dst_id: Any, 
                            max_length: int = 5) -> Optional[List[Tuple[Any, str]]]:
        """
        Find a path between two nodes in the multi-layer graph.
        
        Args:
            src_id: Source node ID (can be track, user, or artist node)
            dst_id: Destination node ID
            max_length: Maximum path length
            
        Returns:
            List of (node_id, relation_type) tuples forming the path, or None
        """
        try:
            path = nx.shortest_path(self.graph, src_id, dst_id)
            
            # Add edge labels
            path_with_relations = []
            for i, node in enumerate(path):
                if i < len(path) - 1:
                    next_node = path[i + 1]
                    # Get edge data
                    edges = self.graph[node][next_node]
                    if isinstance(edges, dict):
                        # Get first edge if multiple
                        edge_data = list(edges.values())[0] if edges else {}
                    else:
                        edge_data = edges
                    
                    relation = edge_data.get("relation", "connected")
                    path_with_relations.append((node, relation))
                else:
                    path_with_relations.append((node, None))
            
            if len(path) <= max_length:
                return path_with_relations
            return None
            
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    
    def get_path(self, src_track_id: int, dst_track_id: int) -> Optional[List[int]]:
        """
        Find the shortest path between two tracks.
        
        Args:
            src_track_id: Source track ID
            dst_track_id: Destination track ID
            
        Returns:
            List of track IDs forming the path, or None if no path exists
        """
        try:
            return nx.shortest_path(self.graph, src_track_id, dst_track_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    
    def get_recommendations(self, track_id: int, limit: int = 10, 
                           min_common_neighbors: int = 2) -> List[Dict[str, Any]]:
        """
        Get track recommendations based on graph structure.
        
        Uses a simple collaborative filtering approach:
        - Find tracks that share multiple neighbors with the seed track
        - Rank by number of common neighbors and edge weights
        
        Args:
            track_id: The seed track ID
            limit: Maximum recommendations to return
            min_common_neighbors: Minimum common neighbors required
            
        Returns:
            List of recommended track dicts
        """
        if track_id not in self.graph:
            return []
        
        # Get direct neighbors (already connected)
        direct_neighbors = set(self.graph.neighbors(track_id))
        
        # Find tracks at distance 2 (neighbors of neighbors)
        candidates = {}
        for neighbor in direct_neighbors:
            for candidate in self.graph.neighbors(neighbor):
                if candidate == track_id or candidate in direct_neighbors:
                    continue
                
                if candidate not in candidates:
                    candidates[candidate] = {
                        "common_neighbors": set(),
                        "total_weight": 0.0
                    }
                
                candidates[candidate]["common_neighbors"].add(neighbor)
                # Add edge weight
                weight = self.graph[neighbor][candidate].get("weight", 1.0)
                candidates[candidate]["total_weight"] += weight
        
        # Filter and rank
        recommendations = []
        for candidate_id, data in candidates.items():
            num_common = len(data["common_neighbors"])
            if num_common < min_common_neighbors:
                continue
            
            node_data = self.graph.nodes[candidate_id]
            recommendations.append({
                "track_id": candidate_id,
                "title": node_data.get("title"),
                "artist_name": node_data.get("artist_name"),
                "genre": node_data.get("genre"),
                "common_neighbors": num_common,
                "score": data["total_weight"] * num_common,  # Combined score
                "permalink_url": node_data.get("permalink_url")
            })
        
        # Sort by score descending
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:limit]
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the graph."""
        if self.graph.number_of_nodes() == 0:
            return {
                "nodes": 0,
                "edges": 0,
                "density": 0.0,
                "avg_degree": 0.0
            }
        
        degrees = [d for n, d in self.graph.degree()]
        
        # Count edges by layer
        layer_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for u, v, data in self.graph.edges(data=True):
            layer = data.get("layer", 1)
            layer_counts[layer] += 1
        
        stats = {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "avg_degree": sum(degrees) / len(degrees) if degrees else 0.0,
            "max_degree": max(degrees) if degrees else 0,
            "min_degree": min(degrees) if degrees else 0,
            "track_nodes": len(self._track_nodes),
            "user_nodes": len(self._user_nodes),
            "artist_nodes": len(self._artist_nodes)
        }
        
        # Calculate connected components (skip for very large graphs)
        num_nodes = self.graph.number_of_nodes()
        if num_nodes < 10000:
            try:
                stats["connected_components"] = nx.number_weakly_connected_components(self.graph)
            except Exception as e:
                logger.warning(f"Could not calculate connected components: {e}")
                stats["connected_components"] = None
        else:
            # Skip for large graphs to avoid performance issues
            stats["connected_components"] = None
        
        # Add layer-specific stats
        if self.enable_multi_layer:
            stats["layer1_edges"] = layer_counts[1]
            stats["layer2_edges"] = layer_counts[2]
            stats["layer3_edges"] = layer_counts[3]
            stats["layer4_edges"] = layer_counts[4]
        
        return stats
    
    def get_track_via_user_path(self, track_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find tracks connected via user engagement (Layer 2).
        
        This finds: track → user (who liked it) → other tracks (they also liked)
        
        Args:
            track_id: Source track ID
            limit: Maximum results
            
        Returns:
            List of track dicts with paths through users
        """
        if track_id not in self.graph:
            return []
        
        results = []
        visited_tracks = {track_id}
        
        # Get users who engaged with this track
        for neighbor_id in self.graph.neighbors(track_id):
            node_data = self.graph.nodes[neighbor_id]
            if node_data.get("node_type") != "user":
                continue
            
            user_id = node_data.get("user_id")
            username = node_data.get("username", f"User {user_id}")
            
            # Get tracks this user engaged with
            for track_neighbor_id in self.graph.neighbors(neighbor_id):
                if track_neighbor_id in visited_tracks:
                    continue
                
                track_node = self.graph.nodes.get(track_neighbor_id, {})
                if track_node.get("node_type") != "track":
                    continue
                
                visited_tracks.add(track_neighbor_id)
                
                results.append({
                    "track_id": track_neighbor_id,
                    "title": track_node.get("title"),
                    "artist_name": track_node.get("artist_name"),
                    "via_user": username,
                    "via_user_id": user_id,
                    "permalink_url": track_node.get("permalink_url")
                })
                
                if len(results) >= limit:
                    return results
        
        return results
    
    def get_similar_users_for_track(self, track_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find users with similar taste based on a track (Layers 2 & 3).
        
        This finds: track → users who liked it → similar users
        
        Args:
            track_id: Source track ID
            limit: Maximum results
            
        Returns:
            List of similar user dicts
        """
        if track_id not in self.graph:
            return []
        
        results = []
        visited_users = set()
        
        # Get users who engaged with this track
        for neighbor_id in self.graph.neighbors(track_id):
            node_data = self.graph.nodes[neighbor_id]
            if node_data.get("node_type") != "user":
                continue
            
            user_id = node_data.get("user_id")
            visited_users.add(user_id)
            
            # Get similar users (Layer 3)
            for similar_user_id in self.graph.neighbors(neighbor_id):
                similar_node = self.graph.nodes.get(similar_user_id, {})
                if similar_node.get("node_type") != "user":
                    continue
                
                similar_uid = similar_node.get("user_id")
                if similar_uid in visited_users:
                    continue
                
                visited_users.add(similar_uid)
                
                # Get edge data for similarity score
                edges = self.graph[neighbor_id][similar_user_id]
                if isinstance(edges, dict):
                    edge_data = list(edges.values())[0] if edges else {}
                else:
                    edge_data = edges
                
                results.append({
                    "user_id": similar_uid,
                    "username": similar_node.get("username"),
                    "similarity_score": edge_data.get("weight", 0.0),
                    "common_tracks": edge_data.get("common_tracks", 0)
                })
                
                if len(results) >= limit:
                    return results[:limit]
        
        return results
    
    def get_artist_collaborations(self, track_id: int) -> List[Dict[str, Any]]:
        """
        Find artist collaborations based on a track (Layer 4).
        
        Args:
            track_id: Source track ID
            
        Returns:
            List of artist collaboration dicts
        """
        track_data = self.cache.get_track(track_id)
        if not track_data:
            return []
        
        artist_id = track_data.get("artist_id")
        if not artist_id:
            return []
        
        artist_node_id = f"artist_{artist_id}"
        if artist_node_id not in self.graph:
            return []
        
        results = []
        for related_artist_id in self.graph.neighbors(artist_node_id):
            artist_node = self.graph.nodes.get(related_artist_id, {})
            if artist_node.get("node_type") != "artist":
                continue
            
            # Get edge data
            edges = self.graph[artist_node_id][related_artist_id]
            if isinstance(edges, dict):
                edge_data = list(edges.values())[0] if edges else {}
            else:
                edge_data = edges
            
            results.append({
                "artist_id": artist_node.get("artist_id"),
                "artist_name": artist_node.get("artist_name"),
                "relationship_type": edge_data.get("relation", "related"),
                "strength": edge_data.get("weight", 0.0),
                "evidence_count": edge_data.get("evidence_count", 0)
            })
        
        return results
    
    def export_to_json(self, output_path: str | Path):
        """
        Export the graph to JSON format (node-link data).
        
        Args:
            output_path: Path to save the JSON file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = nx.node_link_data(self.graph)
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Graph exported to {output_path}")
    
    def load_from_json(self, input_path: str | Path):
        """
        Load a graph from JSON format.
        
        Args:
            input_path: Path to the JSON file
        """
        input_path = Path(input_path)
        
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        self.graph = nx.node_link_graph(data)
        
        # Rebuild node sets
        self._track_nodes = {
            n for n, d in self.graph.nodes(data=True) 
            if d.get("node_type") == "track"
        }
        self._artist_nodes = {
            n for n, d in self.graph.nodes(data=True) 
            if d.get("node_type") == "artist"
        }
        
        logger.info(f"Graph loaded from {input_path}: "
                   f"{self.graph.number_of_nodes()} nodes, "
                   f"{self.graph.number_of_edges()} edges")
    
    def visualize(self, output_path: Optional[str | Path] = None, 
                  highlight_nodes: Optional[Set[int]] = None):
        """
        Create a simple visualization of the graph.
        
        Args:
            output_path: Path to save the visualization (PNG)
            highlight_nodes: Set of node IDs to highlight
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib not installed, cannot visualize")
            return
        
        if self.graph.number_of_nodes() == 0:
            logger.warning("Graph is empty, nothing to visualize")
            return
        
        plt.figure(figsize=(12, 8))
        
        # Layout
        pos = nx.spring_layout(self.graph, k=0.5, iterations=50)
        
        # Draw nodes
        node_colors = []
        for node in self.graph.nodes():
            if highlight_nodes and node in highlight_nodes:
                node_colors.append('#ff4444')  # Red for highlighted
            else:
                node_colors.append('#4444ff')  # Blue for regular
        
        nx.draw_networkx_nodes(
            self.graph, pos, 
            node_color=node_colors,
            node_size=300,
            alpha=0.7
        )
        
        # Draw edges
        nx.draw_networkx_edges(
            self.graph, pos,
            alpha=0.3,
            width=1.0
        )
        
        # Draw labels (limited to avoid clutter)
        if self.graph.number_of_nodes() < 50:
            labels = {
                n: self.graph.nodes[n].get("title", str(n))[:20] 
                for n in self.graph.nodes()
            }
            nx.draw_networkx_labels(
                self.graph, pos,
                labels,
                font_size=8
            )
        
        plt.title("Personal Music Graph")
        plt.axis('off')
        plt.tight_layout()
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            logger.info(f"Visualization saved to {output_path}")
        else:
            plt.show()
        
        plt.close()
