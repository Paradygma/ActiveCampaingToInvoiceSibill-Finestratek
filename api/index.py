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

# "MCOM2.1 pagato" custom deal field — the automation trigger. AC's native
# "Deal Updated" account webhook fires on ANY change to the deal, and its
# payload only carries standard deal attributes (no custom fields), so we
# must re-check this ourselves after fetching the deal's custom fields.
TRIGGER_FIELD_ID = 83
TRIGGER_FIELD_VALUE = "Si"


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook/activecampaign", methods=["GET", "POST"])
def activecampaign_webhook():
    # AC's native account-level "Webhooks" (Settings > Developer > Webhooks,
    # event "Deal Updated") POST form-encoded data with deal[id], deal[title],
    # etc. — not JSON. secret still travels as a URL query param since it's
    # not part of AC's payload. JSON body fallback is kept for manual testing.
    body = request.get_json(silent=True) or {}

    secret = request.args.get("secret") or body.get("secret")
    if not config.ac_webhook_secret or secret != config.ac_webhook_secret:
        logger.warning("Rejected webhook call: invalid secret")
        return jsonify({"error": "unauthorized"}), 401

    deal_id = request.form.get("deal[id]") or request.args.get("dealId") or body.get("dealId")
    if not deal_id:
        return jsonify({"error": "dealId is required"}), 400

    logger.info("Processing ActiveCampaign webhook", extra={"dealId": mask_deal_id(deal_id)})

    try:
        fields = get_deal_custom_fields(deal_id)
        if fields.get(TRIGGER_FIELD_ID) != TRIGGER_FIELD_VALUE:
            return jsonify({"status": "skipped", "reason": "trigger field not set"}), 200

        if check_duplicate_invoice(deal_id):
            return jsonify({"status": "skipped", "reason": "duplicate"}), 200

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
