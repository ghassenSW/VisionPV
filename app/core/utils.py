import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def log_timing(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        logger.info(f"{func.__name__} took {time.time() - start:.2f} seconds")
        return result
    return wrapper

def calculate_gemini_cost(response):
    """
    Calculates cost for Gemini 3.1 Flash based on token usage.
    Rates: $0.25 per 1M input tokens, $0.30 per 1M output tokens.
    """
    INPUT_RATE = 0.25 / 1_000_000
    OUTPUT_RATE = 0.30 / 1_000_000
    
    try:
        usage = response.usage_metadata
        if not usage:
            return {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}
            
        in_tokens = getattr(usage, "prompt_token_count", 0)
        out_tokens = getattr(usage, "candidates_token_count", 0)
        
        cost = (in_tokens * INPUT_RATE) + (out_tokens * OUTPUT_RATE)
        
        return {
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_cost_usd": round(cost, 6)
        }
    except Exception as e:
        logger.error(f"Failed to calculate Gemini cost: {e}")
        return {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}

def calculate_mistral_ocr_cost(response):
    """Mistral OCR is billed at $0.001 per page."""
    page_count = len(response.pages)
    total_cost = page_count * 0.001
    return {"pages": page_count, "cost": round(total_cost, 6)}
