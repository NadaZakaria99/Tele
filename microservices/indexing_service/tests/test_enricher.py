"""
Tests for indexing_service/enricher.py

Tests header propagation, noise filtration, and Document output — no network.
"""

import pytest
from langchain_core.documents import Document

from nbe_schemas.documents import Block, BlockType, BBox, PageResult
from indexing_service.enricher import enrich_pages


def _make_page(doc_id: str, page_num: int, blocks: list[Block]) -> PageResult:
    return PageResult(
        doc_id=doc_id,
        doc_name=f"{doc_id}.pdf",
        doc_type="SOP",
        page_num=page_num,
        original_size=(3000, 2000),
        inference_size=(2000, 1333),
        page_image_path=f"docs_images/{doc_id}/page_{page_num:03d}.png",
        extraction_timestamp="2026-05-11T09:00:00Z",
        blocks=blocks,
    )


class TestEnricher:
    def test_footer_is_filtered(self):
        """Footer blocks must never be indexed."""
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.FOOTER, text="7"),
            Block(block_id="b01", block_type=BlockType.TEXT,
                  text="أنشأ البنك المركزي المصري نظام التسوية"),
        ])
        docs, filtered = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert filtered == 1
        assert len(docs) == 1
        assert docs[0].metadata["block_id"] == "b01"

    def test_short_text_block_filtered(self):
        """Text blocks with fewer than 3 words are noise — must be dropped."""
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.TEXT, text="نظام"),  # 1 word
        ])
        docs, filtered = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert filtered == 1
        assert len(docs) == 0

    def test_short_table_not_filtered(self):
        """Tables are never filtered regardless of word count."""
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.TABLE,
                  text="CBE", table_data="<table><tr><td>CBE</td></tr></table>"),
        ])
        docs, filtered = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert filtered == 0
        assert len(docs) == 1

    def test_header_propagated_to_text(self):
        """Text blocks should have the current section header prepended."""
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.HEADER,
                  text="المصطلحات المستخدمة"),
            Block(block_id="b01", block_type=BlockType.TEXT,
                  text="يُشير هذا المصطلح إلى البنك المركزي المصري"),
        ])
        docs, _ = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        text_doc = next(d for d in docs if d.metadata["block_id"] == "b01")
        assert "[المصطلحات المستخدمة]" in text_doc.page_content

    def test_header_not_propagated_to_itself(self):
        """The header block's own page_content should NOT have a prefix."""
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.HEADER,
                  text="المصطلحات المستخدمة"),
        ])
        docs, _ = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert len(docs) == 1
        assert docs[0].page_content == "المصطلحات المستخدمة"

    def test_header_persists_across_pages(self):
        """Header context from page N should carry over to page N+1."""
        pages = [
            _make_page("rtgs", 1, [
                Block(block_id="p1b00", block_type=BlockType.HEADER,
                      text="دورة العمل في النظام"),
            ]),
            _make_page("rtgs", 2, [
                Block(block_id="p2b00", block_type=BlockType.TEXT,
                      text="يتولى البنك المركزي تشغيل النظام خلال ساعات العمل"),
            ]),
        ]
        docs, _ = enrich_pages(pages, "SOP", "2026-05-11T09:00:00Z")
        text_doc = next(d for d in docs if d.metadata["block_id"] == "p2b00")
        assert "[دورة العمل في النظام]" in text_doc.page_content

    def test_table_uses_html_for_embedding(self):
        """Table page_content should be the HTML string when available."""
        html = "<table><tr><th>A</th></tr></table>"
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.TABLE,
                  text="A", table_data=html),
        ])
        docs, _ = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert docs[0].page_content == html

    def test_metadata_fields_present(self):
        """Every Document must carry the required metadata fields."""
        required_fields = {
            "chunk_id", "doc_id", "doc_name", "doc_type", "page_num",
            "block_type", "raw_text", "crop_path",
        }
        page = _make_page("rtgs", 1, [
            Block(block_id="b00", block_type=BlockType.TEXT,
                  text="يتولى البنك المركزي تشغيل النظام خلال ساعات العمل"),
        ])
        docs, _ = enrich_pages([page], "SOP", "2026-05-11T09:00:00Z")
        assert len(docs) == 1
        for field in required_fields:
            assert field in docs[0].metadata, f"Missing metadata field: {field}"
