import os
import time
import logging
import concurrent.futures
from pdf2image import convert_from_path
from mistralai import Mistral
from mistralai.models import SDKError
from dotenv import load_dotenv
from app.core.utils import log_timing, calculate_gemini_cost, calculate_mistral_ocr_cost

logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")
client = Mistral(api_key=api_key)

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
        logger.info(f"File uploaded (ID: {file_id}). Requesting signed URL...")
        
        # Get signed URL with a polling loop in case of 404s (not ready) or 500s
        import time
        signed = None
        for _ in range(15):
            try:
                signed = client.files.get_signed_url(file_id=file_id)
                break
            except Exception as e:
                logger.warning(f"File not ready for URL yet ({e}). Retrying in 2s...")
                time.sleep(2)

        if not signed:
            raise Exception("Critical Error: Failed to get signed URL from Mistral after uploading.")

        doc_url = signed.url

        logger.info("Calling Mistral OCR on full PDF...")
        response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": doc_url
            },
            include_image_base64=False
        )
        ocr_stats = calculate_mistral_ocr_cost(response)
        logger.info(f"Mistral OCR: {ocr_stats['pages']} pages | Cost: ${ocr_stats['cost']:.6f}")
        return _merge_pages_markdown(response), ocr_stats['cost']
    finally:
        try:
            client.files.delete(file_id=file_id)
        except Exception as e:
            logger.warning(f"Could not delete temp file {file_id}: {e}")

def _extract_date_depot_gemini(pil_image):
    """Run stamp extraction by sending the first page to Gemini Vision."""
    logger.info("Sending Page 1 to Gemini for date de depot extraction...")
    
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")
    if not project or not location:
        logger.error("GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION not found. Skipping Gemini extraction.")
        return ""

    try:
        from google import genai
        gemini_client = genai.Client(vertexai=True, project=project, location=location)
    except ImportError:
        logger.error("google-genai package not found.")
        return ""

    prompt_str = (
        "Vous êtes un expert en lecture de tampons sur des rapports d'accidents (PV) tunisiens."
        "Votre SEUL ET UNIQUE but est de trouver la date d'arrivée estampillée (le tampon d'arrivée)."
        "Regardez cette première page de PV. Cherchez formellement le tampon (souvent rectangulaire) avec des mentions comme 'F. T. U. S. A', 'ARRIVEE', 'وصلت الإحالة' ou 'تاريخ الاستلام'."
        "Si vous trouvez ce tampon, extrayez UNIQUEMENT la date qui se trouve EXACTEMENT À L'INTÉRIEUR de ce tampon sous le format JJ/MM/AAAA (ex: 01/06/2021 pour 01 JUIN 2021)."
        "ATTENTION: Il y a d'autres dates sur la page (date de l'accident, date de rédaction manuscrite en haut à gauche/droite, etc.). Vous devez ABSOLUMENT les ignorer."
        "Seule la date incrustée explicitement dans le bloc du tampon nous intéresse."
        "S'il n'y a pas de tampon bien distinct, retournez une chaîne vide."
    )

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=[prompt_str, pil_image]
        )
        
        stats = calculate_gemini_cost(response)
        logger.info(f"Cost for this PV (Stamp Extraction): ${stats['total_cost_usd']:.6f} "
                    f"(Input: {stats['input_tokens']}, Output: {stats['output_tokens']})")
        
        date_depot = response.text.strip()
        logger.info(f"Gemini returned: {date_depot}")
        return date_depot, stats['total_cost_usd']
    except Exception as e:
        logger.error(f"Error calling Gemini: {e}")
        return "", 0.0

def _process_gemini_page1(pdf_path):
    logger.info("Loading page 1 for Gemini stamp extraction...")
    try:
        pages = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)
        if pages:
            pil_image = pages[0]
            # Try up to 3 times (1 initial + 2 retries)
            for attempt in range(3):
                if attempt > 0:
                    logger.info(f"Retrying Gemini stamp extraction (Attempt {attempt + 1}/3)...")
                
                result = _extract_date_depot_gemini(pil_image)
                # Handle cases where the tuple unpacking might fail if previous code returned scalar, 
                # but we updated it to return tuple
                if isinstance(result, tuple):
                    date_depot, cost = result
                else:
                    date_depot, cost = result, 0.0

                if date_depot:
                    return date_depot, cost
                    
            logger.info("All 3 attempts failed to extract date_depot. Returning None.")
    except Exception as e:
        logger.error(f"Error converting pdf or calling Gemini for page 1: {e}")
    
    return None, 0.0

@log_timing
def process_entire_pdf(pdf_path):
    """
    Hybrid: full PDF OCR for text using Mistral + stamp extraction on page 1 using Gemini VLM.
    Executes Mistral OCR and Gemini Vision concurrently to save time.
    """
    logger.info("Executing Mistral OCR and Gemini Vision concurrently...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_ocr = executor.submit(_ocr_full_pdf, pdf_path)
        future_gemini = executor.submit(_process_gemini_page1, pdf_path)
        
        full_text, m_cost = future_ocr.result()
        date_depot, g_cost = future_gemini.result()

        total_pv_cost = m_cost + g_cost
        logger.info(f"--- TOTAL PV PROCESSING COST: ${total_pv_cost:.6f} ---")
        
        return full_text, date_depot, total_pv_cost
        
        full_document_text = future_ocr.result()
        date_depot = future_gemini.result()

    return full_document_text, date_depot