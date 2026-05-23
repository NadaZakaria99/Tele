#!/usr/bin/env python3
"""
extract_local.py — Standalone PDF Extraction Script (No Docker Required)
=========================================================================
Run this on your local machine to:
  1. Convert PDFs → page images (pypdfium2)
  2. Run Chandra OCR-2 on each page (local GPU)
  3. Generate visual crop PNGs for each block
  4. Save everything to pipeline_output/ ready to copy to the Docker machine

Usage:
    python extract_local.py

Output structure (copy this entire folder to the Docker machine):
    data/
      docs_images/<doc_id>/page_001.png ...   <- page images
      pipeline_output/
        extractions/<doc_id>/page_001.json ... <- OCR results
        crops/<doc_id>/page_001/<crop>.png ... <- visual crops

Install dependencies first (run once):
    pip install pypdfium2 Pillow beautifulsoup4 pydantic python-dotenv
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    pip install transformers accelerate bitsandbytes huggingface_hub
    pip install git+https://github.com/datalab-org/chandra-ocr.git
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================
# Load from .env if available
try:
    from dotenv import load_dotenv
    # Script lives at <project_root>/extract_local.py
    # .env lives at  <project_root>/deploy/config/.env
    ENV_PATH = Path(__file__).parent / "deploy" / "config" / ".env"
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        print(f"[config] Loaded .env from {ENV_PATH}")
    else:
        # Fallback: same directory as script
        ENV_PATH2 = Path(__file__).parent / ".env"
        if ENV_PATH2.exists():
            load_dotenv(ENV_PATH2)
            print(f"[config] Loaded .env from {ENV_PATH2}")
        else:
            print(f"[config] WARNING: .env not found at {ENV_PATH}")
except ImportError:
    pass

PDF_SOURCE_DIR    = Path(os.getenv("PDF_SOURCE_DIR",  r"C:\Users\n.zakaria\Desktop\Data"))
DATA_DIR          = Path(os.getenv("DATA_DIR",         str(Path(__file__).parent.parent / "data")))
HF_TOKEN          = os.getenv("HF_TOKEN", "")
MAX_INFERENCE_DIM = int(os.getenv("MAX_INFERENCE_DIM", "1600"))
CHANDRA_MODEL_ID  = "datalab-to/chandra-ocr-2"
CROP_PADDING_PX   = 8
RENDER_DPI_SCALE  = 2.7   # ~200 DPI — good quality for Arabic OCR

DOCS_IMAGES_DIR     = DATA_DIR / "docs_images"
PIPELINE_OUTPUT_DIR = DATA_DIR / "pipeline_output"
EXTRACTIONS_DIR     = PIPELINE_OUTPUT_DIR / "extractions"
CROPS_DIR           = PIPELINE_OUTPUT_DIR / "crops"

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# =============================================================================
# Inline Pydantic schemas (avoids needing to install the nbe_schemas package)
# =============================================================================

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class BlockType(str, Enum):
    TEXT    = "text"
    TABLE   = "table"
    HEADER  = "header"
    FOOTER  = "footer"
    FIGURE  = "figure"
    LIST    = "list"
    UNKNOWN = "unknown"


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def as_list(self):
        return [self.x1, self.y1, self.x2, self.y2]


class Block(BaseModel):
    block_id:   str
    block_type: BlockType = BlockType.TEXT
    text:       str = ""
    bbox:       Optional[BBox] = None
    confidence: Optional[float] = None
    language:   str = "ar"
    table_data: Optional[str] = None
    crop_path:  Optional[str] = None


class PageResult(BaseModel):
    doc_id:               str
    doc_name:             str
    doc_type:             str
    page_num:             int
    original_size:        tuple[int, int]
    inference_size:       tuple[int, int]
    page_image_path:      str
    extraction_timestamp: str
    blocks:               list[Block] = []


# =============================================================================
# Step 1 — PDF → Page Images
# =============================================================================

def pdf_to_images(pdf_path: Path, output_dir: Path) -> list[Path]:
    """Convert every page of a PDF to a PNG. Returns list of saved image paths."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        log.error("pypdfium2 not installed. Run: pip install pypdfium2")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    image_paths = []

    log.info(f"  Converting {len(pdf)} pages to PNG images...")
    for i in range(len(pdf)):
        img_path = output_dir / f"page_{i + 1:03d}.png"

        if img_path.exists():
            log.info(f"    [SKIP] page_{i + 1:03d}.png already exists")
            image_paths.append(img_path)
            continue

        page    = pdf[i]
        bitmap  = page.render(scale=RENDER_DPI_SCALE)
        pil_img = bitmap.to_pil()
        pil_img.save(str(img_path))
        image_paths.append(img_path)
        log.info(f"    Saved page_{i + 1:03d}.png  ({pil_img.width}x{pil_img.height} px)")

    return image_paths


