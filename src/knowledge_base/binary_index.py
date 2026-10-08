"""Immutable exact dense retrieval with NumPy binary vectors and SQLite row metadata."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from src.knowledge_base.embedding import validate_profile
from src.knowledge_base.identity import normalize_chunk
from src.knowledge_base.similarity import top_indices
from src.utils.artifacts import sha256_file, write_json

FILES = ("storage.json", "vectors.npy", "metadata.sqlite3")
SCHEMA = "chemqa-numpy-sqlite-v1"


def payload(document):
    return json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def documents_digest(documents):
    digest = hashlib.sha256()
    for row, document in enumerate(documents):
        encoded = payload(document).encode("utf-8")
        digest.update(row.to_bytes(8, "little"))
        digest.update(len(encoded).to_bytes(8, "little"))
        digest.update(encoded)
    return digest.hexdigest()


def vectors_digest(vectors):
    return hashlib.sha256(
        np.asarray(vectors, dtype="<f4").tobytes(order="C")
    ).hexdigest()


def validate_vectors(vectors, rows, dimension):
    if (
        vectors.dtype != np.float32
        or vectors.shape != (rows, dimension)
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4, rtol=0)
    ):
        raise ValueError("Expected finite unit float32 vectors aligned with metadata")


def write_binary_index(directory, index, *, source):
    """Write an unpublished candidate; never re-encode or normalize source vectors."""

    directory = Path(directory)
    if (directory / "run.json").exists() or any(
        (directory / f).exists() for f in FILES
    ):
        raise ValueError("Refusing to overwrite a published or populated binary index")
    directory.mkdir(parents=True, exist_ok=True)
    embedding = index["embedding"]
    validate_profile(embedding)
    if embedding.get("token_count_includes_prompt_and_special_tokens") is not True:
        raise ValueError("Source embedding manifest lacks full input budget contract")
    documents = index["documents"]
    if not documents:
        raise ValueError("Refusing an empty migration")
    if any(normalize_chunk(d) != d for d in documents):
        raise ValueError(
            "Source documents must already have canonical chunk identities"
        )
    vectors = np.ascontiguousarray(index["vectors"], dtype=np.float32)
    if not np.array_equal(np.asarray(index["vectors"]), vectors):
        raise ValueError(
            "Migration would change source values when converting to float32"
        )
    validate_vectors(vectors, len(documents), embedding["dimension"])
    with sqlite3.connect(directory / "metadata.sqlite3") as connection:
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "CREATE TABLE chunks (row_id INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE, doc_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO chunks VALUES (?, ?, ?, ?)",
            (
                (i, d["chunk_id"], d["doc_id"], payload(d))
                for i, d in enumerate(documents)
            ),
        )
        connection.execute("CREATE INDEX chunks_doc_id ON chunks(doc_id)")
    np.save(directory / "vectors.npy", vectors, allow_pickle=False)
    spec = {
        "schema": SCHEMA,
        "backend": "numpy-float32-sqlite",
        "metric": "cosine",
        "dtype": "float32",
        "row_count": len(documents),
        "dimension": embedding["dimension"],
        "tie_break": "score_desc_row_id_asc",
        "embedding": embedding,
        "chunking": index["chunking"],
        "corpus_sha256": index["corpus_sha256"],
        "text_processing_versions": sorted(
            {d["text_processing_version"] for d in documents}
        ),
        "location_versions": sorted({d["location_version"] for d in documents}),
        "location_extractors": sorted(
            {payload(d["location_extractor"]) for d in documents}
        ),
        "documents_sha256": documents_digest(documents),
        "float32_vectors_sha256": vectors_digest(vectors),
        "source": source,
    }
    write_json(directory / "storage.json", spec)
    return spec


class SQLiteDocuments(Sequence):
    def __init__(self, connection, count):
        self.connection, self.count = connection, count

    def __len__(self):
        return self.count

    def __getitem__(self, row):
        if isinstance(row, slice):
            return [self[i] for i in range(*row.indices(self.count))]
        row = int(row)
        if row < 0:
            row += self.count
        if not 0 <= row < self.count:
            raise IndexError(row)
        record = self.connection.execute(
            "SELECT payload FROM chunks WHERE row_id=?", (row,)
        ).fetchone()
        if record is None:
            raise ValueError("Missing metadata row")
        return json.loads(record[0])

    def __iter__(self):
        for (text,) in self.connection.execute(
            "SELECT payload FROM chunks ORDER BY row_id"
        ):
            yield json.loads(text)


class BinaryIndex:
    def __init__(self, directory, *, expected_embedding, staging=False):

        self.directory = Path(directory)
        if not staging:
            run = json.loads((self.directory / "run.json").read_text())
            if (
                run.get("schema") != "chemqa-artifact-run-v1"
                or run.get("kind") != "indexes"
                or run.get("status") != "ready"
                or run.get("storage_backend") != "numpy-float32-sqlite"
            ):
                raise ValueError(
                    "Binary candidate is not ready or has an incompatible manifest"
                )
            for name in FILES:
                if run.get("files", {}).get(name) != sha256_file(self.directory / name):
                    raise ValueError("Binary candidate file checksum mismatch")
        self.spec = json.loads((self.directory / "storage.json").read_text())
        spec = self.spec
        validate_profile(spec["embedding"])
        if (
            spec.get("schema") != SCHEMA
            or spec.get("backend") != "numpy-float32-sqlite"
            or spec.get("metric") != "cosine"
            or spec.get("dtype") != "float32"
            or spec.get("tie_break") != "score_desc_row_id_asc"
            or spec["embedding"] != expected_embedding
            or spec["dimension"] != expected_embedding["dimension"]
        ):
            raise ValueError("Binary index configuration/profile mismatch")
        self.vectors = np.load(
            self.directory / "vectors.npy", mmap_mode="r", allow_pickle=False
        )
        validate_vectors(self.vectors, spec["row_count"], spec["dimension"])
        if vectors_digest(self.vectors) != spec["float32_vectors_sha256"]:
            raise ValueError("Binary vector content mismatch")
        self.vectors.flags.writeable = False
        # Cache the existing float64 cosine reference's document-only work.
        # This preserves its operations/order while avoiding JSON and per-query scaling.
        matrix = np.asarray(self.vectors, dtype=np.float64)
        self._scaled = matrix / np.max(np.abs(matrix), axis=1)[:, None]
        self._norms = np.linalg.norm(self._scaled, axis=1)
        self._scaled.flags.writeable = False
        self._norms.flags.writeable = False
        uri = (
            self.directory / "metadata.sqlite3"
        ).resolve().as_uri() + "?mode=ro&immutable=1"
        self.connection = sqlite3.connect(uri, uri=True)
        try:
            if (
                self.connection.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                or self.connection.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise ValueError("SQLite integrity/schema mismatch")
            rows = self.connection.execute(
                "SELECT row_id,chunk_id,doc_id,payload FROM chunks ORDER BY row_id"
            )
            count = 0
            for row, chunk_id, doc_id, text in rows:
                doc = json.loads(text)
                if (
                    row != count
                    or chunk_id != doc["chunk_id"]
                    or doc_id != doc["doc_id"]
                    or normalize_chunk(doc) != doc
                ):
                    raise ValueError("SQLite row/identity mapping mismatch")
                count += 1
            if count != spec["row_count"]:
                raise ValueError("SQLite row count mismatch")
            self.documents = SQLiteDocuments(self.connection, count)
            if documents_digest(self.documents) != spec["documents_sha256"]:
                raise ValueError("SQLite metadata content mismatch")
        except BaseException:
            self.connection.close()
            raise
        self.index_sha256 = sha256_file(self.directory / "storage.json")

    def search(self, query, top_k=10):
        top_indices(np.empty(0), top_k)
        if top_k == 0:
            return []
        query = np.asarray(query, dtype=np.float64)
        if (
            query.shape != (self.spec["dimension"],)
            or not np.isfinite(query).all()
            or not np.any(query)
        ):
            raise ValueError("Expected a finite nonzero matching query vector")
        scaled_query = query / np.max(np.abs(query))
        scores = np.clip(
            (self._scaled @ scaled_query) / self._norms / np.linalg.norm(scaled_query),
            -1.0,
            1.0,
        )
        return [
            {"document": self.documents[int(i)], "score": float(scores[i])}
            for i in top_indices(scores, top_k)
        ]

    def close(self):
        self.connection.close()
