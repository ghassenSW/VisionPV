import json
import os
import base64
import time
import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pdf2image import convert_from_path
from mistralai import Mistral
from mistralai.models import SDKError
from dotenv import load_dotenv
from utils import log_timing

logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")
client = Mistral(api_key=api_key)

# Schema for bbox annotation: each extracted image → date_depot (stamp)
STAMP_BBOX_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "properties": {
                "date_depot": {
                    "type": "string",
                    "description": "Date du dépôt JJ/MM/AAAA si ce tampon contient F.T.U.S.A./ARRIVEE. Vide sinon."
                }
            },
            "required": ["date_depot"],
            "title": "StampAnnotation",
            "type": "object",
            "additionalProperties": False
        },
        "name": "StampAnnotation",
        "strict": True
    }
}

# Schema for document annotation: date from F.T.U.S.A./ARRIVEE stamp only
DOCUMENT_ANNOTATION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "properties": {
                "date_depot": {
                    "type": "string",
                    "description": "Date du dépôt JJ/MM/AAAA from the rectangular F.T.U.S.A./ARRIVEE stamp ONLY. Empty if no such stamp. Ignore dates from 'رقم' or 'تاريخ' in headers. Format: DD/MM/YYYY."
                }
            },
            "required": ["date_depot"],
            "title": "StampDateAnnotation",
            "type": "object",
            "additionalProperties": False
        },
        "name": "StampDateAnnotation",
        "strict": True
    }
}

def _extract_from_bbox(response):
    """Parse image_annotation from each bbox."""
    date_depot = ""
    for page in response.pages:
        for img in getattr(page, "images", []) or []:
            ann = getattr(img, "image_annotation", None)
            if not ann:
                continue
            try:
                data = json.loads(ann) if isinstance(ann, str) else ann
                d = (data.get("date_depot") or "").strip()
                if d:
                    return d
            except (json.JSONDecodeError, TypeError):
                continue
    return date_depot


def _extract_from_document_annotation(response):
    """Parse document_annotation: date from F.T.U.S.A./ARRIVEE stamp only."""
    date_depot = ""
    ann = getattr(response, "document_annotation", None)
    if not ann:
        return date_depot
    try:
        data = json.loads(ann) if isinstance(ann, str) else ann
        date_depot = (data.get("date_depot") or "").strip()
    except (json.JSONDecodeError, TypeError):
        pass
    return date_depot


def _ocr_single_image(pil_image):
    """Run OCR + annotations on a single image. Returns (markdown, date_depot)."""
    # JPEG expects RGB; PDF pages are often CMYK or P mode — avoids encoder failures.
    img = pil_image if pil_image.mode == "RGB" else pil_image.convert("RGB")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG", quality=85)
    encoded_string = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{encoded_string}"

    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": data_url},
        bbox_annotation_format=STAMP_BBOX_SCHEMA,
        document_annotation_format=DOCUMENT_ANNOTATION_SCHEMA,
        include_image_base64=False
    )
    page = response.pages[0]
    date_depot = _extract_from_document_annotation(response)
    if not date_depot:
        date_depot = _extract_from_bbox(response)
    return page.markdown, date_depot


def _merge_pages_markdown(response):
    """Combine markdown from all pages of OCR response."""
    parts = []
    for i, page in enumerate(response.pages):
        parts.append(f"\n\n--- PAGE {i + 1} ---\n\n" + (page.markdown or ""))
    return "".join(parts)


@log_timing
def _ocr_full_pdf(pdf_path):
    """OCR entire PDF in one call. Returns full document text."""
    logger.info("Uploading PDF for full-document OCR...")
    with open(pdf_path, "rb") as f:
        content = f.read()

    uploaded = client.files.upload(
        file={"file_name": os.path.basename(pdf_path), "content": content},
        purpose="ocr"
    )
    file_id = uploaded.id
    try:
        logger.info(f"File uploaded (ID: {file_id}). Requesting signed URL...")
        
        # Get signed URL with a polling loop in case of 404s (not ready) or 500s
        import time
        signed = None
        for _ in range(15):
            try:
                signed = client.files.get_signed_url(file_id=file_id)
                break
            except Exception as e:
                logger.warning(f"File not ready for URL yet ({e}). Retrying in 2s...")
                time.sleep(2)

        if not signed:
            raise Exception("Critical Error: Failed to get signed URL from Mistral after uploading.")

        doc_url = signed.url

        logger.info("Calling Mistral OCR on full PDF...")
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": doc_url
            },
            include_image_base64=False
        )
        return _merge_pages_markdown(response)
    finally:
        try:
            client.files.delete(file_id=file_id)
        except Exception as e:
            logger.warning(f"Could not delete temp file {file_id}: {e}")