# =============================================================================
# Coordinate helpers
# =============================================================================

def resize_for_inference(image, max_dim: int):
    from PIL import Image
    w, h = image.size
    if max(w, h) <= max_dim:
        return image, 1.0
    scale = max_dim / max(w, h)
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS), scale


def correct_bbox(raw_bbox, orig_w, orig_h, inf_w, inf_h, scale):
    """Convert Chandra OCR-2 bbox coordinates back to original image pixel space."""
    if raw_bbox is None or len(raw_bbox) != 4:
        return None

    x1, y1, x2, y2 = raw_bbox

    # Case A: normalized floats [0.0 – 1.0]
    if all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in [x1, y1, x2, y2]):
        x1 *= inf_w; y1 *= inf_h; x2 *= inf_w; y2 *= inf_h
        if scale < 1.0:
            inv = 1.0 / scale
            x1, y1, x2, y2 = x1 * inv, y1 * inv, x2 * inv, y2 * inv
    # Case B: 0–1000 integer space (Chandra OCR-2 default)
    else:
        x1 = (x1 / 1000.0) * orig_w
        y1 = (y1 / 1000.0) * orig_h
        x2 = (x2 / 1000.0) * orig_w
        y2 = (y2 / 1000.0) * orig_h

    if x2 <= x1 or y2 <= y1:
        return None

    return BBox(x1=round(x1), y1=round(y1), x2=round(x2), y2=round(y2))


# =============================================================================
# Step 2 — OCR Model (Chandra OCR-2)
# =============================================================================

_model = None

LABEL_MAP = {
    "page-header":    BlockType.HEADER,
    "page-footer":    BlockType.FOOTER,
    "text":           BlockType.TEXT,
    "table":          BlockType.TABLE,
    "figure":         BlockType.FIGURE,
    "list":           BlockType.LIST,
    "section-header": BlockType.HEADER,
    "caption":        BlockType.TEXT,
}


