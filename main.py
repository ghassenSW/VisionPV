import os
import uuid
import logging
import time
import asyncio
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
    """Validate uploaded file is PDF (extension). Size enforced while streaming."""
    name = (file.filename or "").strip()
    base = os.path.basename(name).lower()
    if not base.endswith(".pdf"):
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
    safe_name = os.path.basename((file.filename or "upload").strip()) or "upload.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"
    temp_pdf_path = os.path.join(UPLOAD_DIR, f"{request_id}_{safe_name}")

    try:
        start_total = time.time()

        logger.info(f"[{request_id}] Saving file: {safe_name}")
        t0 = time.time()
        file_size = 0
        chunk_size = 1024 * 1024
        with open(temp_pdf_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux. Limite: {MAX_UPLOAD_SIZE // (1024*1024)} MB.",
                    )
                buffer.write(chunk)

        logger.info(f"[{request_id}] File saved ({file_size // 1024} KB) in {time.time() - t0:.2f}s")

        def _run_extraction():
            full_ocr_text, ref_ftusa, date_depot = process_entire_pdf(temp_pdf_path)
            return process_pv(
                full_ocr_text, ref_ftusa=ref_ftusa, date_depot=date_depot
            )

        t1 = time.time()
        logger.info(f"[{request_id}] Starting OCR + LLM processing...")
        final_json = await asyncio.to_thread(_run_extraction)
        logger.info(f"[{request_id}] OCR + LLM took {time.time() - t1:.2f}s")

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
