import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from mistralai import Mistral
from utils import log_timing
from prompt import PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY is missing from environment variables")

client = Mistral(api_key=api_key)


def calculate_age_from_dates(birth_date, date_du_pv):
    try:
        if isinstance(birth_date, str):
            if '/' in birth_date:
                birth = datetime.strptime(birth_date, '%d/%m/%Y')
            elif '-' in birth_date:
                birth = datetime.strptime(birth_date, '%Y-%m-%d')
            else:
                return None
        else:
            return None

        if isinstance(date_du_pv, str):
            if '/' in date_du_pv:
                accident = datetime.strptime(date_du_pv, '%d/%m/%Y')
            elif '-' in date_du_pv:
                accident = datetime.strptime(date_du_pv, '%Y-%m-%d')
            else:
                return None
        else:
            return None

        age = accident.year - birth.year
        if (accident.month, accident.day) < (birth.month, birth.day):
            age -= 1

        return age

    except Exception as e:
        logger.error(f"Error calculating age: {e}")
        return None


def _ref_instruction(ref_ftusa):
    if ref_ftusa:
        return f'Valeur DÉFINITIVE extraite du tampon : "{ref_ftusa}". Recopiez-la MOT À MOT dans le JSON.'
    return 'Repérez la mention chiffres*étoiles (ex: 03*06*2021). Extraire du texte OCR. Si introuvable : "".'

def _date_depot_instruction(date_depot):
    if date_depot:
        return f'Valeur DÉFINITIVE extraite du tampon : "{date_depot}". Recopiez-la MOT À MOT dans le JSON.'
    return 'Cherchez le tampon F.T.U.S.A./ARRIVEE, ou وصلت الإحالة/تاريخ الاستلام près d\'une date. Format JJ/MM/AAAA. Si absent : "".'


@log_timing
def run_text_step(truncated_text, ref_ftusa="", date_depot=""):
    """Text extraction using Mistral Large: OCR text -> structured JSON."""
    prompt = PROMPT_TEMPLATE.format(
        ref_ftusa_instruction=_ref_instruction(ref_ftusa),
        date_depot_instruction=_date_depot_instruction(date_depot),
        truncated_text=truncated_text
    )

    logger.info("Appel Mistral Large (Analyse du texte narratif)...")
    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )

    raw_content = response.choices[0].message.content
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.error(f"Mistral returned malformed JSON: {e}")
        logger.error(f"Raw response (first 500 chars): {raw_content[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e


@log_timing
def process_pv(ocr_text, ref_ftusa="", date_depot=""):
    """Processes a single PV via Mistral text extraction and post-processing."""
    # 1. Extract structured data from OCR text
    data_final = run_text_step(ocr_text, ref_ftusa=ref_ftusa, date_depot=date_depot)

    # Make sure 'pv_info' exists to avoid KeyErrors
    if "pv_info" not in data_final:
        data_final["pv_info"] = {}

    # 2. Override with bbox-extracted values when we have them (vision on stamp image)
    if ref_ftusa:
        data_final["pv_info"]["Référence FTUSA"] = ref_ftusa
    if date_depot:
        data_final["pv_info"]["Date du dépôt du PV"] = date_depot

    extracted_ref = data_final["pv_info"].get("Référence FTUSA", "")
    extracted_date = data_final["pv_info"].get("Date du dépôt du PV", "")

    if not extracted_ref:
        logger.warning("Référence FTUSA est vide")
    if not extracted_date:
        logger.warning("Date du dépôt du PV est vide")

    # 3. Calculate ages from birth dates for nested victims list
    date_du_pv = data_final["pv_info"].get("Date du PV", "").strip()
    logger.info("Calcul des ages des victimes...")

    if "victimes" in data_final and isinstance(data_final["victimes"], list):
        for i, victime in enumerate(data_final["victimes"]):
            birth_date = str(victime.get("Date naissance", "")).strip()
            current_age = victime.get("Age", 0)

            if current_age == "" or current_age is None:
                current_age = 0

            if not current_age or current_age == 0:
                if birth_date and date_du_pv:
                    calculated_age = calculate_age_from_dates(birth_date, date_du_pv)
                    if calculated_age is not None:
                        victime["Age"] = calculated_age
                        logger.info(f"Victime {i+1}: Age calcule = {calculated_age} ans (ne le {birth_date})")
                    else:
                        logger.warning(f"Victime {i+1}: Erreur de calcul d'age (dates invalides)")
                else:
                    logger.info(f"Victime {i+1}: Donnees manquantes pour calcul d'age")
            else:
                logger.info(f"Victime {i+1}: Age deja present = {current_age} ans")

            # Remove the 'Date naissance' from the final output
            victime.pop("Date naissance", None)

    # 4. Remove chain-of-thought reasoning fields
    for field in ("_reasoning_contexte", "_reasoning_causes", "_reasoning_lieu", "_reasoning_vehicules", "_reasoning_victimes"):
        data_final.pop(field, None)

    return data_final
