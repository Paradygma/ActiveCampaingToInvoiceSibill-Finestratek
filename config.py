import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    ac_api_url = _env("AC_API_URL").rstrip("/")
    ac_api_token = _env("AC_API_TOKEN")
    ac_webhook_secret = _env("AC_WEBHOOK_SECRET")

    sibill_api_url = _env("SIBILL_API_URL").rstrip("/")
    sibill_api_key = _env("SIBILL_API_KEY")
    sibill_company_id = _env("SIBILL_COMPANY_ID")

    company_denominazione = _env("COMPANY_DENOMINAZIONE")
    company_partita_iva = _env("COMPANY_PARTITA_IVA")
    company_codice_fiscale = _env("COMPANY_CODICE_FISCALE")
    company_indirizzo = _env("COMPANY_INDIRIZZO")
    company_cap = _env("COMPANY_CAP")
    company_comune = _env("COMPANY_COMUNE")
    company_provincia = _env("COMPANY_PROVINCIA")
    company_nazione = _env("COMPANY_NAZIONE", "IT")

    required = [
        "ac_api_url",
        "ac_api_token",
        "ac_webhook_secret",
        "sibill_api_url",
        "sibill_api_key",
        "sibill_company_id",
    ]


def get_config() -> Config:
    config = Config()
    missing = [name for name in config.required if not getattr(config, name)]
    if missing:
        # Non-fatal: logged so the serverless function doesn't crash on cold start,
        # matching the reference stripe-sibill-middleware behaviour.
        from logger import logger

        logger.error("Missing required env vars: %s", ", ".join(missing))
    return config
