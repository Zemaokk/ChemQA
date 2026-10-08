"""Versioned scientific lexical analysis and immutable BM25 postings on frozen rows."""

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from src.knowledge_base.similarity import top_indices
from src.utils.artifacts import sha256_file, write_json

ANALYZER_VERSION = "scientific-nfkc-latin-cjk-v1"
# Fixed generic English function words; formula aliases are added before this filter.
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
    ]
)
ELEMENTS = frozenset(
    [
        "H",
        "He",
        "Li",
        "Be",
        "B",
        "C",
        "N",
        "O",
        "F",
        "Ne",
        "Na",
        "Mg",
        "Al",
        "Si",
        "P",
        "S",
        "Cl",
        "Ar",
        "K",
        "Ca",
        "Sc",
        "Ti",
        "V",
        "Cr",
        "Mn",
        "Fe",
        "Co",
        "Ni",
        "Cu",
        "Zn",
        "Ga",
        "Ge",
        "As",
        "Se",
        "Br",
        "Kr",
        "Rb",
        "Sr",
        "Y",
        "Zr",
        "Nb",
        "Mo",
        "Tc",
        "Ru",
        "Rh",
        "Pd",
        "Ag",
        "Cd",
        "In",
        "Sn",
        "Sb",
        "Te",
        "I",
        "Xe",
        "Cs",
        "Ba",
        "La",
        "Ce",
        "Pr",
        "Nd",
        "Pm",
        "Sm",
        "Eu",
        "Gd",
        "Tb",
        "Dy",
        "Ho",
        "Er",
        "Tm",
        "Yb",
        "Lu",
        "Hf",
        "Ta",
        "W",
        "Re",
        "Os",
        "Ir",
        "Pt",
        "Au",
        "Hg",
        "Tl",
        "Pb",
        "Bi",
        "Po",
        "At",
        "Rn",
        "Fr",
        "Ra",
        "Ac",
        "Th",
        "Pa",
        "U",
        "Np",
        "Pu",
        "Am",
        "Cm",
        "Bk",
        "Cf",
        "Es",
        "Fm",
        "Md",
        "No",
        "Lr",
        "Rf",
        "Db",
        "Sg",
        "Bh",
        "Hs",
        "Mt",
        "Ds",
        "Rg",
        "Cn",
        "Nh",
        "Fl",
        "Mc",
        "Lv",
        "Ts",
        "Og",
    ]
)
TOKEN = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-+][A-Za-z0-9]+)*[+-]?|[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[\u0370-\u03ff]+|[\u3400-\u9fff]+"
)
FORMULA = re.compile(r"(?:[A-Z][a-z]?\d*)+[+-]?")
FILES = ("lexical.json", "vocabulary.json", "postings.npz")


def analyzer_fingerprint():
    profile = {
        "version": ANALYZER_VERSION,
        "unicode_version": unicodedata.unidata_version,
        "normalization": "NFKC plus fixed dash mapping; search-copy only",
        "token_pattern": TOKEN.pattern,
        "formula_pattern": FORMULA.pattern,
        "stop_words": sorted(STOP_WORDS),
        "elements": sorted(ELEMENTS),
        "cjk": "unigrams_and_bigrams",
        "formula_alias": "case_sensitive",
    }
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def analyze(text):
    """Normalize a search copy only; preserve formulas as case-sensitive aliases."""
    text = unicodedata.normalize("NFKC", text).translate(
        str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-"})
    )
    tokens = []
    for match in TOKEN.finditer(text):
        word = match.group()
        if "\u3400" <= word[0] <= "\u9fff":
            tokens.extend("c:" + c for c in word)
            tokens.extend("c:" + word[i : i + 2] for i in range(len(word) - 1))
        elif word[0].isdigit() or word[0] in "+-":
            tokens.append("n:" + word.casefold())
        else:
            if FORMULA.fullmatch(word) and all(
                e in ELEMENTS for e in re.findall(r"[A-Z][a-z]?", word)
            ):
                tokens.append("chem:" + word)
            folded = word.casefold()
            if folded not in STOP_WORDS:
                tokens.append("w:" + folded)
            if "-" in folded:
                tokens.extend(
                    "w:" + part
                    for part in folded.split("-")
                    if part and part not in STOP_WORDS
                )
    return tokens


def build_lexical(directory, documents, binding, *, k1=1.2, b=0.75):
    directory = Path(directory)
    if any((directory / f).exists() for f in [*FILES, "run.json"]):
        raise ValueError("Refusing to overwrite lexical candidate")
    if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
        raise ValueError("Invalid BM25 parameters")
    directory.mkdir(parents=True, exist_ok=True)
    inverted = defaultdict(list)
    lengths = []
    for row, document in enumerate(documents):
        counts = Counter(analyze(document["text"]))
        lengths.append(sum(counts.values()))
        for term, frequency in counts.items():
            inverted[term].append((row, frequency))
    if not lengths or not inverted:
        raise ValueError("Cannot build an empty lexical corpus")
    vocabulary = sorted(inverted)
    rows = []
    frequencies = []
    offsets = [0]
    for term in vocabulary:
        for row, frequency in inverted[term]:
            rows.append(row)
            frequencies.append(frequency)
        offsets.append(len(rows))
    np.savez_compressed(
        directory / "postings.npz",
        rows=np.array(rows, dtype=np.int32),
        frequencies=np.array(frequencies, dtype=np.int32),
        offsets=np.array(offsets, dtype=np.int64),
        lengths=np.array(lengths, dtype=np.int32),
    )
    write_json(directory / "vocabulary.json", vocabulary)
    spec = {
        "schema": "chemqa-bm25-v1",
        "analyzer_version": ANALYZER_VERSION,
        "analyzer_sha256": analyzer_fingerprint(),
        "unicode_version": unicodedata.unidata_version,
        "k1": k1,
        "b": b,
        "query_term_frequency": "binary",
        "row_count": len(lengths),
        "vocabulary_size": len(vocabulary),
        "posting_count": len(rows),
        "average_length": float(np.mean(lengths)),
        "binding": binding,
    }
    write_json(directory / "lexical.json", spec)
    return spec