def _extract_date_depot_from_page(pil_image, page_num):
    """Run stamp extraction by cropping the page into 4 equal quadrants (OCR in parallel)."""
    logger.info("Page %d: analyzing 4 quadrants for stamp (parallel)...", page_num)

    width, height = pil_image.size
    mid_x, mid_y = width // 2, height // 2
    ov_x, ov_y = 0, 0

    quadrants = [
        ("upper_left", (0, 0, mid_x + ov_x, mid_y + ov_y)),
        ("upper_right", (mid_x - ov_x, 0, width, mid_y + ov_y)),
        ("bottom_left", (0, mid_y - ov_y, mid_x + ov_x, height)),
        ("bottom_right", (mid_x - ov_x, mid_y - ov_y, width, height)),
    ]

    # Crop on the main thread only: concurrent crop() on one Image is not thread-safe
    # and caused corrupt JPEG / "image file is truncated" under ThreadPoolExecutor.
    quadrant_images = [(name, pil_image.crop(box).copy()) for name, box in quadrants]

    def ocr_one_quadrant(name_img):
        name, quadrant_img = name_img
        for attempt in range(2):
            try:
                _, page_date = _ocr_single_image(quadrant_img)
                return name, (page_date or "").strip()
            except SDKError as e:
                if e.status_code == 429 and attempt == 0:
                    logger.warning(
                        "Rate limit quadrant %s page %d; retry in 2s", name, page_num
                    )
                    time.sleep(2)
                    continue
                logger.error("SDKError quadrant %s page %d: %s", name, page_num, e)
                return name, ""
            except Exception as ex:
                logger.error("Error quadrant %s page %d: %s", name, page_num, ex)
                return name, ""
        return name, ""

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ocr_one_quadrant, qi) for qi in quadrant_images]
        for fut in as_completed(futures):
            name, page_date = fut.result()
            results[name] = page_date

    for name, _ in quadrants:
        depot = results.get(name, "")
        logger.info(
            "Page %d quadrant %s: stamp date_depot extrait = %r",
            page_num,
            name,
            depot if depot else "",
        )

    for name, _ in quadrants:
        page_date = results.get(name, "")
        if page_date:
            logger.info(
                "Page %d: date_depot retenu = %r (premier quadrant avec valeur : %s)",
                page_num,
                page_date,
                name,
            )
            return page_date
    return ""


def _stamp_date_depot_from_pdf(pdf_path):
    """Pages 1–2: stamp extraction for date_depot only."""
    logger.info("Loading pages 1-2 for stamp extraction...")
    pages = convert_from_path(pdf_path, 200, first_page=1, last_page=2)
    date_depot = ""
    for i, page in enumerate(pages):
        page_num = i + 1
        try:
            date_depot = _extract_date_depot_from_page(page, page_num)
            if date_depot:
                break
        except SDKError as e:
            if e.status_code == 429:
                logger.warning("Rate limit on page %d, waiting 2s...", page_num)
                time.sleep(2)
                date_depot = _extract_date_depot_from_page(page, page_num)
            else:
                logger.error("Error on page %d: %s", page_num, e)
        except Exception as ex:
            logger.error("Error on page %d: %s", page_num, ex)
    return date_depot


@log_timing
def process_entire_pdf(pdf_path):
    """
    Hybrid: full PDF OCR for text + stamp extraction on pages 1–2 for date_depot.
    Full-document OCR and stamp pipeline run in parallel to reduce wall-clock time.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_full = pool.submit(_ocr_full_pdf, pdf_path)
        fut_stamp = pool.submit(_stamp_date_depot_from_pdf, pdf_path)
        full_document_text = fut_full.result()
        date_depot = fut_stamp.result()

    if date_depot:
        logger.info("Extracted date_depot from stamp: %r", date_depot)
    return full_document_text, "", date_depot