import os
import json
import logging
from difflib import SequenceMatcher
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

# Import hardcoded regions and headquarters for fuzzy matching
from FTUSA_names import REGION_LIST, POLICE_HQ_LIST, NAV_GUARD_HQ_LIST, GOUVERNORAT_LIST

# Limit LLM input size (chars). Override with PV_MAX_OCR_CHARS.
_DEFAULT_MAX_OCR_CHARS = 100_000
# Cap generation length for structured JSON (sufficient for long PVs).
_LLM_MAX_TOKENS = 12_288
# Extraction model default: Mistral Small (faster than Large). Override with PV_LLM_MODEL.
# Docs use versioned ids too, e.g. mistral-small-2506 (Small 3.2), Mistral Small 4 (v26.03).
# Rolling alias (same pattern as mistral-large-latest): https://docs.mistral.ai/getting-started/models
_DEFAULT_LLM_MODEL = "mistral-small-latest"


def _llm_model_name() -> str:
    return (os.getenv("PV_LLM_MODEL") or _DEFAULT_LLM_MODEL).strip() or _DEFAULT_LLM_MODEL


def _max_ocr_chars():
    raw = os.getenv("PV_MAX_OCR_CHARS", str(_DEFAULT_MAX_OCR_CHARS))
    try:
        return max(10_000, int(raw))
    except ValueError:
        return _DEFAULT_MAX_OCR_CHARS


def _truncate_ocr_for_llm(text: str) -> str:
    """Reduce prompt size: keep the beginning (admin + facts) and a tail slice for long OCR."""
    max_chars = _max_ocr_chars()
    if not text or len(text) <= max_chars:
        return text
    tail_keep = min(15_000, max_chars // 5)
    head_keep = max_chars - tail_keep - 120
    if head_keep < 5000:
        logger.warning("OCR truncated to %d characters (single block)", max_chars)
        return text[:max_chars]
    sep = "\n\n[... OCR intermédiaire omis (limite de contexte) ...]\n\n"
    logger.warning(
        "OCR truncated from %d to ~%d characters (tête + fin)",
        len(text),
        head_keep + tail_keep + len(sep),
    )
    return text[:head_keep] + sep + text[-tail_keep:]

def get_best_fuzzy_match(extracted_str, valid_list, threshold=0.7, log_prefix="match"):
    if not extracted_str or not valid_list:
        return extracted_str
    
    best_match = extracted_str
    highest_ratio = 0.0
    extracted_lower = str(extracted_str).lower()
    
    for item in valid_list:
        ratio = SequenceMatcher(None, extracted_lower, item.lower()).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = item
            if ratio == 1.0:  # Perfect match, no need to keep checking
                break
            
    if highest_ratio >= threshold:
        logger.info(f"Fuzzy {log_prefix}: '{extracted_str}' -> '{best_match}' (score: {highest_ratio:.2f})")
        return best_match
        
    logger.info(f"No {log_prefix} fuzzy match found for '{extracted_str}' (best score: {highest_ratio:.2f})")
    return extracted_str

def get_best_delegation_match(extracted_delegation, threshold=0.7):
    return get_best_fuzzy_match(extracted_delegation, REGION_LIST, threshold, "delegation")


def calculate_age_from_dates(birth_date, date_du_pv):
    if not isinstance(birth_date, str) or not isinstance(date_du_pv, str):
        return None

    def parse_date(date_str):
        if '/' in date_str:
            return datetime.strptime(date_str, '%d/%m/%Y')
        if '-' in date_str:
            return datetime.strptime(date_str, '%Y-%m-%d')
        return None

    try:
        birth = parse_date(birth_date)
        accident = parse_date(date_du_pv)

        if not birth or not accident:
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
    """Structured JSON extraction from OCR text (Mistral chat; model from PV_LLM_MODEL)."""
    truncated_text = _truncate_ocr_for_llm(truncated_text)
    model = _llm_model_name()
    prompt = PROMPT_TEMPLATE.format(
        ref_ftusa_instruction=_ref_instruction(ref_ftusa),
        date_depot_instruction=_date_depot_instruction(date_depot),
        truncated_text=truncated_text
    )

    logger.info("Appel Mistral LLM model=%s (extraction structurée)...", model)
    response = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=_LLM_MAX_TOKENS,
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

    # Apply fuzzy matching to Délégation / Nom du poste
    extracted_delegation = data_final["pv_info"].get("Délégation", "")
    if extracted_delegation:
        best_delegation = get_best_delegation_match(extracted_delegation, threshold=0.7)
        data_final["pv_info"]["Délégation"] = best_delegation

    extracted_poste_type = data_final["pv_info"].get("Poste de Police / Garde Nationale", "")
    extracted_nom_poste = data_final["pv_info"].get("Nom du poste", "")
    
    if extracted_nom_poste:
        if extracted_poste_type.lower().strip() == "poste de police":
            best_nom_poste = get_best_fuzzy_match(extracted_nom_poste, POLICE_HQ_LIST, threshold=0.7, log_prefix="nom_poste_police")
            data_final["pv_info"]["Nom du poste"] = best_nom_poste
        elif extracted_poste_type.lower().strip() == "garde nationale":
            best_nom_poste = get_best_fuzzy_match(extracted_nom_poste, NAV_GUARD_HQ_LIST, threshold=0.7, log_prefix="nom_poste_garde")
            data_final["pv_info"]["Nom du poste"] = best_nom_poste
        else:
            # If the type is empty or incorrect, fallback to delegation logic or leave it as is
            pass

    # Apply fuzzy matching to Gouvernorat
    extracted_gov = data_final["pv_info"].get("Gouvernorat", "")
    if extracted_gov:
        best_gov = get_best_fuzzy_match(extracted_gov, GOUVERNORAT_LIST, threshold=0.7, log_prefix="gouvernorat")
        data_final["pv_info"]["Gouvernorat"] = best_gov

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
