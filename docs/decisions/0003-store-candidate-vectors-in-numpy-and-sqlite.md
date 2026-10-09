# 0003. Store candidate vectors in NumPy and SQLite

Date: 2026-10-09  
Status: Accepted (retrospective record of an existing decision)

## Context

The experimental Qwen JSON index was large. A FAISS trial could run independently but conflicted with the locked PyTorch/OpenMP combination during actual computation on the tested macOS ARM64 environment.

## Decision

Store candidate float32 vectors in NumPy `.npy` with read-only memory mapping and complete row metadata in SQLite. Keep exact cosine ranking and validate vectors, row mappings, metadata, and source hashes. Preserve the JSON compatibility path.

## Alternatives

FAISS was not adopted after reproducible process termination; an unsafe duplicate-OpenMP override was not used. Continuing only with JSON was compatible but retained loading/storage overhead. Approximation and quantization were outside the fixed-vector migration scope.

## Consequences

The migration preserved 6,960 rows and development rankings while reducing measured storage from 221.6 to 61.3 MiB. Validation touches all vectors and cached scoring still uses memory. The single-machine benchmark does not establish end-to-end speed or a general FAISS incompatibility.

Evidence: [Storage contracts](../reference/artifact-contracts.md), [full validation](../Q06_5F_FULL.json), [benchmark](../Q06_5F_BENCHMARK.json), and [FAISS trial](../Q06_5F_FAISS_TRIAL.json).

[Decision index](README.md)
