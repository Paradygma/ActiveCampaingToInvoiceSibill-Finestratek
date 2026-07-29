import requests

from config import get_config
from logger import logger, mask_deal_id

config = get_config()


def check_duplicate_invoice(deal_id: str) -> bool:
    """Check Sibill for an existing document matching this Deal, to keep the
    webhook idempotent (AC retries/duplicate triggers must not double-invoice).
    """
    response = requests.get(
        f"{config.sibill_api_url}/companies/{config.sibill_company_id}/documents",
        headers={"Authorization": f"Bearer {config.sibill_api_key}"},
        timeout=5,
    )
    response.raise_for_status()
    documents = response.json().get("data", [])

    deal_id = str(deal_id)
    duplicate = any(
        doc.get("reconciliation_identifier") == deal_id or doc.get("external_id") == deal_id
        for doc in documents
    )

    if duplicate:
        logger.info("Invoice already exists, skipping", extra={"dealId": mask_deal_id(deal_id)})
    return duplicate


def send_invoice_to_sibill(payload: dict, deal_id: str) -> None:
    """Create the invoice in Sibill as a draft (issue=false) — mirrors the
    stripe-sibill-middleware reference: never auto-emits to SDI.
    """
    response = requests.post(
        f"{config.sibill_api_url}/companies/{config.sibill_company_id}/documents/invoice",
        params={"issue": "false", "reconciliation_identifier": str(deal_id)},
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.sibill_api_key}",
        },
        timeout=10,
    )
    if not response.ok:
        logger.error(
            "Failed to send invoice to Sibill",
            extra={
                "dealId": mask_deal_id(deal_id),
                "statusCode": response.status_code,
                "sibillError": response.text,
            },
        )
        response.raise_for_status()

    logger.info(
        "Invoice sent to Sibill successfully",
        extra={"dealId": mask_deal_id(deal_id), "statusCode": response.status_code},
    )
