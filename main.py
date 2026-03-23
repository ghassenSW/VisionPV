import os
import shutil
import uuid
import logging
import time
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import your existing modules
from OCR_mistral import process_entire_pdf
from LLM_mistral import process_pv

app = FastAPI(
    title="Tunisian PV Extraction API",
    description="API for converting PDF accident reports into structured JSON using Mistral AI"
)

# Enable CORS (Crucial if you build a web frontend later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary directory for processing
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/extract-pv")
async def extract_pv_endpoint(file: UploadFile = File(...)):
    # 1. Validation
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")

    # Generate unique ID and Path
    request_id = str(uuid.uuid4())
    temp_pdf_path = os.path.join(UPLOAD_DIR, f"{request_id}_{file.filename}")

    try:
        start_total = time.time()
        
        # 2. Save uploaded PDF locally
        t0 = time.time()
        logger.info(f"[{request_id}] Saving file: {file.filename}")
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"[{request_id}] File saving took {time.time() - t0:.2f} seconds.")

        # 3. PHASE 1: OCR (PDF -> Text)
        t1 = time.time()
        logger.info(f"[{request_id}] Starting OCR processing...")
        full_ocr_text = process_entire_pdf(temp_pdf_path)
        logger.info(f"[{request_id}] OCR processing took {time.time() - t1:.2f} seconds.")

        # 4. PHASE 2: LLM EXTRACTION (OCR Text + PDF Path -> JSON)
        t2 = time.time()
        logger.info(f"[{request_id}] Starting LLM Feature Extraction...")
        final_json = process_pv(full_ocr_text, temp_pdf_path)
        logger.info(f"[{request_id}] LLM Extraction took {time.time() - t2:.2f} seconds.")

        # 5. Return JSON to Client
        logger.info(f"[{request_id}] Extraction successful. Total time: {time.time() - start_total:.2f} seconds.")
        return final_json

    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement: {str(e)}")

    finally:
        # 6. Cleanup: Remove the temporary file from the server
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            logger.info(f"[{request_id}] Temporary file cleaned up.")

@app.get("/")
def health_check():
    return {"status": "running", "message": "PV Extraction API is active"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)