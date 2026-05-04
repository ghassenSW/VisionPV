import os
import shutil
import uuid
import logging
import time
import uvicorn
from fastapi import APIRouter, FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True
)
logger = logging.getLogger(__name__)

# Ensure root logger also logs to console
root_logger = logging.getLogger()
if not root_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(handler)

from OCR_mistral import process_entire_pdf
from LLM_gemini import process_pv

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

app = FastAPI(
    title="Tunisian PV Extraction API",
    description="API for converting PDF accident reports into structured JSON using Mistral AI"
)

# Add startup event to confirm API is running
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 80)
    logger.info("🚀 VISIONPV API STARTING UP")
    logger.info(f"Server listening on http://0.0.0.0:8080")
    logger.info("Endpoints available:")
    logger.info("  - POST /api/report/extract (main extraction endpoint)")
    logger.info("  - GET  /api/version (version info)")
    logger.info("  - GET  /api/health (health check)")
    logger.info("=" * 80)

# Add request/response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"📨 Incoming {request.method} request to {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"✅ Response: {response.status_code} for {request.method} {request.url.path}")
        return response
    except Exception as e:
        logger.error(f"❌ Error processing {request.method} {request.url.path}: {e}")
        raise

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "INVALID_REQUEST",
            "details": "The request is missing required fields or contains invalid values."
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    content = exc.detail
    if not isinstance(content, dict):
        content = {
            "success": False,
            "error": "HTTP_ERROR",
            "details": "An unexpected HTTP error occurred. Please check your request and try again."
        }
    return JSONResponse(status_code=exc.status_code, content=content)

# Enable CORS (Crucial if you build a web frontend later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 router
api_v1 = APIRouter(prefix="/api", tags=["v1"])

# Temporary directory for processing
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@api_v1.get("/version")
def api_version():
    return {"version": "1.0"}


def validate_pdf_upload(reportFile: UploadFile = File(...)) -> UploadFile:
    """Validate uploaded file is PDF and within size limits."""
    if not reportFile.filename or not reportFile.filename.lower().endswith((".pdf", ".jpeg", ".jpg", ".png")):
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "INVALID_REQUEST",
                "details": "Only PDF, JPEG, and PNG files are accepted. Please upload a valid report file."
            }
        )
    return reportFile


@api_v1.post("/report/extract", response_model_exclude_none=True)
async def pv_extraction_endpoint(
    requestId: str = Form(...),
    reportFile: UploadFile = Depends(validate_pdf_upload)
):
        
    request_id = requestId or str(uuid.uuid4())
    temp_pdf_path = os.path.join(UPLOAD_DIR, f"{request_id}_{reportFile.filename}")

    try:
        start_total = time.time()

        logger.info(f"[{request_id}] Saving file: {reportFile.filename}")
        t0 = time.time()
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(reportFile.file, buffer)

        file_size = os.path.getsize(temp_pdf_path)
        if file_size > MAX_UPLOAD_SIZE:
            logger.error(f"[{request_id}] Fichier trop volumineux: {file_size}")
            
            return JSONResponse(status_code=400, content={"success": False, "error": "INVALID_REQUEST", "details": "The uploaded file is too large. Maximum allowed size is 50 MB."})
        logger.info(f"[{request_id}] File saved ({file_size // 1024} KB) in {time.time() - t0:.2f}s")

        t1 = time.time()
        logger.info(f"[{request_id}] Starting OCR processing...")
        
        try:
            ocr_result = process_entire_pdf(temp_pdf_path)
            # Safely unpack in case process_entire_pdf returns unexpectedly
            if isinstance(ocr_result, tuple) and len(ocr_result) == 2:
                full_ocr_text, date_depot = ocr_result
            else:
                logger.error(f"[{request_id}] process_entire_pdf returned unexpected type/length: {ocr_result}")
                
                return JSONResponse(status_code=422, content={"success": False, "error": "OCR_RESULT_INVALID", "details": "The document could not be read properly by the OCR service."})
        except Exception as e:
            logger.error(f"[{request_id}] Exception during OCR/Gemini processing: {e}")
            
            return JSONResponse(status_code=502, content={"success": False, "error": "OCR_PROCESSING_FAILED", "details": f"OCR extraction failed: {str(e)}"})
            
        logger.info(f"[{request_id}] OCR processing took {time.time() - t1:.2f}s")
        
        # Let Gemini evaluate if the document is irrelevant based on empty date_depot or missing info
        t2 = time.time()
        logger.info(f"[{request_id}] Starting LLM extraction...")
        
        try:
            final_response = process_pv(full_ocr_text, date_depot=date_depot, requestId=requestId)
        except Exception as e:
            logger.error(f"[{request_id}] Gemini extraction failed: {e}", exc_info=True)
            
            error_type = "LLM_JSON_PARSE_ERROR" if "JSON" in str(e) else "LLM_EXTRACTION_FAILED"
            return JSONResponse(status_code=422, content={"success": False, "error": error_type, "details": f"Failed to extract structured data: {str(e)}"})
            
        logger.info(f"[{request_id}] LLM extraction took {time.time() - t2:.2f}s")
        
        # Check if Gemini itself returned an Error block
        if "Success" in final_response and not final_response.get("Success"):
            logger.warning(f"[{request_id}] Gemini rejected the document: {final_response.get('Error')}")
            
            return JSONResponse(status_code=422, content={"success": False, "error": "DOCUMENT_NOT_RECOGNIZED", "details": final_response.get('Error', "Document does not appear to be a valid accident report.")})

        # If Gemini succeeded, it should have a 'Data' key. Extract the data or use it directly.
        data_payload = final_response.get("Data", final_response)

        logger.info(f"[{request_id}] Extraction successful. Total: {time.time() - start_total:.2f}s")
        
        return JSONResponse(status_code=200, content=data_payload)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"[{request_id}] Error: {str(e)}", exc_info=True)
        
        return JSONResponse(status_code=500, content={"success": False, "error": "INTERNAL_ERROR", "details": "An internal server error occurred."})

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
        "message": "PV Extraction API is active.",
    }


if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8080,
        log_level="info"  # Ensure uvicorn logs to console
    )