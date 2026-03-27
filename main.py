import os
import shutil
import uuid
import logging
import time
import uvicorn
from fastapi import APIRouter, FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from OCR_mistral import process_entire_pdf
from LLM_mistral import process_pv
from schemas import PVExtractionResponse, HealthResponse

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

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

# API v1 router
api_v1 = APIRouter(prefix="/api/v1/pv", tags=["v1"])

# Temporary directory for processing
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def validate_pdf_upload(file: UploadFile = File(...)) -> UploadFile:
    """Validate uploaded file is PDF and within size limits."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Seuls les fichiers PDF sont acceptés."
        )
    return file


@api_v1.post("/pv-extraction", response_model=PVExtractionResponse)
async def pv_extraction_endpoint(
    file: UploadFile = Depends(validate_pdf_upload)
):
    request_id = str(uuid.uuid4())
    temp_pdf_path = os.path.join(UPLOAD_DIR, f"{request_id}_{file.filename}")

    try:
        start_total = time.time()

        logger.info(f"[{request_id}] Saving file: {file.filename}")
        t0 = time.time()
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(temp_pdf_path)
        if file_size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux ({file_size // (1024*1024)} MB). Limite: {MAX_UPLOAD_SIZE // (1024*1024)} MB."
            )
        logger.info(f"[{request_id}] File saved ({file_size // 1024} KB) in {time.time() - t0:.2f}s")

        t1 = time.time()
        logger.info(f"[{request_id}] Starting OCR processing...")
        full_ocr_text, ref_ftusa, date_depot = process_entire_pdf(temp_pdf_path)
        logger.info(f"[{request_id}] OCR processing took {time.time() - t1:.2f}s")

        t2 = time.time()
        logger.info(f"[{request_id}] Starting LLM extraction...")
        final_json = process_pv(full_ocr_text, ref_ftusa=ref_ftusa, date_depot=date_depot)
        logger.info(f"[{request_id}] LLM extraction took {time.time() - t2:.2f}s")

        logger.info(f"[{request_id}] Extraction successful. Total: {time.time() - start_total:.2f}s")
        return PVExtractionResponse.from_extraction_dict(final_json)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur lors du traitement: {str(e)}")

    finally:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            logger.info(f"[{request_id}] Temporary file cleaned up.")


@api_v1.get("/", response_model=HealthResponse)
def health_check():
    return HealthResponse()


@api_v1.get("/health", response_model=HealthResponse)
def health_check_explicit():
    return HealthResponse()


app.include_router(api_v1)

# Root redirect for backwards compatibility
@app.get("/")
def root_redirect():
    return {
        "status": "running",
        "message": "PV Extraction API is active. Use /api/v1/pv/ for endpoints.",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
