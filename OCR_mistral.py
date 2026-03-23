import os
import base64
import time
import io
import cv2
import numpy as np
import logging
import concurrent.futures
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
    # OPTIMIZATION: Saving as JPEG instead of PNG massively reduces payload size
    # and drastically speeds up the network upload to Mistral without losing text quality.
    pil_image.save(img_byte_arr, format='JPEG', quality=85)
    encoded_string = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{encoded_string}"
    
    response = client.ocr.process(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": data_url}
    )
    return response.pages[0].markdown

@log_timing
def process_entire_pdf(pdf_path):
    logger.info(f"Loading PDF pages...")
    # OPTIMIZATION: Reduced from 300 to 200 DPI. Mistral is highly capable at 200, 
    # and this reduces the image memory size by more than 50%, speeding up conversion and upload.
    pages = convert_from_path(pdf_path, 200) 
    
    def process_single_page(i, page):
        logger.info(f"Checking Page {i+1}/{len(pages)}...")
        
        if not is_page_relevant(page):
            logger.info(f"Skipping Page {i+1} (not relevant)")
            return (i, "")
            
        logger.info(f"Calling Mistral OCR for Page {i+1}...")
        
        while True:
            try:
                page_text = ocr_page_mistral(page)
                # Small safety delay strictly to protect free-tier quotas (1 request / second limit)
                time.sleep(1.5)
                return (i, f"\n\n--- PAGE {i+1} ---\n\n" + page_text)
            except SDKError as e:
                if e.status_code == 429:
                    logger.warning(f"Rate limit hit! Waiting 65s before retry for page {i+1}...")
                    time.sleep(65)
                else:
                    logger.error(f"Error on page {i+1}: {e}")
                    return (i, "")
            except Exception as ex:
                logger.error(f"Unexpected error on page {i+1}: {ex}")
                return (i, "")

    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(process_single_page, i, page): i for i, page in enumerate(pages)}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Error yielding future: {e}")

    # Reassemble pages sequentially so the document remains in the correct order
    results.sort(key=lambda x: x[0])
    full_document_text = "".join([res[1] for res in results])
                    
    return full_document_text