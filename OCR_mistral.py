import json
import os
import base64
import time
import io
import logging
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
    img_byte_arr = io.BytesIO()
    pil_image.save(img_byte_arr, format='JPEG', quality=85)
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
        signed = client.files.get_signed_url(file_id=file_id)
        doc_url = signed.url
        logger.info("Calling Mistral OCR on full PDF...")
        time.sleep(1)
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": doc_url},
            include_image_base64=False
        )
        return _merge_pages_markdown(response)
    finally:
        try:
            client.files.delete(file_id=file_id)
        except Exception as e:
            logger.warning(f"Could not delete temp file {file_id}: {e}")

# see the accuracty_barchart_V2.png for this version of code
def _extract_date_depot_from_page(pil_image, page_num):
    """Run stamp extraction on the entire full page directly without any cropping."""
    logger.info("Page %d: analyzing full page for stamp...", page_num)
    
    _, page_date = _ocr_single_image(pil_image)

    if page_num and page_date:
        logger.info("Page %d: date_depot=%r found on full page", page_num, page_date)
        
    return page_date


@log_timing
def process_entire_pdf(pdf_path):
    """
    Hybrid: full PDF OCR for text + stamp extraction on full pages 1-2 for date_depot.
    """
    # 1. Full PDF → all OCR text (1 call)
    full_document_text = _ocr_full_pdf(pdf_path)

    # 2. Pages 1-2: stamp extraction for date_depot only
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
                logger.warning("Rate limit on page %d, waiting 65s...", page_num)
                time.sleep(65)
                date_depot = _extract_date_depot_from_page(page, page_num)
            else:
                logger.error("Error on page %d: %s", page_num, e)
        except Exception as ex:
            logger.error("Error on page %d: %s", page_num, ex)
        time.sleep(1.5)

    if date_depot:
        logger.info("Extracted date_depot from stamp: %r", date_depot)
    return full_document_text, "", date_depot