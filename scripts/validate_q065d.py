"""Local page-level parser pilot; no API calls, index writes or corpus migration."""

import argparse
import importlib.metadata
import json
import time
import unicodedata
from pathlib import Path

import pymupdf

from config.settings import BASE_DIR
from src.utils.artifacts import ArtifactRun, sha256_file, write_json, write_text

ROOT = Path(BASE_DIR)
BASELINES = ("data/vector_db/vector_index.json", "data/processed/processed_chunks.json")


def unique_alignment(raw, quote):
    """Accept only one exact raw-text occurrence; normalization is diagnostic only."""
    if not quote:
        return {"status": "empty"}
    first = raw.find(quote)
    if first >= 0:
        if raw.find(quote, first + 1) >= 0:
            return {"status": "ambiguous"}
        return {
            "status": "exact_unique",
            "char_start": first,
            "char_end": first + len(quote),
        }
    normalize = lambda s: "".join(unicodedata.normalize("NFKC", s).split())
    normalized, needle = normalize(raw), normalize(quote)
    if needle and needle in normalized:
        return {"status": "normalized_only_no_source_offsets"}
    return {"status": "unmatched"}


def valid_bbox(bbox, width, height):
    values = [bbox.get(k) for k in ("l", "t", "r", "b")]
    if any(not isinstance(v, (int, float)) for v in values):
        return False
    left, top, right, bottom = values
    return (
        bbox.get("coord_origin") in {"TOPLEFT", "BOTTOMLEFT"}
        and 0 <= left <= right <= width
        and 0 <= min(top, bottom) <= max(top, bottom) <= height
        and (top <= bottom if bbox["coord_origin"] == "TOPLEFT" else bottom <= top)
    )


def baseline_hashes():
    return {p: sha256_file(ROOT / p) for p in BASELINES}


def model_files():
    specs = json.loads((ROOT / "config/q065d_models.json").read_text())
    return {
        str(p.relative_to(ROOT)): sha256_file(p)
        for spec in specs
        for p in sorted(
            (ROOT / "models/docling" / spec["repo_id"].replace("/", "--")).rglob("*")
        )
        if p.is_file() and ".cache" not in p.parts
    }


def download():
    from huggingface_hub import snapshot_download

    specs = json.loads((ROOT / "config/q065d_models.json").read_text())
    for spec in specs:
        snapshot_download(
            spec["repo_id"],
            revision=spec["revision"],
            local_dir=ROOT / "models/docling" / spec["repo_id"].replace("/", "--"),
            allow_patterns=spec["allow_patterns"],
        )


def converter(ocr=False):
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMacOptions, PdfPipelineOptions
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    options = PdfPipelineOptions(
        artifacts_path=ROOT / "models/docling",
        do_ocr=ocr,
        do_table_structure=True,
        enable_remote_services=False,
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.CPU, num_threads=1
        ),
    )
    if ocr:
        options.ocr_options = OcrMacOptions(force_full_page_ocr=True, lang=["en-US"])
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        }
    )


