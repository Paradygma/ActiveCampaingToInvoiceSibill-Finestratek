import logging
import os

logger = logging.getLogger("ac_to_sibill")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def mask_piva(value: str | None) -> str:
    if not value:
        return "N/A"
    return f"***{value[-4:]}" if len(value) > 4 else "***"


def mask_deal_id(value: str | int | None) -> str:
    if not value:
        return "N/A"
    value = str(value)
    return f"deal_***{value[-3:]}" if len(value) > 3 else f"deal_{value}"
