"""
Personal music graph representation using NetworkX.

This module provides a graph-based view of music relationships,
built from cached track data.
"""

from __future__ import annotations
import networkx as nx
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import json
from loguru import logger

from sgr.cache.track_cache import TrackCache


class PersonalGraph:
    """
    NetworkX-based representation of a personal music knowledge graph.
    
    Nodes represent:
    - Tracks (with metadata like title, artist, genre)
    - Artists (optional)
    
    Edges represent:
    - Co-occurrence in playlists
    - Artist relationships
    - Similar tracks
    """
    
    def __init__(self, cache: TrackCache):
        """
        Initialize a personal graph.
        
        Args:
            cache: Track cache instance to load data from
        """
        self.cache = cache
        self.graph = nx.Graph()
        self._track_nodes = set()
        self._artist_nodes = set()
    
    def build_from_seed(self, seed_track_id: int, max_depth: int = 2) -> Dict[str, Any]:
        """
        Build the graph starting from a seed track.
        
        Uses BFS to expand from the seed track through related tracks.
        
        Args:
            seed_track_id: The starting track ID
            max_depth: Maximum depth to expand (number of hops)
            
        Returns:
            Statistics about the built graph
        """
        logger.info(f"Building graph from seed track {seed_track_id}, max_depth={max_depth}")
        
        visited = set()
        queue = [(seed_track_id, 0)]
        
        while queue:
            track_id, depth = queue.pop(0)
            
            if track_id in visited or depth > max_depth:
                continue
            
            visited.add(track_id)
            
            # Add track node
            track_data = self.cache.get_track(track_id)
            if not track_data:
                continue
            
            self._add_track_node(track_id, track_data)
            
            # Get related tracks and add edges
            if depth < max_depth:
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
                        relation=relation_type
                    )
                    
                    # Queue for expansion
                    if rel_track_id not in visited:
                        queue.append((rel_track_id, depth + 1))
        
        stats = {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "track_nodes": len(self._track_nodes),
            "artist_nodes": len(self._artist_nodes),
            "seed_track_id": seed_track_id,
            "max_depth": max_depth
        }
        
        logger.success(f"Graph built: {stats['nodes']} nodes, {stats['edges']} edges")
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
    
    def get_neighbors(self, track_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get neighboring tracks in the graph.
        
        Args:
            track_id: The track ID
            limit: Maximum neighbors to return
            
        Returns:
            List of neighbor track dicts with edge weights
        """
        if track_id not in self.graph:
            return []
        
        neighbors = []
        for neighbor_id in self.graph.neighbors(track_id):
            edge_data = self.graph[track_id][neighbor_id]
            node_data = self.graph.nodes[neighbor_id]
            
            neighbors.append({
                "track_id": neighbor_id,
                "title": node_data.get("title"),
                "artist_name": node_data.get("artist_name"),
                "weight": edge_data.get("weight", 1.0),
                "relation": edge_data.get("relation", "related")
            })
        
        # Sort by weight descending
        neighbors.sort(key=lambda x: x["weight"], reverse=True)
        return neighbors[:limit]
    
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
        
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "avg_degree": sum(degrees) / len(degrees) if degrees else 0.0,
            "max_degree": max(degrees) if degrees else 0,
            "min_degree": min(degrees) if degrees else 0,
            "connected_components": nx.number_connected_components(self.graph),
            "track_nodes": len(self._track_nodes),
            "artist_nodes": len(self._artist_nodes)
        }
    
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