def compare_page(case, directory, parser, *, image_control=False):
    source = ROOT / case["source"]
    if "doc_" + sha256_file(source) != case["doc_id"]:
        raise ValueError("Source bytes differ from the frozen sample")
    page_number = case["page_number"]
    directory.mkdir()
    with pymupdf.open(source) as pdf:
        page = pdf[page_number - 1]
        start = time.perf_counter()
        raw = page.get_text("text", sort=False)
        native_seconds = time.perf_counter() - start
        width, height = page.rect.width, page.rect.height
        # Image rendering only: the source PDF is never rewritten.
        image_path = directory / "original-page.png"
        page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(image_path)
    write_text(directory / "pymupdf.txt", raw)
    result = {
        "sample_id": case["sample_id"],
        "source": case["source"],
        "doc_id": case["doc_id"],
        "page_number": page_number,
        "pymupdf_characters": len(raw),
        "pymupdf_seconds": native_seconds,
        "mode": "synthetic_image_control" if image_control else "native_pdf",
        "source_offsets_are_page_local": True,
    }
    start = time.perf_counter()
    try:
        # A PNG follows Docling's image backend; its page 1 maps explicitly back
        # to this frozen source page, never to physical PDF page 1 by inference.
        conversion = parser.convert(
            image_path if image_control else source,
            page_range=(1, 1) if image_control else (page_number, page_number),
        )
        document = conversion.document
        payload = document.export_to_dict()
        markdown = document.export_to_markdown()
        write_json(directory / "docling.json", payload)
        write_text(directory / "docling.md", markdown)
        items = []
        for item, _level in document.iterate_items():
            data = item.model_dump(mode="json")
            if not data.get("prov"):
                continue
            expected = 1 if image_control else page_number
            size = document.pages[expected].size
            location_ok = all(
                prov["page_no"] == expected
                and valid_bbox(prov["bbox"], size.width, size.height)
                for prov in data["prov"]
            )
            entry = {
                "ref": data["self_ref"],
                "label": data["label"],
                "source_page_number": page_number,
                "docling_provenance": data["prov"],
                "docling_page_size": {"width": size.width, "height": size.height},
                "source_page_size": {"width": width, "height": height},
                "page_and_bbox_valid": location_ok,
                "docling_charspan_is_not_raw_pdf_offset": True,
            }
            if "text" in data:
                entry.update(
                    text=data["text"],
                    raw_alignment=unique_alignment(raw, data["text"]),
                )
            if "data" in data and "table_cells" in data["data"]:
                entry["table_cells"] = [
                    {
                        "text": cell["text"],
                        "row": cell["start_row_offset_idx"],
                        "column": cell["start_col_offset_idx"],
                        "raw_alignment": unique_alignment(raw, cell["text"]),
                    }
                    for cell in data["data"]["table_cells"]
                ]
            items.append(entry)
        write_json(directory / "alignment.json", {"items": items})
        text_items = [i for i in items if "raw_alignment" in i]
        result.update(
            conversion_status=conversion.status.value,
            docling_characters=len(markdown),
            docling_seconds=time.perf_counter() - start,
            item_count=len(items),
            table_count=sum(i["label"] == "table" for i in items),
            text_items=len(text_items),
            exact_unique_text_items=sum(
                i["raw_alignment"]["status"] == "exact_unique" for i in text_items
            ),
            invalid_page_or_bbox=sum(not i["page_and_bbox_valid"] for i in items),
            errors=[str(e) for e in conversion.errors],
            content_audit_issues=(
                ["no_text_or_table_cell_text"]
                if not text_items
                and not any(
                    c["text"].strip() for i in items for c in i.get("table_cells", [])
                )
                else []
            ),
        )
    except Exception as exc:  # noqa: BLE001 - persist each isolated candidate failure
        result.update(
            conversion_status="exception",
            error_type=type(exc).__name__,
            error=str(exc),
            docling_seconds=time.perf_counter() - start,
        )
    write_json(directory / "result.json", result)
    return result


def run():
    before = baseline_hashes()
    protocol = json.loads((ROOT / "docs/Q06_5D_SAMPLE.json").read_text())
    native = converter()
    records = []
    with ArtifactRun("q065d_parsing") as artifact:
        write_json(artifact.path / "protocol.json", protocol)
        for case in protocol["samples"]:
            print(case["sample_id"], flush=True)
            records.append(
                compare_page(case, artifact.path / case["sample_id"], native)
            )
        control = {**protocol["samples"][0], "sample_id": "synthetic-scan-control"}
        print(control["sample_id"], flush=True)
        records.append(
            compare_page(
                control,
                artifact.path / control["sample_id"],
                converter(ocr=True),
                image_control=True,
            )
        )
        after = baseline_hashes()
        if after != before:
            raise ValueError("Existing index or processed corpus changed during pilot")
        report = {
            "schema": "chemqa-q065d-parsing-v1",
            "records": records,
            "protocol_sha256": sha256_file(ROOT / "docs/Q06_5D_SAMPLE.json"),
            "versions": {
                p: importlib.metadata.version(p)
                for p in (
                    "docling",
                    "docling-core",
                    "docling-parse",
                    "docling-ibm-models",
                    "pymupdf",
                    "torch",
                    "ocrmac",
                )
            },
            "candidate_requirements_sha256": sha256_file(
                ROOT / "config/q065d_requirements.txt"
            ),
            "model_revisions": json.loads(
                (ROOT / "config/q065d_models.json").read_text()
            ),
            "model_files_sha256": model_files(),
            "device": "cpu",
            "num_threads": 1,
            "remote_services": False,
            "generation_requests": 0,
            "baseline_before": before,
            "baseline_after": after,
            "review_status": "assistant_visual_review_pending_researcher_review",
        }
        write_json(artifact.path / "report.json", report)
        target = artifact.publish(
            "recorded", {"native_pages": 10, "synthetic_controls": 1}
        )
    write_json(
        ROOT / "docs/Q06_5D_RUNTIME.json", {**report, "artifact_directory": str(target)}
    )
    print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fetch only fixed public parsing weights; no literature upload",
    )
    args = parser.parse_args()
    download() if args.download else run()


if __name__ == "__main__":
    main()
