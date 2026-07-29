import requests

from config import get_config
from logger import logger, mask_deal_id

config = get_config()


def get_deal_custom_fields(deal_id: str) -> dict[int, str]:
    """Fetch all custom field values for a Deal, keyed by customFieldId.

    ActiveCampaign paginates dealCustomFieldData; a Deal in this account can
    have 100+ custom fields defined, so we page through until exhausted.
    """
    fields: dict[int, str] = {}
    offset = 0
    limit = 100

    while True:
        response = requests.get(
            f"{config.ac_api_url}/api/3/deals/{deal_id}/dealCustomFieldData",
            headers={"Api-Token": config.ac_api_token},
            params={"limit": limit, "offset": offset},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("dealCustomFieldData", [])

        for item in items:
            fields[int(item["customFieldId"])] = item.get("fieldValue") or ""

        total = int(data.get("meta", {}).get("total", len(items)))
        offset += len(items)
        if offset >= total or not items:
            break

    logger.info(
        "Fetched deal custom fields",
        extra={"dealId": mask_deal_id(deal_id), "fieldCount": len(fields)},
    )
    return fields
