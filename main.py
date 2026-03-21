import os
import shutil
import uuid
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
        # 2. Save uploaded PDF locally
        print(f"[{request_id}] Saving file: {file.filename}")
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 3. PHASE 1: OCR (PDF -> Text)
        print(f"[{request_id}] Starting OCR processing...")
        full_ocr_text = process_entire_pdf(temp_pdf_path)

        # 4. PHASE 2: LLM EXTRACTION (OCR Text + PDF Path -> JSON)
        # Based on your requirement: process_pv handles Vision and Text logic
        print(f"[{request_id}] Starting LLM Feature Extraction...")
        final_json = process_pv(full_ocr_text, temp_pdf_path)

        # 5. Return JSON to Client
        print(f"[{request_id}] Extraction successful.")
        return final_json

    except Exception as e:
        print(f"[{request_id}] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement: {str(e)}")

    finally:
        # 6. Cleanup: Remove the temporary file from the server
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            print(f"[{request_id}] Temporary file cleaned up.")

@app.get("/")
def health_check():
    return {"status": "running", "message": "PV Extraction API is active"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)