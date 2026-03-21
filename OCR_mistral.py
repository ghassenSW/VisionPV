import os
import base64
import time
import io
import cv2
import numpy as np
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from mistralai import Mistral
from mistralai.models import SDKError
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")
client = Mistral(api_key=api_key)

def is_page_relevant(pil_image):
    open_cv_image = np.array(pil_image.convert('RGB'))
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
    line_count = 0 if lines is None else len(lines)

    try:
        width, height = pil_image.size
        top_crop = pil_image.crop((0, 0, width, height // 3))
        local_text = pytesseract.image_to_string(top_crop, lang='ara')
        keywords = ["الجمهورية", "وزارة", "محضر", "بحث", "الحرس", "الشرطة"]
        has_keywords = any(key in local_text for key in keywords)
        if has_keywords:
            return True
        if len(local_text.strip()) < 30 and line_count < 5:
            return False
        return True
    except:
        return True

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

def process_entire_pdf(pdf_path):
    print(f"Loading PDF pages...")
    pages = convert_from_path(pdf_path, 300) 
    full_document_text = ""
    
    for i, page in enumerate(pages):
        print(f"Checking Page {i+1}/{len(pages)}...")
        
        if not is_page_relevant(page):
            print(f"⏩ Skipping Page {i+1}")
            continue
            
        print(f"📝 Calling Mistral for Page {i+1}...")
        
        success = False
        while not success:
            try:
                page_text = ocr_page_mistral(page)
                full_document_text += f"\n\n--- PAGE {i+1} ---\n\n" + page_text
                success = True
                
                # --- OPTIMIZATION 1: REMOVED FIXED SLEEP ---
                # Instead of waiting 30s every time, we wait only 1s 
                # to allow the network buffer to clear.
                if i < len(pages) - 1:
                    time.sleep(1) 
                    
            except SDKError as e:
                if e.status_code == 429:
                    # --- OPTIMIZATION 2: DYNAMIC RETRY ---
                    print("Rate limit hit! Waiting 65s before retry...")
                    time.sleep(65)
                else:
                    print(f"Error on page {i+1}: {e}")
                    break
                    
    return full_document_text

if __name__ == "__main__":
    pdf_path = r"C:\Users\ghass\OneDrive\Desktop\PFE\PV dataset\Export PVs\PVs-06-2021\PV-16_06_2021-77.pdf"
    if os.path.exists(pdf_path):
        final_text = process_entire_pdf(pdf_path)
        output_dir = r"C:\Users\ghass\OneDrive\Desktop\PFE\mistral\ocr_text"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "test_16.txt")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"Success! Full document scanned. Saved to {output_file}")
    else:
        print(f"Error: The file {pdf_path} does not exist.")