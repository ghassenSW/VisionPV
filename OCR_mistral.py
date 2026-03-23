import os
import base64
import time
import io
import cv2
import numpy as np
import logging
from functools import wraps
from PIL import Image
from pdf2image import convert_from_path
from mistralai import Mistral
from mistralai.models import SDKError
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def log_timing(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        logger.info(f"{func.__name__} took {time.time() - start:.2f} seconds")
        return result
    return wrapper

load_dotenv()

# --- CONFIGURATION ---
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")
client = Mistral(api_key=api_key)

@log_timing
def is_page_relevant(pil_image):
    open_cv_image = np.array(pil_image.convert('RGB'))
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    line_count = 0 if lines is None else len(lines)

    try:
        if line_count < 5:
            return False
        return True
    except:
        return True

@log_timing
def ocr_page_mistral(pil_image):
    img_byte_arr = io.BytesIO()
    pil_image.save(img_byte_arr, format='PNG')
    encoded_string = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    data_url = f"data:image/png;base64,{encoded_string}"
    
    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": data_url}
    )
    return response.pages[0].markdown

@log_timing
def process_entire_pdf(pdf_path):
    logger.info(f"Loading PDF pages...")
    pages = convert_from_path(pdf_path, 300) 
    full_document_text = ""
    
    for i, page in enumerate(pages):
        logger.info(f"Checking Page {i+1}/{len(pages)}...")
        
        if not is_page_relevant(page):
            logger.info(f"Skipping Page {i+1} (not relevant)")
            continue
            
        logger.info(f"Calling Mistral OCR for Page {i+1}...")
        
        success = False
        while not success:
            try:
                page_text = ocr_page_mistral(page)
                full_document_text += f"\n\n--- PAGE {i+1} ---\n\n" + page_text
                success = True
                if i < len(pages) - 1:
                    time.sleep(1) 
                    
            except SDKError as e:
                if e.status_code == 429:
                    # --- OPTIMIZATION 2: DYNAMIC RETRY ---
                    logger.warning("Rate limit hit! Waiting 65s before retry...")
                    time.sleep(65)
                else:
                    logger.error(f"Error on page {i+1}: {e}")
                    break
                    
    return full_document_text