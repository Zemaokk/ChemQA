"""
Organic Electrocatalysis Query-Chunk Similarity Heatmap Generator

This script generates a focused heatmap showing the similarity between 5 key organic electrocatalysis queries
and the top 15 most relevant text chunks from the entire knowledge base.
"""

import argparse
import os
import sys

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import configure_paths
from src.utils.artifacts import ArtifactRun
from src.visualization.heatmap import HeatmapVisualizer


def main():
    """Generate the focused heatmap"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", help="Candidate index directory")
    parser.add_argument("--output-dir", help="Root for generated runs")
    args = parser.parse_args()
    configure_paths(index_dir=args.index_dir, output_dir=args.output_dir)
    print("🧪 Generating Organic Electrocatalysis Query-Chunk Similarity Heatmap")
    print("=" * 70)

    # Initialize visualizer
    visualizer = HeatmapVisualizer()

    # Create focused heatmap
    with ArtifactRun("heatmaps") as run:
        visualizer.create_similarity_heatmap(
            max_docs=15,  # Number of top chunks to display
            figsize=(12, 8),  # Image size
            cmap="viridis",  # Color mapping (optimized for 0.4-0.8 range)
            vmin=0.4,  # Minimum similarity threshold
            vmax=0.8,  # Maximum similarity threshold
            save_path=str(run.path / "similarity_heatmap.png"),
        )
        if not (run.path / "similarity_heatmap.png").is_file():
            raise ValueError("Heatmap was not generated; run was not published")
        output_dir = run.publish("complete")

    print("✅ Heatmap generation completed!")
    print(f"📁 Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