def load_model():
    """Load Chandra OCR-2 into GPU memory using 4-bit NF4 quantization. Runs once."""
    global _model
    if _model is not None:
        return

    try:
        import torch
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            BitsAndBytesConfig,
        )
        from huggingface_hub import login
    except ImportError as e:
        log.error(f"Missing dependency: {e}")
        log.error("Run:")
        log.error("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        log.error("  pip install transformers accelerate bitsandbytes huggingface_hub")
        sys.exit(1)

    if HF_TOKEN:
        log.info("Logging in to HuggingFace...")
        login(token=HF_TOKEN, add_to_git_credential=False)
    else:
        log.warning("HF_TOKEN not set — download will fail if model is gated")

    log.info(f"Loading Chandra OCR-2 (4-bit NF4) from '{CHANDRA_MODEL_ID}'...")
    log.info("This uses ~8GB VRAM and is ~4x faster than full precision...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    _model = AutoModelForImageTextToText.from_pretrained(
        CHANDRA_MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        token=HF_TOKEN or None,
    )
    _model.eval()
    _model.processor = AutoProcessor.from_pretrained(
        CHANDRA_MODEL_ID,
        token=HF_TOKEN or None,
    )
    _model.processor.tokenizer.padding_side = "left"
    log.info("Model loaded successfully.")


def parse_blocks(raw_html, doc_id, page_num, orig_w, orig_h, inf_w, inf_h, scale, language):
    """Parse Chandra OCR-2 HTML output into a list of Block objects."""
    from bs4 import BeautifulSoup

    soup   = BeautifulSoup(raw_html, "html.parser")
    blocks = []

    for idx, div in enumerate(soup.find_all("div", attrs={"data-bbox": True})):
        block_id   = f"{doc_id}_p{page_num:03d}_b{idx:02d}"
        raw_label  = div.get("data-label", "text").lower().strip()
        block_type = LABEL_MAP.get(raw_label, BlockType.TEXT)

        raw_bbox_str = div.get("data-bbox", "").strip()
        raw_bbox = None
        if raw_bbox_str:
            try:
                parts = list(map(float, raw_bbox_str.split()))
                if len(parts) == 4:
                    raw_bbox = parts
            except (ValueError, TypeError):
                pass

        bbox       = correct_bbox(raw_bbox, orig_w, orig_h, inf_w, inf_h, scale)
        text       = div.get_text(separator=" ", strip=True)
        table_data = div.decode_contents().strip() if block_type == BlockType.TABLE else None

        blocks.append(Block(
            block_id=block_id,
            block_type=block_type,
            text=text or "",
            bbox=bbox,
            language=language,
            table_data=table_data,
            crop_path=None,
        ))

    return blocks


def extract_page(doc_id, doc_name, doc_type, page_num, image_path, language="ara") -> PageResult:
    """Run Chandra OCR-2 on a single page image and return a PageResult."""
    import torch
    from PIL import Image

    try:
        from chandra.model.hf import generate_hf
        from chandra.model.schema import BatchInputItem
    except ImportError:
        log.error("chandra-ocr not installed.")
        log.error("Run: pip install git+https://github.com/datalab-org/chandra-ocr.git")
        sys.exit(1)

    original_image = Image.open(image_path).convert("RGB")
    orig_w, orig_h = original_image.size

    inference_image, scale = resize_for_inference(original_image, MAX_INFERENCE_DIM)
    inf_w, inf_h = inference_image.size

    log.info(f"    OCR page {page_num:03d}: {orig_w}x{orig_h} -> {inf_w}x{inf_h} (scale={scale:.3f})")

    batch = [BatchInputItem(image=inference_image, prompt_type="ocr_layout")]
    with torch.inference_mode():
        results = generate_hf(batch, _model)
        result  = results[0]

    if result.error:
        raise RuntimeError(f"Chandra OCR error: {result.error}")

    blocks = parse_blocks(
        result.raw,
        doc_id, page_num,
        orig_w, orig_h,
        inf_w, inf_h,
        scale, language,
    )

    # Free GPU memory after each page
    del inference_image, original_image, results, result
    torch.cuda.empty_cache()
    gc.collect()

    return PageResult(
        doc_id=doc_id,
        doc_name=doc_name,
        doc_type=doc_type,
        page_num=page_num,
        original_size=(orig_w, orig_h),
        inference_size=(inf_w, inf_h),
        page_image_path=str(image_path),
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        blocks=blocks,
    )


# =============================================================================
# Step 3 — Crop Generation
# =============================================================================

def generate_crops(page_result: PageResult, page_image_path: Path) -> PageResult:
    """Crop each detected block from the page image and save as PNG."""
    from PIL import Image

    doc_id    = page_result.doc_id
    page_num  = page_result.page_num
    page_name = f"page_{page_num:03d}"

    crops_dir = CROPS_DIR / doc_id / page_name
    crops_dir.mkdir(parents=True, exist_ok=True)

    page_image    = Image.open(page_image_path).convert("RGB")
    img_w, img_h  = page_image.size

    for block in page_result.blocks:
        if block.bbox is None:
            continue

        crop_filename = f"{block.block_id}_{block.block_type.value}.png"
        crop_abs      = crops_dir / crop_filename
        crop_rel      = f"crops/{doc_id}/{page_name}/{crop_filename}"

        if crop_abs.exists():
            block.crop_path = crop_rel
            continue

        x1 = max(0,     block.bbox.x1 - CROP_PADDING_PX)
        y1 = max(0,     block.bbox.y1 - CROP_PADDING_PX)
        x2 = min(img_w, block.bbox.x2 + CROP_PADDING_PX)
        y2 = min(img_h, block.bbox.y2 + CROP_PADDING_PX)

        if x2 > x1 and y2 > y1:
            page_image.crop((x1, y1, x2, y2)).save(
                str(crop_abs), format="PNG", optimize=True
            )
            block.crop_path = crop_rel

    return page_result


# =============================================================================
# Per-PDF pipeline
# =============================================================================

def process_pdf(pdf_path: Path) -> dict:
    """Run the full extraction pipeline for one PDF file."""
    doc_id   = re.sub(r"[^\w\-]", "_", pdf_path.stem.lower())
    doc_name = pdf_path.name
    doc_type = "Legal Circular"   # change to "SOP" or other if needed

    log.info(f"\n{'=' * 60}")
    log.info(f"Processing: {doc_name}  (doc_id={doc_id})")
    log.info(f"{'=' * 60}")

    # ── Step 1: PDF → images ──────────────────────────────────────────────────
    images_dir  = DOCS_IMAGES_DIR / doc_id
    image_paths = pdf_to_images(pdf_path, images_dir)

    if not image_paths:
        log.warning(f"  No images produced for {doc_name} — skipping")
        return {"doc_id": doc_id, "status": "skipped", "reason": "no images"}

    # ── Step 2: OCR + crops, page by page ─────────────────────────────────────
    extractions_dir = EXTRACTIONS_DIR / doc_id
    extractions_dir.mkdir(parents=True, exist_ok=True)

    successful = []
    failed     = []

    for page_num, image_path in enumerate(image_paths, start=1):
        out_json = extractions_dir / f"page_{page_num:03d}.json"

        # Resume support: skip pages already extracted
        if out_json.exists():
            log.info(f"  [SKIP] page_{page_num:03d} already extracted")
            with open(out_json, encoding="utf-8") as f:
                successful.append(PageResult.model_validate_json(f.read()))
            continue

        try:
            page_result = extract_page(
                doc_id=doc_id,
                doc_name=doc_name,
                doc_type=doc_type,
                page_num=page_num,
                image_path=str(image_path),
            )
            page_result = generate_crops(page_result, image_path)

            # Save JSON immediately (safe resume if interrupted)
            with open(out_json, "w", encoding="utf-8") as f:
                f.write(page_result.model_dump_json(indent=2))

            successful.append(page_result)
            log.info(f"  [OK] page_{page_num:03d}: {len(page_result.blocks)} blocks")

        except Exception as e:
            log.error(f"  [FAIL] page_{page_num:03d}: {e}")
            failed.append({"page_num": page_num, "error": str(e)})
            import torch
            torch.cuda.empty_cache()
            gc.collect()

    log.info(f"  Finished: {len(successful)} pages OK, {len(failed)} failed")
    return {
        "doc_id":       doc_id,
        "doc_name":     doc_name,
        "status":       "complete",
        "pages_ok":     len(successful),
        "pages_failed": len(failed),
        "output_dir":   str(extractions_dir),
    }


# =============================================================================
# Main entry point
# =============================================================================

def main():
    log.info("=" * 60)
    log.info("NBE Local Extraction Pipeline")
    log.info("=" * 60)
    log.info(f"PDF source : {PDF_SOURCE_DIR}")
    log.info(f"Output dir : {PIPELINE_OUTPUT_DIR}")

    # ── Validate PDF source directory ─────────────────────────────────────────
    if not PDF_SOURCE_DIR.exists():
        log.error(f"PDF_SOURCE_DIR not found: {PDF_SOURCE_DIR}")
        log.error("Open deploy/config/.env and update the PDF_SOURCE_DIR line.")
        sys.exit(1)

    pdf_files = sorted(PDF_SOURCE_DIR.glob("**/*.pdf"))
    if not pdf_files:
        log.error(f"No PDF files found in {PDF_SOURCE_DIR}")
        sys.exit(1)

    log.info(f"\nFound {len(pdf_files)} PDF(s):")
    for p in pdf_files:
        log.info(f"  - {p.name}")

    # ── Create all output directories ─────────────────────────────────────────
    DOCS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    PIPELINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load OCR model once (shared across all PDFs) ──────────────────────────
    log.info("\nLoading OCR model...")
    load_model()

    # ── Process each PDF ──────────────────────────────────────────────────────
    results = []
    for pdf_path in pdf_files:
        result = process_pdf(pdf_path)
        results.append(result)

    # ── Final summary ─────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("EXTRACTION COMPLETE")
    log.info("=" * 60)
    for r in results:
        icon = "OK" if r["status"] == "complete" else "FAIL"
        log.info(
            f"  [{icon}] {r.get('doc_name', r['doc_id'])}: "
            f"{r.get('pages_ok', 0)} pages extracted, "
            f"{r.get('pages_failed', 0)} failed"
        )

    log.info(f"\nAll output saved to:")
    log.info(f"  {DATA_DIR}")
    log.info("\nCopy that entire 'data' folder to the Docker machine, then run:")
    log.info("  docker compose -f deploy/docker-compose.no-extraction.yml \\")
    log.info("    --env-file deploy/config/.env up -d --build")
    log.info("\nThen trigger indexing once:")
    log.info("  curl -X POST http://localhost:8001/v1/index/legacy \\")
    log.info('    -H "Content-Type: application/json" \\')
    log.info('    -d \'{"extractions_dir": "/data/pipeline_output/extractions"}\'')


if __name__ == "__main__":
    main()