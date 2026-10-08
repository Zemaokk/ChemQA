"""Shared cosine scoring for retrieval and visualization; stored vectors stay intact."""

import numpy as np


def cosine_scores(vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Score rows against a query, rejecting undefined or inconsistent inputs."""
    matrix = np.asarray(vectors, dtype=np.float64)
    query = np.asarray(query, dtype=np.float64)
    if (
        matrix.ndim != 2
        or query.ndim != 1
        or matrix.shape[1] != query.size
        or not query.size
    ):
        raise ValueError("Cosine scoring requires a matrix and a matching query vector")
    if not np.isfinite(matrix).all() or not np.isfinite(query).all():
        raise ValueError("Cosine scoring requires finite embedding values")
    # Scale before normalization to avoid overflow/underflow for finite vectors.
    query_scale = np.max(np.abs(query))
    if query_scale == 0:
        raise ValueError("Cosine similarity is undefined for a zero query vector")
    if not len(matrix):
        return np.empty(0, dtype=np.float64)
    scales = np.max(np.abs(matrix), axis=1)
    if np.any(scales == 0):
        raise ValueError("Cosine similarity is undefined for a zero document vector")
    scaled = matrix / scales[:, None]
    scaled_query = query / query_scale
    scores = (
        (scaled @ scaled_query)
        / np.linalg.norm(scaled, axis=1)
        / np.linalg.norm(scaled_query)
    )
    return np.clip(scores, -1.0, 1.0)


def top_indices(scores: np.ndarray, limit: int) -> np.ndarray:
    """Descending score order; ties retain index order for reproducibility."""
    if isinstance(limit, bool) or not isinstance(limit, (int, np.integer)) or limit < 0:
        raise ValueError("Result count must be a nonnegative integer")
    return np.argsort(-scores, kind="stable")[:limit]
