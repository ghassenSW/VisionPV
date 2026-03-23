import os
import base64
import io
import time
import json
import logging
from functools import wraps
from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path
from mistralai import Mistral
from google import genai
from google.genai import types

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
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is missing from environment variables")
gemini_client = genai.Client(api_key=gemini_api_key)

api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")

client = Mistral(api_key=api_key)

@log_timing
def calculate_age_from_dates(birth_date, Date_du_PV):
    from datetime import datetime
    try:
        # Parse birth date
        if isinstance(birth_date, str):
            if '/' in birth_date:
                birth = datetime.strptime(birth_date, '%d/%m/%Y')
            elif '-' in birth_date:
                birth = datetime.strptime(birth_date, '%Y-%m-%d')
            else:
                return None
        else:
            return None
        
        # Parse accident date
        if isinstance(Date_du_PV, str):
            if '/' in Date_du_PV:
                accident = datetime.strptime(Date_du_PV, '%d/%m/%Y')
            elif '-' in Date_du_PV:
                accident = datetime.strptime(Date_du_PV, '%Y-%m-%d')
            else:
                return None
        else:
            return None
        
        birth_year = birth.year
        birth_month = birth.month
        birth_day = birth.day
        
        accident_year = accident.year
        accident_month = accident.month
        accident_day = accident.day
        age = accident_year - birth_year
        if accident_month < birth_month:
            age -= 1
        elif accident_month == birth_month and accident_day < birth_day:
            age -= 1
        
        return age
        
    except Exception as e:
        logger.error(f"Error calculating age: {e}")
        return None

@log_timing
def prepare_vision_image_pil(pdf_path):
    """Converts PDF Page 1 into a fast-process PIL Image for Gemini Vision."""
    logger.info("Etape 1 : Preparation de l'en-tete (Page 1)...")
    pages = convert_from_path(pdf_path, 200, first_page=1, last_page=1)
    img = pages[0]
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    width, height = img.size
    
    target_width = 700
    target_height = int(target_width * (height / width))
    
    if target_height > 1000:
        target_height = 800
        
    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return img

@log_timing
def run_vision_step(img_pil):
    """Vision Module using Gem2ni Flash (Optimisé pour Vision+JSON)"""
    logger.info("Etape 2 : Lancement de l'analyse Vision (Gemini 1.5 pro)...")
    prompt = """Tu es un expert en lecture de documents administratifs tunisiens. Analyse l'image de ce Procès-Verbal et extrais UNIQUEMENT les deux champs suivants dans un format JSON strict, sans aucun texte d'introduction ni de conclusion.
    Instructions d'extraction :
    Référence : Repère la mention MANUSCRITE (écrite à la main) qui suit le motif visuel de chiffres séparés par des étoiles (exemple : 03*06*2021) (sans espace). Tu dois extraire la valeur exacte en conservant impérativement les étoiles * et les chiffres. Ne confonds pas cette valeur avec les numéros de PV imprimés ou les numéros de page.
    Date_Depot : Localise l'ancre textuelle 'F.T.U.S.A.' et le mot 'ARRIVEE' figurant dans un tampon rectangulaire.
    Extrais la date figurant dans ce tampon (ex: '01 JUIN 2021').
    Convertis impérativement cette date au format numérique JJ/MM/AAAA (ex: '01/06/2021').
    
    Réponds UNIQUEMENT avec l'objet JSON :
    { "Référence": "...", "Date_Depot": "..." }"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_pil],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        vision_output = response.text
        logger.info("Analyse Vision (En-tete) reussie.")
        return json.loads(vision_output)
    except Exception as e:
        logger.error(f"Erreur lors de l'appel Vision Gemini : {str(e)}")
        return None

@log_timing
def run_text_step(truncated_text, ref_ftusa, date_depot):
    """Text Module: Logic-heavy narrative analysis using Mistral Large 3"""
    import os
    
    # Read the prompt from the external text file
    prompt_path = os.path.join(os.path.dirname(__file__), "mistral_prompt.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # Format the prompt with the dynamic variables
    prompt = prompt_template.format(
        ref_ftusa=ref_ftusa,
        date_depot=date_depot,
        truncated_text=truncated_text
    )

    logger.info("Appel Mistral Large 3 (Analyse du texte narratif)...")
    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )
    return json.loads(response.choices[0].message.content)

@log_timing
def process_pv(ocr_text, pdf_path):
    """Processes a single PV by combining Vision and Text extraction."""
    # 1. Start with Vision (with error handling)
    ref_ftusa = ""
    date_depot = ""
    
    try:
        logger.info("Tentative d'extraction avec Vision (Aplatissement en Capture d'ecran)...")
        img_pil = prepare_vision_image_pil(pdf_path)
        
        logger.info("Analyse Vision...")
        data = run_vision_step(img_pil)
        
        ref_ftusa = data.get("Référence", "") if data else ""
        date_depot = data.get("Date_Depot", "") if data else ""
            
        logger.info(f"Vision OK: Reference={ref_ftusa}, Date_Depot={date_depot}")
    except Exception as vision_error:
        logger.warning(f"Erreur Vision (non-bloquante): {vision_error}")
        logger.info("Passage direct a l'etape LLM avec champs Vision vides...")
        ref_ftusa = ""
        date_depot = ""
    
    # 2. Quota Safety Gap
    if ref_ftusa or date_depot:
        logger.info("Pause finale de synchronisation API (15s)...")
        time.sleep(15)

    # 3. Process Text with Large 3
    # Inject Vision results into the Text prompt
    data_final = run_text_step(
        ocr_text, 
        ref_ftusa, 
        date_depot
    )

    # 4. Final Verification: Ensure Vision data is in the final JSON
    data_final["Référence FTUSA"] = ref_ftusa
    data_final["Date du dépôt du PV"] = date_depot
    
    if not ref_ftusa:
        logger.warning("Reference FTUSA est vide (vision step echouee)")
    if not date_depot:
        logger.warning("Date du depot du PV est vide (vision step echouee)")
    
    # 5. Calculate ages from birth dates if needed
    Date_du_PV = data_final.get("Date du PV", "").strip()
    logger.info("Calcul des ages des victimes...")
    
    for i in range(1, 11):  # Check up to 10 victims
        age_key = f"Age victime {i}"
        birth_key = f"Date naissance victime {i}"
        
        # If birth date exists
        if birth_key in data_final and data_final[birth_key]:
            birth_date = str(data_final[birth_key]).strip()
            current_age = data_final.get(age_key, 0)
            
            # Convert empty string or None to 0
            if current_age == "" or current_age is None:
                current_age = 0
            
            # Calculate age if not already present or is 0
            if not current_age or current_age == 0:
                if birth_date and Date_du_PV:
                    calculated_age = calculate_age_from_dates(birth_date, Date_du_PV)
                    if calculated_age is not None:
                        data_final[age_key] = calculated_age
                        logger.info(f"Victime {i}: Age calcule = {calculated_age} ans (ne le {birth_date})")
                    else:
                        logger.warning(f"Victime {i}: Erreur de calcul d'age (dates invalides)")
                else:
                    logger.info(f"Victime {i}: Donnees manquantes pour calcul d'age")
            else:
                logger.info(f"Victime {i}: Age deja present = {current_age} ans")
                
            # Remove birth date from final output
            if birth_key in data_final:
                del data_final[birth_key]
            
    return data_final