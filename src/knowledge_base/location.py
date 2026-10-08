"""Map cleaned text back to page-local extracted-text offsets."""

import re

LOCATION_VERSION = "pymupdf-text-offset-v1"


def clean_with_offsets(
    text: str, *, preserve_symbols: bool = False
) -> tuple[str, list[tuple[int, int]]]:
    """Retain raw intervals; preserve_symbols selects whitespace-only Q03 cleaning."""
    characters = []
    offsets = []
    for match in re.finditer(r"\s+|\S", text):
        char = " " if match.group().isspace() else match.group()
        if preserve_symbols or re.fullmatch(r"[\w\s,.?;:!-]", char):
            characters.append(char)
            offsets.append((match.start(), match.end()))
    # Same strip operation as clean_text(); retained characters have identical positions.
    first, last = 0, len(characters)
    while first < last and characters[first].isspace():
        first += 1
    while last > first and characters[last - 1].isspace():
        last -= 1
    return "".join(characters[first:last]), offsets[first:last]


def locate_chunks(document: dict, chunk_size: int, overlap: int) -> list[dict]:
    """Return exact page excerpts for the unchanged word-based chunking algorithm."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk size must be positive and overlap smaller than size")
    raw = document["text"]
    pages = document.get("pages")
    if pages is None:
        return []
    cursor = 0
    for i, page in enumerate(pages, 1):
        if (
            page["page_number"] != i
            or page["char_start"] != cursor
            or page["char_end"] != cursor + len(page["text"])
        ):
            raise ValueError("Invalid PDF page text boundaries")
        cursor = page["char_end"]
    if cursor != len(raw) or "".join(p["text"] for p in pages) != raw:
        raise ValueError("Page text does not match document text")
    cleaned, offsets = clean_with_offsets(raw)
    words = list(re.finditer(r"\S+", cleaned))
    located = []
    for index, start in enumerate(range(0, len(words), chunk_size - overlap)):
        selected = words[start : start + chunk_size]
        raw_start = offsets[selected[0].start()][0]
        raw_end = offsets[selected[-1].end() - 1][1]
        # Preserve removed chemical symbols at the edges of the original raw tokens.
        while raw_start > 0 and not raw[raw_start - 1].isspace():
            raw_start -= 1
        while raw_end < len(raw) and not raw[raw_end].isspace():
            raw_end += 1
        spans = []
        for page in pages:
            first, last = (
                max(raw_start, page["char_start"]),
                min(raw_end, page["char_end"]),
            )
            if first < last:
                start_in_page, end_in_page = (
                    first - page["char_start"],
                    last - page["char_start"],
                )
                spans.append(
                    {
                        "page_number": page["page_number"],
                        "char_start": start_in_page,
                        "char_end": end_in_page,
                        "raw_text": page["text"][start_in_page:end_in_page],
                    }
                )
        located.append(
            {
                "text": " ".join(word.group() for word in selected),
                "chunk_index": index,
                "location_version": LOCATION_VERSION,
                "location_status": "located",
                "location_extractor": document.get(
                    "extraction", {"library": "supplied_page_text"}
                ),
                "page_numbers": [span["page_number"] for span in spans],
                "source_spans": spans,
            }
        )
    return located


def validate_location(record: dict) -> None:
    """Reject structurally inconsistent location metadata without reopening a PDF."""
    status = record.get("location_status")
    if status is None:
        return  # Legacy/synthetic records may not carry location metadata yet.
    if record.get("location_version") != LOCATION_VERSION:
        raise ValueError("Unsupported location metadata version")
    spans = record.get("source_spans", [])
    pages = record.get("page_numbers", [])
    if status == "unavailable":
        if spans or pages or not record.get("location_reason"):
            raise ValueError(
                "Unavailable locations require a reason and no guessed spans"
            )
        return
    if status != "located" or not spans or pages != [s["page_number"] for s in spans]:
        raise ValueError("Invalid location metadata")
    if pages != sorted(set(pages)):
        raise ValueError("Page numbers must be unique and ordered")
    for span in spans:
        page, start, end, text = (
            span["page_number"],
            span["char_start"],
            span["char_end"],
            span["raw_text"],
        )
        if (
            type(page) is not int
            or page < 1
            or type(start) is not int
            or type(end) is not int
            or start < 0
            or end <= start
            or not isinstance(text, str)
            or len(text) != end - start
        ):
            raise ValueError("Invalid page-local text interval")
        if record.get("total_pages") is not None and page > record["total_pages"]:
            raise ValueError("Location page exceeds PDF page count")


def unavailable_location(reason: str) -> dict:
    return {
        "location_version": LOCATION_VERSION,
        "location_status": "unavailable",
        "location_reason": reason,
        "page_numbers": [],
        "source_spans": [],
    }


def locate_intervals(
    document: dict, intervals: list[tuple[int, int]], offsets: list[tuple[int, int]]
) -> list[dict]:
    """Locate exact character slices from the symbol-preserving cleaned text."""
    pages = document.get("pages")
    if pages is None:
        return [unavailable_location("page_text_not_supplied") for _ in intervals]
    cursor = 0
    for i, page in enumerate(pages, 1):
        if (
            page["page_number"] != i
            or page["char_start"] != cursor
            or page["char_end"] != cursor + len(page["text"])
        ):
            raise ValueError("Invalid PDF page text boundaries")
        cursor = page["char_end"]
    if (
        cursor != len(document["text"])
        or "".join(p["text"] for p in pages) != document["text"]
    ):
        raise ValueError("Page text does not match document text")
    locations = []
    for start, end in intervals:
        raw_start, raw_end = offsets[start][0], offsets[end - 1][1]
        spans = []
        for page in pages:
            first = max(raw_start, page["char_start"]) - page["char_start"]
            last = min(raw_end, page["char_end"]) - page["char_start"]
            if first < last:
                spans.append(
                    {
                        "page_number": page["page_number"],
                        "char_start": first,
                        "char_end": last,
                        "raw_text": page["text"][first:last],
                    }
                )
        locations.append(
            {
                "location_version": LOCATION_VERSION,
                "location_status": "located",
                "location_extractor": document.get(
                    "extraction", {"library": "supplied_page_text"}
                ),
                "page_numbers": [s["page_number"] for s in spans],
                "source_spans": spans,
            }
        )
    return locations
