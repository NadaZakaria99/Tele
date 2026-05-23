"""
Tests for extraction_service/coords.py

Tests bbox coordinate correction logic in isolation — no GPU / model required.
Imports from coords.py directly (zero heavy dependencies: no torch, no transformers).
"""

import pytest
from extraction_service.coords import correct_bbox, resize_for_inference
from PIL import Image


class TestCorrectBbox:
    """
    The core correctness guarantee: Chandra OCR-2 returns bboxes in 0–1000
    integer space. We must convert to original pixel coords by:
        pixel = (val / 1000) * original_dimension

    The historical bug (fix_json_coords.py) was treating them as pixel coords
    and applying an additional 1/scale factor — this test suite prevents regression.
    """

    def test_integer_space_conversion(self):
        """0–1000 int bbox → correct pixel coords for a 4000×3000 image."""
        # bbox covers the right half horizontally, middle third vertically
        raw = [500, 333, 1000, 666]
        orig_w, orig_h = 4000, 3000
        inf_w, inf_h = 2000, 1500
        scale = 0.5

        bbox = correct_bbox(raw, orig_w, orig_h, inf_w, inf_h, scale)

        assert bbox is not None
        assert bbox.x1 == 2000   # 500/1000 * 4000
        assert bbox.y1 == 999    # 333/1000 * 3000
        assert bbox.x2 == 4000   # 1000/1000 * 4000
        assert bbox.y2 == 1998   # 666/1000 * 3000

    def test_old_bug_not_reproduced(self):
        """
        Old buggy code would do: pixel = raw / scale
        e.g. for raw=500, scale=0.5 → 500/0.5 = 1000 (wrong!)
        Correct: 500/1000 * 4000 = 2000
        """
        raw = [500, 333, 1000, 666]
        orig_w, orig_h = 4000, 3000
        inf_w, inf_h = 2000, 1500
        scale = 0.5

        bbox = correct_bbox(raw, orig_w, orig_h, inf_w, inf_h, scale)
        # Old bug would give x2 = 1000/0.5 = 2000 (half of correct)
        assert bbox.x2 == 4000  # must be the full width, not 2000

    def test_normalized_float_bbox(self):
        """Handle normalized [0.0–1.0] float coords (alternative model output format)."""
        raw = [0.0, 0.0, 0.5, 0.5]
        orig_w, orig_h = 4000, 3000
        inf_w, inf_h = 2000, 1500
        scale = 0.5

        bbox = correct_bbox(raw, orig_w, orig_h, inf_w, inf_h, scale)

        assert bbox is not None
        # 0.5 * inf_w=2000 = 1000 → scale back: 1000 / 0.5 = 2000
        assert bbox.x2 == 2000
        assert bbox.y2 == 1500

    def test_degenerate_bbox_returns_none(self):
        """Invalid bbox (x2 <= x1) should return None cleanly."""
        raw = [500, 100, 300, 900]  # x2 < x1
        assert correct_bbox(raw, 4000, 3000, 2000, 1500, 0.5) is None

    def test_none_bbox_returns_none(self):
        assert correct_bbox(None, 4000, 3000, 2000, 1500, 0.5) is None

    def test_wrong_length_returns_none(self):
        assert correct_bbox([100, 200], 4000, 3000, 2000, 1500, 0.5) is None


class TestResizeForInference:
    def test_no_resize_needed(self):
        """Image smaller than max_dim should not be resized."""
        img = Image.new("RGB", (800, 600))
        resized, scale = resize_for_inference(img, max_dim=2000)
        assert resized.size == (800, 600)
        assert scale == 1.0

    def test_landscape_resize(self):
        """Width is the longest side — should be scaled to max_dim."""
        img = Image.new("RGB", (4000, 2000))
        resized, scale = resize_for_inference(img, max_dim=2000)
        assert resized.size[0] == 2000
        assert resized.size[1] == 1000
        assert abs(scale - 0.5) < 0.01

    def test_portrait_resize(self):
        """Height is the longest side — should be scaled to max_dim."""
        img = Image.new("RGB", (2000, 6000))
        resized, scale = resize_for_inference(img, max_dim=2000)
        assert resized.size[1] == 2000
        assert resized.size[0] == 666
        assert abs(scale - 1 / 3) < 0.01
