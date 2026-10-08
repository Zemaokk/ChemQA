"""Source offsets must remain exact and unambiguous across parser experiments."""

import unittest

from scripts.validate_q065d import unique_alignment, valid_bbox


class ParserProvenanceTests(unittest.TestCase):
    def test_exact_unique_offsets_reproduce_source(self):
        raw = "条件：β-Ni(OH)₂\n1.484 V vs RHE"
        quote = "1.484 V vs RHE"
        match = unique_alignment(raw, quote)
        self.assertEqual(match["status"], "exact_unique")
        self.assertEqual(raw[match["char_start"] : match["char_end"]], quote)

    def test_repeated_table_values_do_not_get_arbitrary_offsets(self):
        self.assertEqual(unique_alignment("93 93", "93"), {"status": "ambiguous"})
        self.assertEqual(unique_alignment("aaa", "aa"), {"status": "ambiguous"})

    def test_normalized_formula_or_line_wrap_does_not_become_raw_span(self):
        result = unique_alignment("Ni(OH)₂\n1.484 V", "Ni(OH)2 1.484 V")
        self.assertEqual(result, {"status": "normalized_only_no_source_offsets"})

    def test_missing_and_empty_quotes_remain_unmapped(self):
        self.assertEqual(unique_alignment("93%", "97%"), {"status": "unmatched"})
        self.assertEqual(unique_alignment("93%", ""), {"status": "empty"})

    def test_bbox_bounds_respect_coordinate_origin(self):
        box = {"l": 2, "r": 50, "t": 90, "b": 10, "coord_origin": "BOTTOMLEFT"}
        self.assertTrue(valid_bbox(box, 100, 100))
        self.assertTrue(
            valid_bbox({**box, "t": 10, "b": 90, "coord_origin": "TOPLEFT"}, 100, 100)
        )
        for change in [
            {"r": 101},
            {"l": -1},
            {"r": 1},
            {"t": float("nan")},
            {"t": None},
            {"coord_origin": "unknown"},
        ]:
            self.assertFalse(valid_bbox({**box, **change}, 100, 100))


if __name__ == "__main__":
    unittest.main()