class BM25Index:
    def __init__(self, directory, documents, binding, *, staging=False):
        directory = Path(directory)
        if not staging:
            run = json.loads((directory / "run.json").read_text())
            if (
                run.get("schema") != "chemqa-artifact-run-v1"
                or run.get("kind") != "lexical_indexes"
                or run.get("status") != "ready"
            ):
                raise ValueError("Lexical candidate is not ready")
            for name in FILES:
                if run.get("files", {}).get(name) != sha256_file(directory / name):
                    raise ValueError("Lexical checksum mismatch")
        self.spec = json.loads((directory / "lexical.json").read_text())
        s = self.spec
        if (
            s.get("schema") != "chemqa-bm25-v1"
            or s.get("analyzer_version") != ANALYZER_VERSION
            or s.get("analyzer_sha256") != analyzer_fingerprint()
            or s.get("unicode_version") != unicodedata.unidata_version
            or s.get("binding") != binding
            or s.get("row_count") != len(documents)
            or s.get("query_term_frequency") != "binary"
            or not isinstance(s.get("k1"), (float, int))
            or not math.isfinite(s["k1"])
            or s["k1"] <= 0
            or not isinstance(s.get("b"), (float, int))
            or not math.isfinite(s["b"])
            or not 0 <= s["b"] <= 1
        ):
            raise ValueError("Lexical profile or dense row binding mismatch")
        self.documents = documents
        vocabulary = json.loads((directory / "vocabulary.json").read_text())
        if (
            not isinstance(vocabulary, list)
            or not all(isinstance(t, str) and t for t in vocabulary)
            or vocabulary != sorted(set(vocabulary))
            or len(vocabulary) != s["vocabulary_size"]
        ):
            raise ValueError("Invalid lexical vocabulary")
        self.vocabulary = {term: i for i, term in enumerate(vocabulary)}
        with np.load(directory / "postings.npz", allow_pickle=False) as data:
            self.rows = data["rows"]
            self.frequencies = data["frequencies"]
            self.offsets = data["offsets"]
            self.lengths = data["lengths"]
        if (
            self.rows.dtype != np.int32
            or self.frequencies.dtype != np.int32
            or self.lengths.dtype != np.int32
            or self.offsets.dtype != np.int64
            or self.rows.ndim != 1
            or self.frequencies.shape != self.rows.shape
            or self.lengths.shape != (len(documents),)
            or self.offsets.shape != (len(vocabulary) + 1,)
            or self.offsets[0] != 0
            or self.offsets[-1] != len(self.rows)
            or len(self.rows) != s["posting_count"]
            or np.any(np.diff(self.offsets) <= 0)
            or np.any(self.rows < 0)
            or np.any(self.rows >= len(documents))
            or np.any(self.frequencies <= 0)
            or np.any(self.lengths < 0)
            or float(np.mean(self.lengths)) != s["average_length"]
            or s["average_length"] <= 0
        ):
            raise ValueError("Invalid lexical posting arrays/statistics")
        for start, end in zip(self.offsets[:-1], self.offsets[1:], strict=True):
            if np.any(np.diff(self.rows[start:end]) <= 0):
                raise ValueError("Duplicate or unordered posting rows")
        if not np.array_equal(
            np.bincount(self.rows, weights=self.frequencies, minlength=len(documents)),
            self.lengths,
        ):
            raise ValueError("Posting term frequencies do not match document lengths")
        self.denominator = s["k1"] * (
            1 - s["b"] + s["b"] * self.lengths / s["average_length"]
        )
        self.idf = np.log1p(
            (len(documents) - np.diff(self.offsets) + 0.5)
            / (np.diff(self.offsets) + 0.5)
        )
        for array in [
            self.rows,
            self.frequencies,
            self.offsets,
            self.lengths,
            self.denominator,
            self.idf,
        ]:
            array.flags.writeable = False

    def scores(self, query):
        scores = np.zeros(len(self.documents), dtype=np.float64)
        for term in sorted(set(analyze(query))):
            if term not in self.vocabulary:
                continue
            i = self.vocabulary[term]
            start, end = self.offsets[i : i + 2]
            rows = self.rows[start:end]
            tf = self.frequencies[start:end]
            scores[rows] += (
                self.idf[i] * tf * (self.spec["k1"] + 1) / (tf + self.denominator[rows])
            )
        return scores

    def search(self, query, top_k=10):
        top_indices(np.empty(0), top_k)
        if top_k == 0:
            return []
        scores = self.scores(query)
        positive = np.flatnonzero(scores > 0)
        selected = positive[top_indices(scores[positive], top_k)]
        return [
            {
                "document": self.documents[int(row)],
                "score": float(scores[row]),
                "row_id": int(row),
                "score_kind": "bm25",
            }
            for row in selected
        ]


def dense_binding(storage):
    return {
        "storage_sha256": storage.index_sha256,
        "documents_sha256": storage.spec["documents_sha256"],
        "row_count": storage.spec["row_count"],
        "embedding": storage.spec["embedding"],
    }
