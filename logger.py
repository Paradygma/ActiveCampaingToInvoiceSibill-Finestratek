import logging
import os

_STANDARD_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())


class ExtraFieldsFormatter(logging.Formatter):
    """Appends any extra={...} fields to the log line, so they show up in
    Vercel's runtime logs instead of being silently dropped."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_KEYS
        }
        return f"{base} {extras}" if extras else base


logger = logging.getLogger("ac_to_sibill")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(ExtraFieldsFormatter("%(asctime)s %(levelname)s %(message)s"))
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
