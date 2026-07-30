import os
import sys

# Vercel's Python runtime executes this file from api/, but our shared
# modules (config, ac_client, mapping, sibill_client, logger) live at the
# project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request

from ac_client import get_deal_custom_fields
from config import get_config
from logger import logger, mask_deal_id
from mapping import MissingInvoiceDataError, build_invoice_payload
from sibill_client import check_duplicate_invoice, send_invoice_to_sibill

config = get_config()
app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook/activecampaign", methods=["GET", "POST"])
def activecampaign_webhook():
    # AC's built-in Webhook action can't send a custom JSON body — it always
    # posts its own fixed contact payload. So secret + dealId travel as query
    # params on the URL itself (AC substitutes %DEAL_ID% there too), not in
    # the body. request.get_json() fallback is kept for manual/local testing.
    body = request.get_json(silent=True) or {}

    logger.info(
        "Raw webhook payload received",
        extra={
            "args": dict(request.args),
            "form": dict(request.form),
            "json": body,
            "rawBody": request.get_data(as_text=True)[:2000],
        },
    )

    secret = request.args.get("secret") or body.get("secret")
    if not config.ac_webhook_secret or secret != config.ac_webhook_secret:
        logger.warning("Rejected webhook call: invalid secret")
        return jsonify({"error": "unauthorized"}), 401

    deal_id = request.args.get("dealId") or body.get("dealId")
    if not deal_id:
        return jsonify({"error": "dealId is required"}), 400

    logger.info("Processing ActiveCampaign webhook", extra={"dealId": mask_deal_id(deal_id)})

    try:
        if check_duplicate_invoice(deal_id):
            return jsonify({"status": "skipped", "reason": "duplicate"}), 200

        fields = get_deal_custom_fields(deal_id)
        payload = build_invoice_payload(deal_id, fields)
        send_invoice_to_sibill(payload, deal_id)
    except MissingInvoiceDataError as error:
        logger.error(
            "Invoice data incomplete", extra={"dealId": mask_deal_id(deal_id), "error": str(error)}
        )
        return jsonify({"error": str(error)}), 422
    except Exception as error:  # noqa: BLE001 - surface as generic 500 to AC
        logger.error(
            "Unexpected error processing webhook",
            extra={"dealId": mask_deal_id(deal_id), "error": str(error)},
        )
        return jsonify({"error": "internal error"}), 500

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 3000)), debug=True)
