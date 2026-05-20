import os
import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter, before_sleep_log
from app.core.utils import log_timing, calculate_gemini_cost
from app.core.prompt import PROMPT_TEMPLATE
from sqlalchemy.orm import Session
from app.db.database import engine
from app.db.models import (
    Governorate, Region, InsuranceCompany, ClaimReason,
    DeathMedicalCause, HealthInstitution, NavGuardHq,
    PoliceHq, SocialState, VehicleType
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load hierarchical regions from the database (Governorate -> Region)
REGIONS_BY_GOV = {}
ALL_JSON_REGIONS = []
CLAIM_REASON_LIST = []
DEATH_MEDICAL_CAUSE_LIST = []
INSURANCE_LIST = []
POLICE_HQ_LIST = []
NAV_GUARD_HQ_LIST = []
GOUVERNORAT_LIST = []
SOCIAL_STATE_LIST = []
VEHICLE_TYPE_LIST = []
HEALTH_INSTITUTION_LIST = []


def refresh_reference_lists():
    """Reload all reference lists from PostgreSQL so updates are reflected immediately."""
    global REGIONS_BY_GOV, ALL_JSON_REGIONS
    global CLAIM_REASON_LIST, DEATH_MEDICAL_CAUSE_LIST, INSURANCE_LIST
    global POLICE_HQ_LIST, NAV_GUARD_HQ_LIST, GOUVERNORAT_LIST
    global SOCIAL_STATE_LIST, VEHICLE_TYPE_LIST, HEALTH_INSTITUTION_LIST

    try:
        with Session(engine) as db:
            govs = db.query(Governorate).order_by(Governorate.name).all()
            REGIONS_BY_GOV = {}
            for gov in govs:
                regions = [r.name for r in db.query(Region).filter(Region.governorate_id == gov.id).order_by(Region.name).all()]
                REGIONS_BY_GOV[gov.name] = regions
            ALL_JSON_REGIONS = [region for regions in REGIONS_BY_GOV.values() for region in regions]

            CLAIM_REASON_LIST = [r.name for r in db.query(ClaimReason).order_by(ClaimReason.name).all()]
            DEATH_MEDICAL_CAUSE_LIST = [r.name for r in db.query(DeathMedicalCause).order_by(DeathMedicalCause.name).all()]
            INSURANCE_LIST = [r.name for r in db.query(InsuranceCompany).order_by(InsuranceCompany.name).all()]
            POLICE_HQ_LIST = [r.name for r in db.query(PoliceHq).order_by(PoliceHq.name).all()]
            NAV_GUARD_HQ_LIST = [r.name for r in db.query(NavGuardHq).order_by(NavGuardHq.name).all()]
            GOUVERNORAT_LIST = [r.name for r in db.query(Governorate).order_by(Governorate.name).all()]
            SOCIAL_STATE_LIST = [r.name for r in db.query(SocialState).order_by(SocialState.name).all()]
            VEHICLE_TYPE_LIST = [r.name for r in db.query(VehicleType).order_by(VehicleType.name).all()]
            HEALTH_INSTITUTION_LIST = [r.name for r in db.query(HealthInstitution).order_by(HealthInstitution.name).all()]

        logger.info(f"✅ Refreshed DB reference lists: {len(REGIONS_BY_GOV)} governorates")
    except Exception as e:
        logger.error(f"Error refreshing DB reference lists: {e}")


refresh_reference_lists()

# 2. Load Models by Manufacturer (from hierarchical JSON)
# Vehicle models/manufacturers remain file-backed for now (unused in strict mode)
MODELS_BY_MAKER = {}


# Force load the .env from the project root
env_path = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(env_path)

# Ensure the credentials path is absolute based on the project root
creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if creds_path and not os.path.isabs(creds_path):
    # Use forward slashes for cross-platform compatibility (works in Docker)
    creds_full_path = os.path.join(PROJECT_ROOT, creds_path)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_full_path.replace("\\", "/")

# --- CONFIGURATION ---
project = os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("GOOGLE_CLOUD_LOCATION")
if not project or not location:
    raise ValueError("GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION is missing from environment variables")

client = genai.Client(vertexai=True, project=project, location=location)

# Load simple reference lists from the database
def _fetch_names(model):
    try:
        with Session(engine) as db:
            return [r.name for r in db.query(model).order_by(model.name).all()]
    except Exception as e:
        logger.error(f"Error fetching {model}: {e}")
        return []


def _get_claim_reasons_block():
    claim_reasons = _fetch_names(ClaimReason)
    if not claim_reasons:
        logger.warning("No claim reasons found in database for prompt injection.")
        return '    "Non mentionné / Non déterminé"'

    return "\n".join(f'    "{reason}",' for reason in claim_reasons)


def _get_insurance_block():
    """Return a multiline quoted list of insurance names for prompt injection."""
    insurances = _fetch_names(InsuranceCompany)
    if not insurances:
        logger.warning("No insurance companies found in database for prompt injection.")
        return '    "Inconnue"'

    return "\n".join(f'    "{name}",' for name in insurances)


def _get_vehicle_types_block():
    """Return a single-line Python-style list of vehicle type names for the prompt."""
    types = _fetch_names(VehicleType)
    if not types:
        logger.warning("No vehicle types found in database for prompt injection.")
        return "    ['voiture']"

    # Produce a compact bracketed list literal indented to match prompt formatting
    joined = ', '.join(f"'{t}'" for t in types)
    return f"    [{joined}]"


def _get_death_medical_cause_block():
    """Return a multiline quoted list of death medical causes for prompt injection."""
    causes = _fetch_names(DeathMedicalCause)
    if not causes:
        logger.warning("No death medical causes found in database for prompt injection.")
        return '    "Suite à l’accident",\n    "Non déterminé",\n    "Autre"'

    return "\n".join(f'    "{c}",' for c in causes)


def _get_social_state_block():
    """Return a bracketed Python-style list literal for social state / profession names."""
    states = _fetch_names(SocialState)
    if not states:
        logger.warning("No social states found in database for prompt injection.")
        return "    ['Retraité', 'Sans emploi', 'Profession libérale', 'Agent d\'exécution', 'Enseignant universitaire', 'Pétanqueur professionnel', 'Pétanqueur', 'Médecin expert - laboratoire', 'Médecin expert', 'Médecin expert judiciaire', 'Médecin expert assurance', 'Fonctionnaire Public']"

    joined = ', '.join(f"'{s}'" for s in states)
    return f"    [{joined}]"

CLAIM_REASON_LIST = _fetch_names(ClaimReason)
DEATH_MEDICAL_CAUSE_LIST = _fetch_names(DeathMedicalCause)
INSURANCE_LIST = _fetch_names(InsuranceCompany)
POLICE_HQ_LIST = _fetch_names(PoliceHq)
NAV_GUARD_HQ_LIST = _fetch_names(NavGuardHq)
GOUVERNORAT_LIST = _fetch_names(Governorate)
SOCIAL_STATE_LIST = _fetch_names(SocialState)
VEHICLE_TYPE_LIST = _fetch_names(VehicleType)
HEALTH_INSTITUTION_LIST = _fetch_names(HealthInstitution)


def _normalize_assert_key(value):
    text = re.sub(r"\s+", " ", str(value).strip())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return text.casefold()


def assert_value_in_list(value, valid_list, field_name):
    """Return the canonical list value if present, otherwise None.

    This is a strict validation gate: list-backed fields are allowed to survive
    only when their extracted value resolves to an official value from the list.
    """
    if value is None:
        return None

    if isinstance(value, list):
        validated_values = []
        for item in value:
            validated_item = assert_value_in_list(item, valid_list, field_name)
            if validated_item is not None:
                validated_values.append(validated_item)
            else:
                logger.warning(f"{field_name}: dropped value outside allowed list: {item!r}")
        return validated_values

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate or candidate.lower() in {"null", "none", "n/a"}:
            return None
        normalized_candidate = _normalize_assert_key(candidate)
    else:
        normalized_candidate = _normalize_assert_key(value)

    for allowed_value in valid_list:
        if normalized_candidate == _normalize_assert_key(allowed_value):
            if value != allowed_value:
                logger.info(f"{field_name}: canonicalized {value!r} -> {allowed_value!r}")
            return allowed_value

    logger.warning(f"{field_name}: value outside allowed list -> {value!r}")
    return None


def assert_list_backed_fields(payload):
    """Enforce that every list-backed field resolves to an allowed value or None."""
    payload["governorate"] = assert_value_in_list(payload.get("governorate"), GOUVERNORAT_LIST, "governorate")
    payload["region"] = assert_value_in_list(payload.get("region"), ALL_JSON_REGIONS, "region")
    payload["nationalGuardHQ"] = assert_value_in_list(payload.get("nationalGuardHQ"), NAV_GUARD_HQ_LIST, "nationalGuardHQ")
    payload["policeHQ"] = assert_value_in_list(payload.get("policeHQ"), POLICE_HQ_LIST, "policeHQ")
    payload["claimReasons"] = assert_value_in_list(payload.get("claimReasons"), CLAIM_REASON_LIST, "claimReasons")

    if isinstance(payload.get("vehicles"), list):
        for vehicle in payload["vehicles"]:
            if not isinstance(vehicle, dict):
                continue
            vehicle["type"] = assert_value_in_list(vehicle.get("type"), VEHICLE_TYPE_LIST, "vehicles.type")
            vehicle["insurance"] = assert_value_in_list(vehicle.get("insurance"), INSURANCE_LIST, "vehicles.insurance")
            # vehicle["model"] = assert_value_in_list(vehicle.get("model"), VEHICLE_MODEL_LIST, "vehicles.model")
            # vehicle["manufacturer"] = assert_value_in_list(vehicle.get("manufacturer"), VEHICLE_MANUFACTURER_LIST, "vehicles.manufacturer")

    if isinstance(payload.get("victims"), list):
        for victim in payload["victims"]:
            if not isinstance(victim, dict):
                continue
            victim["gender"] = assert_value_in_list(victim.get("gender"), ["MALE", "FEMALE"], "victims.gender")
            victim["casualtyType"] = assert_value_in_list(victim.get("casualtyType"), ["INJURY", "DEATH"], "victims.casualtyType")
            victim["casualtyCategory"] = assert_value_in_list(victim.get("casualtyCategory"), ["DRIVER", "PASSENGER", "PEDESTRIAN"], "victims.casualtyCategory")
            victim["deathGovernorate"] = assert_value_in_list(victim.get("deathGovernorate"), GOUVERNORAT_LIST, "victims.deathGovernorate")
            victim["deathMedicalCause"] = assert_value_in_list(victim.get("deathMedicalCause"), DEATH_MEDICAL_CAUSE_LIST, "victims.deathMedicalCause")
            victim["profession"] = assert_value_in_list(victim.get("profession"), SOCIAL_STATE_LIST, "victims.profession")

    return payload

def get_best_fuzzy_match(extracted_str, valid_list, threshold=0.7, log_prefix="match", force_valid_list=False):
    if not extracted_str or not valid_list:
        return None if force_valid_list else extracted_str

    best_match = None
    highest_ratio = 0.0
    extracted_lower = str(extracted_str).lower()

    for item in valid_list:
        ratio = SequenceMatcher(None, extracted_lower, item.lower()).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = item
            if ratio == 1.0:  # Perfect match, no need to keep checking
                break

    # STRICT ENFORCEMENT: No soft thresholds, no fallbacks to original text
    if best_match is None:
        logger.warning(f"No {log_prefix} candidates found in valid list for '{extracted_str}'")
        return None

    if highest_ratio >= threshold:
        logger.info(f"Fuzzy {log_prefix}: '{extracted_str}' -> '{best_match}' (score: {highest_ratio:.2f}) [ACCEPTED ✓]")
        return best_match
    else:
        logger.warning(f"Fuzzy {log_prefix}: '{extracted_str}' -> None (score: {highest_ratio:.2f} < threshold: {threshold}) [REJECTED → NULL]")
        return None

def get_smart_fuzzy_match(query, default_list, mapping_dict=None, parent_value=None, threshold=0.7, force_valid_list=True):
    if not query:
        return None

    search_list = default_list

    # If we have a parent (e.g., manufacturer like "TOYOTA") and it exists in our mapping
    if mapping_dict and parent_value and parent_value in mapping_dict:
        # Get the specific sublist for this parent (e.g., models for TOYOTA)
        search_list = mapping_dict.get(parent_value, default_list)
        logger.info(f"Using parent-specific list for '{parent_value}': {len(search_list)} models available")
    else:
        if parent_value and mapping_dict:
            logger.info(f"Parent '{parent_value}' not found in mapping. Using default list of {len(default_list)} items.")

    # Perform fuzzy match with strict validation (enforces null-or-valid-list contract)
    return get_best_fuzzy_match(query, search_list, threshold, force_valid_list=force_valid_list)


def get_best_delegation_match(extracted_delegation, threshold=0.7):
    return get_best_fuzzy_match(extracted_delegation, ALL_JSON_REGIONS, threshold, "delegation")


def normalize_date_to_iso(date_str):
    """Normalize various date formats to YYYY-MM-DD format."""
    if not date_str or date_str is None:
        return None

    date_str = str(date_str).strip()
    if not date_str or date_str.lower() in ('null', '', 'n/a', 'none'):
        return None

    # Try common date formats
    formats_to_try = [
        '%Y-%m-%d',      # Already ISO format
        '%d/%m/%Y',      # DD/MM/YYYY (common European)
        '%d-%m-%Y',      # DD-MM-YYYY
        '%d/%m/%y',      # DD/MM/YY
        '%m/%d/%Y',      # MM/DD/YYYY (American)
        '%Y/%m/%d',      # YYYY/MM/DD
        '%d.%m.%Y',      # DD.MM.YYYY (German style)
    ]

    for fmt in formats_to_try:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {date_str}. Returning as-is.")
    return date_str


def _date_depot_instruction(date_depot):
    if date_depot:
        return f'Valeur DÉFINITIVE extraite du tampon par le modèle Vision : "{date_depot}". Recopiez-la MOT À MOT dans le JSON.'
    return 'Laissez ce champ vide (""). Ne tentez pas de chercher la date de dépôt dans le texte.'


def _is_resource_exhausted(exc):
    return isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429


@log_timing
@retry(
    retry=retry_if_exception(_is_resource_exhausted),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def run_text_step(truncated_text, date_depot="", requestId=""):
    """Text extraction using Gemini: OCR text -> structured JSON."""
    prompt = PROMPT_TEMPLATE.format(
        date_depot_instruction=_date_depot_instruction(date_depot),
        requestId=requestId if requestId else "N/A",
        truncated_text=truncated_text,
        claim_reasons_block=_get_claim_reasons_block(),
        insurance_list_block=_get_insurance_block(),
        vehicle_types_block=_get_vehicle_types_block(),
        death_medical_cause_block=_get_death_medical_cause_block(),
        social_state_block=_get_social_state_block()
    )

    logger.info("Calling Gemini (Narrative text analysis)...")

    response = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "temperature": 0
        }
    )

    stats = calculate_gemini_cost(response)
    logger.info(f"Cost for this PV (Text Extraction): ${stats['total_cost_usd']:.6f} "
                f"(Input: {stats['input_tokens']}, Output: {stats['output_tokens']})")

    raw_content = response.text
    try:
        return json.loads(raw_content), stats['total_cost_usd']
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned malformed JSON: {e}")
        logger.error(f"Raw response (first 500 chars): {raw_content[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e


@log_timing
def process_pv(ocr_text, date_depot='', requestId=""):
    refresh_reference_lists()
    payload, llm_cost = run_text_step(ocr_text, date_depot=date_depot, requestId=requestId)

    # Prepend requestId to the final payload
    if requestId:
        final_payload = {"requestId": requestId}
    else:
        final_payload = {}

    final_payload.update(payload)
    payload = final_payload

    # Always include submissionDate key. If date_depot is None (not found after retries),
    # this will serialize to JSON null which is the desired fallback behavior.
    payload['submissionDate'] = date_depot

    # Apply fuzzy matching to relevant fields
    if payload.get("governorate"):
        payload["governorate"] = get_best_fuzzy_match(payload["governorate"], GOUVERNORAT_LIST, 0.80, "governorate", force_valid_list=True)
    if payload.get("region"):
        if payload.get("governorate") and payload["governorate"] in REGIONS_BY_GOV:
            payload["region"] = get_best_fuzzy_match(
                payload["region"],
                REGIONS_BY_GOV[payload["governorate"]],
                0.70,
                "region",
                force_valid_list=True
            )
        else:
            logger.warning(f"Region '{payload['region']}' dropped because no valid governorate was found to scope the fuzzy match.")
            payload["region"] = None

    accident_time = payload.get("accidentTime")
    if isinstance(accident_time, str) and accident_time.strip():
        match = re.search(r"(\d{1,2})\s*[:hH]\s*(\d{1,2})(?:\s*[:hH]\s*(\d{1,2}))?", accident_time)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3) or 0)
            payload["accidentTime"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Apply fuzzy matching to HQ names based on type
    reasoning_poste_type = payload.get("_reasoning_Poste_Type")
    national_guard_hq = payload.get("nationalGuardHQ")
    police_hq = payload.get("policeHQ")

    # Apply fuzzy matching to HQ names
    if national_guard_hq:
        national_guard_hq = get_best_fuzzy_match(national_guard_hq, NAV_GUARD_HQ_LIST, 0.8, "nationalGuardHQ", force_valid_list=True)
    if police_hq:
        police_hq = get_best_fuzzy_match(police_hq, POLICE_HQ_LIST, 0.8, "policeHQ", force_valid_list=True)

    if reasoning_poste_type == "Garde Nationale":
        if not national_guard_hq and police_hq:
            national_guard_hq = police_hq
        police_hq = None
    elif reasoning_poste_type == "Poste de Police":
        if not police_hq and national_guard_hq:
            police_hq = national_guard_hq
        national_guard_hq = None
    else:
        if national_guard_hq and police_hq:
            police_hq = None
        elif national_guard_hq and not police_hq:
            police_hq = None
        elif police_hq and not national_guard_hq:
            national_guard_hq = None

    payload["nationalGuardHQ"] = national_guard_hq
    payload["policeHQ"] = police_hq

    # Apply fuzzy matching to vehicle model and manufacturer
    # if payload.get("vehicles") and isinstance(payload["vehicles"], list):
    #     for vehicle in payload["vehicles"]:
    #         if isinstance(vehicle, dict):
    #             # Fuzzy match manufacturer (normalize to UPPERCASE first)
    #             if vehicle.get("manufacturer"):
    #                 mfg = vehicle["manufacturer"].upper().strip()
    #                 vehicle["manufacturer"] = get_best_fuzzy_match(mfg, VEHICLE_MANUFACTURER_LIST, 0.75, "vehicle_manufacturer", force_valid_list=True)
    #
    #             # Fuzzy match model against manufacturer-specific sublist (FORCED to be from VEHICLE_MODEL_LIST)
    #             if vehicle.get("model"):
    #                 vehicle["model"] = get_smart_fuzzy_match(
    #                     query=vehicle["model"],
    #                     default_list=VEHICLE_MODEL_LIST,
    #                     mapping_dict=MODELS_BY_MAKER,
    #                     parent_value=vehicle.get("manufacturer"),
    #                     threshold=0.70,
    #                     force_valid_list=True  # CRITICAL: Ensures model is ALWAYS from VEHICLE_MODEL_LIST
    #                 )
    # Normalize all date fields to YYYY-MM-DD format
    date_fields = ['submissionDate', 'reportDate', 'accidentDate']
    for field in date_fields:
        if payload.get(field):
            payload[field] = normalize_date_to_iso(payload[field])

    # Normalize dates in victims array and apply fuzzy matching to victim fields
    if payload.get("victims") and isinstance(payload["victims"], list):
        for victim in payload["victims"]:
            if isinstance(victim, dict):
                # Normalize dates
                if victim.get("birthDate"):
                    victim["birthDate"] = normalize_date_to_iso(victim["birthDate"])
                if victim.get("deathDate"):
                    victim["deathDate"] = normalize_date_to_iso(victim["deathDate"])

                # Fuzzy match deathGovernorate
                if victim.get("deathGovernorate"):
                    victim["deathGovernorate"] = get_best_fuzzy_match(victim["deathGovernorate"], GOUVERNORAT_LIST, 0.85, "deathGovernorate", force_valid_list=True)

                # Fuzzy match healthInstitution
                if victim.get("healthInstitution"):
                    victim["healthInstitution"] = get_best_fuzzy_match(victim["healthInstitution"], HEALTH_INSTITUTION_LIST, 0.60, "healthInstitution", force_valid_list=True)

    # Final assertion pass: every list-backed field must resolve to an allowed value or None.
    payload = assert_list_backed_fields(payload)

    # Remove all reasoning fields before returning
    for field in ('_reasoning_contexte', '_reasoning_causes', '_reasoning_lieu', '_reasoning_vehicules', '_reasoning_victimes', '_reasoning_Poste_Type', '_reasoning_Total_decedes', '_reasoning_Total_blesses'):
        payload.pop(field, None)

    return payload, llm_cost
