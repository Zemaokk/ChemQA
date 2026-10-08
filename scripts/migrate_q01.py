"""Bind legacy records to current PDFs, back up originals and add stable IDs.

Default is read-only preview. Use --apply to migrate both existing JSON files.
No embedding or API calls; exact duplicate chunks keep their first vector.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from config.settings import BASE_DIR, settings
from src.knowledge_base.identity import document_id_for_source, normalize_chunk


def migrate(processed: list[dict], index: dict) -> tuple[list[dict], dict, dict]:
    documents = index["documents"]
    vectors = index["vectors"]
    if len(processed) != len(documents) or len(documents) != len(vectors):
        raise ValueError("Processed records and vector rows do not align")
    positions = {}
    migrated_chunks = []
    migrated_docs = []
    migrated_vectors = []
    for old_chunk, old_doc, vector in zip(processed, documents, vectors, strict=True):
        chunk, doc = normalize_chunk(old_chunk), normalize_chunk(old_doc)
        if chunk["chunk_id"] != doc["chunk_id"]:
            raise ValueError(
                "Processed record and corresponding vector document differ"
            )
        if doc["doc_id"] != document_id_for_source(doc["source"]):
            raise ValueError(
                "Current PDF bytes differ from the recorded document identity"
            )
        cid = doc["chunk_id"]
        if cid in positions:
            pos = positions[cid]
            if not np.allclose(migrated_vectors[pos], vector, rtol=0, atol=1e-6):
                raise ValueError("Duplicate chunk IDs have inconsistent vectors")
            sources = sorted(set(migrated_docs[pos]["sources"] + doc["sources"]))
            migrated_docs[pos]["sources"] = sources
            migrated_chunks[pos]["metadata"]["sources"] = sources
        else:
            positions[cid] = len(migrated_docs)
            migrated_docs.append(doc)
            migrated_vectors.append(vector)
            migrated_chunks.append(
                {
                    "text": chunk["text"],
                    "metadata": {k: v for k, v in chunk.items() if k != "text"},
                }
            )
    report = {
        "input_rows": len(documents),
        "output_rows": len(migrated_docs),
        "duplicate_rows_removed": len(documents) - len(migrated_docs),
        "unique_documents": len({d["doc_id"] for d in migrated_docs}),
        "vectors_reencoded": False,
    }
    return (
        migrated_chunks,
        {**index, "documents": migrated_docs, "vectors": migrated_vectors},
        report,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    processed_path = Path(settings.PROCESSED_DIR) / "processed_chunks.json"
    index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    originals = {p: p.read_bytes() for p in (processed_path, index_path)}
    chunks, index, report = migrate(
        json.loads(originals[processed_path]), json.loads(originals[index_path])
    )
    print(json.dumps(report, indent=2))
    if not args.apply:
        print("Read-only preview; use --apply after reviewing the report.")
        return
    if chunks == json.loads(originals[processed_path]) and index == json.loads(
        originals[index_path]
    ):
        print("Already migrated; no files changed.")
        return
    backup_dir = Path(BASE_DIR) / "output" / "q01_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path, content in originals.items():
        digest = hashlib.sha256(content).hexdigest()
        backup_path = backup_dir / f"{path.stem}.{digest}.json"
        if backup_path.exists() and backup_path.read_bytes() != content:
            raise ValueError("Backup content mismatch")
        backup_path.write_bytes(content)
    # Back up both originals before replacing either file. The IDs are deterministic.
    for path, data in ((processed_path, chunks), (index_path, index)):
        temporary = path.with_suffix(".q01.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    print(f"Migration applied. Original files backed up in {backup_dir}")


if __name__ == "__main__":
    main()
