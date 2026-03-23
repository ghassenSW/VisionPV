import json
import os
import base64
import time
import io
import logging
import concurrent.futures
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


@log_timing
def ocr_page_mistral(pil_image, split_for_stamp=False, page_num=None):
    """Run OCR on page. If split_for_stamp: split in two halves for better stamp detection."""
    if not split_for_stamp:
        text, date = _ocr_single_image(pil_image)
        return text, "", date

    # Pages 1-2: split 70% top / 30% bottom for text; stamp crops for date
    w, h = pil_image.size
    split_y = int(h * 0.7)
    top_part = pil_image.crop((0, 0, w, split_y))
    bottom_part = pil_image.crop((0, split_y, w, h))

    logger.info("Pages 1–2: splitting 70%% top / 30%% bottom for stamp extraction")
    top_md, top_date = _ocr_single_image(top_part)
    time.sleep(1.5)
    bottom_md, bottom_date = _ocr_single_image(bottom_part)

    # Stamp crops: top-right AND bottom-right (stamp location varies by document)
    stamp_top_right = pil_image.crop((w // 2, 0, w, split_y))  # right half of top 70%
    stamp_bottom_right = pil_image.crop((w // 2, split_y, w, h))  # right half of bottom 30%
    time.sleep(1.5)
    _, stamp_tr_date = _ocr_single_image(stamp_top_right)
    time.sleep(1.5)
    _, stamp_br_date = _ocr_single_image(stamp_bottom_right)
    if page_num:
        logger.info("Page %d STAMP ZONE top-right: date=%r", page_num, stamp_tr_date)
        logger.info("Page %d STAMP ZONE bottom-right: date=%r", page_num, stamp_br_date)

    merged_md = top_md + "\n\n" + bottom_md
    # Take date from whichever stamp crop has it (handles both top-right and bottom-right stamps)
    date_depot = stamp_tr_date or stamp_br_date or top_date or bottom_date
    if page_num and date_depot:
        src = "top-right stamp" if stamp_tr_date else "bottom-right stamp" if stamp_br_date else "top" if top_date else "bottom"
        logger.info("Page %d: date_depot=%r from %s", page_num, date_depot, src)

    return merged_md, "", date_depot


@log_timing
def process_entire_pdf(pdf_path):
    logger.info(f"Loading PDF pages...")
    # OPTIMIZATION: Reduced from 300 to 200 DPI. Mistral is highly capable at 200, 
    # and this reduces the image memory size by more than 50%, speeding up conversion and upload.
    pages = convert_from_path(pdf_path, 200) 
    
    def process_single_page(i, page):
        logger.info(f"Calling Mistral OCR for Page {i+1}/{len(pages)}...")
        split_for_stamp = i < 2  # Pages 1 and 2: split in half for better stamp detection
        while True:
            try:
                page_text, ref_ftusa, date_depot = ocr_page_mistral(
                    page, split_for_stamp=split_for_stamp, page_num=i + 1
                )
                time.sleep(1.5)
                return (i, f"\n\n--- PAGE {i+1} ---\n\n" + page_text, ref_ftusa, date_depot)
            except SDKError as e:
                if e.status_code == 429:
                    logger.warning(f"Rate limit hit! Waiting 65s before retry for page {i+1}...")
                    time.sleep(65)
                else:
                    logger.error(f"Error on page {i+1}: {e}")
                    return (i, "", "", "")
            except Exception as ex:
                logger.error(f"Unexpected error on page {i+1}: {ex}")
                return (i, "", "", "")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(process_single_page, i, page): i for i, page in enumerate(pages)}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Error yielding future: {e}")

    results.sort(key=lambda x: x[0])
    full_document_text = "".join([res[1] for res in results])
    ref_ftusa, date_depot = "", ""
    for r in results:
        if r[2] or r[3]:
            ref_ftusa = ref_ftusa or r[2]
            date_depot = date_depot or r[3]
            if date_depot:
                break
    if date_depot:
        logger.info(f"Extracted date_depot from stamp: {date_depot!r}")
    return full_document_text, ref_ftusa, date_depot