import re
from datetime import date

from config import get_config

config = get_config()

# ActiveCampaign Deal custom field IDs (finestratek.api-us1.com account).
# See memory/project_ac_deal_field_schema.md for the full discovery notes.
FIELD = {
    "comune": 79,
    "cap": 80,
    "provincia": 94,
    "numero_fattura": 101,
    "data_fattura": 102,
    "cliente_destinatario": 107,
    "cf_destinatario": 108,
    "indirizzo_destinatario": 109,
    "codice_destinatario": 110,
    "metodo_pagamento": 111,
    "istituto_bancario": 112,
    "iban": 113,
    "tipo_documento": 124,
    "causale": 125,
    "prodotto": 126,
    "quantita": 127,
    "prezzo_unitario": 128,
    "importo_netto": 129,
    "importo_lordo": 130,
    "totale_imponibile": 132,
    "iva_10": 133,
    "iva_22": 134,
    "totale_documento": 135,
}

# Up to 5 installments: (due date field id, amount field id) pairs.
SCADENZA_FIELDS = [(114, 115), (116, 117), (118, 119), (120, 121), (122, 123)]

# Fixed SDI payment-method code — the business confirmed all payments are
# bank transfers, so this is a constant, not inferred from the free-text
# "Metodo di pagamento" Deal field (111), which is never read.
MODALITA_PAGAMENTO = "MP05"


class MissingInvoiceDataError(Exception):
    pass


def _get(fields: dict[int, str], key: str, default: str = "") -> str:
    value = fields.get(FIELD[key], "")
    return value.strip() if value else default


def _to_iso_date(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return date.today().isoformat()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return raw


def _is_populated_amount(value: str) -> bool:
    try:
        return float(value.replace(",", ".")) > 0
    except ValueError:
        return False


def _resolve_vat_rate(fields: dict[int, str]) -> str:
    iva_10 = _get(fields, "iva_10")
    iva_22 = _get(fields, "iva_22")

    if _is_populated_amount(iva_10):
        return "10.00"
    if _is_populated_amount(iva_22):
        return "22.00"
    raise MissingInvoiceDataError(
        "Nessuna aliquota IVA valorizzata (campi 'IVA 10%'/'IVA 22%' entrambi vuoti)"
    )


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(";")] if value else []


def _build_dettaglio_linee(fields: dict[int, str], vat_rate: str) -> list[dict]:
    """Parses the Deal's ';'-delimited prodotto/quantita/prezzo_unitario/
    importo_netto fields into one or more FatturaPA line items. A single
    value with no ';' behaves as a single line, same as before."""
    prodotti = _split(_get(fields, "prodotto", "Servizio"))
    quantitas = _split(_get(fields, "quantita", "1.00"))
    prezzi_unitari = _split(_get(fields, "prezzo_unitario", "0.00"))
    importi = _split(_get(fields, "importo_netto", "0.00"))

    if not (len(prodotti) == len(quantitas) == len(prezzi_unitari) == len(importi)):
        raise MissingInvoiceDataError(
            "I campi 'Prodotto', 'Quantità', 'Prezzo Unitario' e 'Importo Netto' "
            "devono avere lo stesso numero di voci separate da ';'"
        )

    return [
        {
            "numero_linea": str(index + 1),
            "descrizione": descrizione,
            "quantita": quantita,
            "prezzo_unitario": prezzo_unitario,
            "prezzo_totale": importo,
            "aliquota_iva": vat_rate,
        }
        for index, (descrizione, quantita, prezzo_unitario, importo) in enumerate(
            zip(prodotti, quantitas, prezzi_unitari, importi)
        )
    ]


def _build_dettaglio_pagamento(fields: dict[int, str]) -> list[dict]:
    """Maps the Deal's up-to-5 installment (Scadenza/Importo Scadenza) field
    pairs into FatturaPA payment-detail lines, skipping empty installments."""
    dettaglio_pagamento = []
    for date_field_id, amount_field_id in SCADENZA_FIELDS:
        amount = (fields.get(amount_field_id) or "").strip()
        if not _is_populated_amount(amount):
            continue
        due_date = _to_iso_date((fields.get(date_field_id) or "").strip())
        dettaglio_pagamento.append(
            {
                "modalita_pagamento": MODALITA_PAGAMENTO,
                "data_scadenza_pagamento": due_date,
                "importo_pagamento": amount,
            }
        )
    return dettaglio_pagamento


def build_invoice_payload(deal_id: str, fields: dict[int, str]) -> dict:
    """Pure 1:1 mapping of manually-filled Deal custom fields into an FPR12
    payload for Sibill. No tax/VAT calculation is performed here — the
    business decided all invoice fields are filled by hand in ActiveCampaign
    before the trigger fires.
    """
    # Cedente/prestatore (issuer) is always Aura srl's own registered fiscal
    # data from config — never from the Deal's "* EMITTENTE" fields, which
    # Sibill rejects with invalid_invoice_ownership if they don't match the
    # company actually registered on the Sibill account.
    denominazione_cedente = config.company_denominazione
    piva_cedente = config.company_partita_iva
    cf_cedente = config.company_codice_fiscale
    indirizzo_cedente = config.company_indirizzo

    denominazione_cliente = _get(fields, "cliente_destinatario", "Cliente")
    cf_cliente = _get(fields, "cf_destinatario")
    indirizzo_cliente = _get(fields, "indirizzo_destinatario", "Indirizzo non specificato")
    codice_destinatario = _get(fields, "codice_destinatario", "0000000")

    comune = _get(fields, "comune", "Non specificato")
    cap = _get(fields, "cap", config.company_cap)
    provincia = _get(fields, "provincia", "MI")

    tipo_documento = _get(fields, "tipo_documento", "TD01")
    causale = _get(fields, "causale", "Servizio")
    data_fattura = _to_iso_date(_get(fields, "data_fattura"))

    imponibile = _get(fields, "totale_imponibile", "0.00")
    totale_documento = _get(fields, "totale_documento", imponibile)

    vat_rate = _resolve_vat_rate(fields)
    vat_amount = round(float(totale_documento.replace(",", ".")) - float(imponibile.replace(",", ".")), 2)

    dettaglio_linee = _build_dettaglio_linee(fields, vat_rate)
    dettaglio_pagamento = _build_dettaglio_pagamento(fields)

    return {
        "versione": "FPR12",
        "fattura_elettronica_header": {
            "versione": "FPR12",
            "dati_trasmissione": {
                "id_trasmittente": {"id_paese": "IT", "id_codice": piva_cedente},
                "codice_destinatario": codice_destinatario,
                "formato_trasmissione": "FPR12",
            },
            "cedente_prestatore": {
                "dati_anagrafici": {
                    "id_fiscale_iva": {"id_paese": "IT", "id_codice": piva_cedente},
                    "codice_fiscale": cf_cedente,
                    "anagrafica": {"denominazione": denominazione_cedente},
                    "regime_fiscale": "RF01",
                },
                "sede": {
                    "indirizzo": indirizzo_cedente,
                    "cap": config.company_cap,
                    "comune": config.company_comune,
                    "provincia": config.company_provincia,
                    "nazione": config.company_nazione,
                },
            },
            "cessionario_committente": {
                "dati_anagrafici": {
                    # Solo codice_fiscale: il Deal non distingue P.IVA da CF per il
                    # destinatario (clientela prevalentemente privata/B2C).
                    "codice_fiscale": cf_cliente,
                    "anagrafica": {"denominazione": denominazione_cliente},
                },
                "sede": {
                    "indirizzo": indirizzo_cliente,
                    "cap": cap,
                    "comune": comune,
                    "provincia": provincia,
                    "nazione": "IT",
                },
            },
        },
        "fattura_elettronica_body": [
            {
                "dati_generali": {
                    "dati_generali_documento": {
                        "tipo_documento": tipo_documento,
                        "divisa": "EUR",
                        "data": data_fattura,
                        "causale": [causale],
                        "importo_totale_documento": totale_documento,
                    },
                },
                "dati_beni_servizi": {
                    "dettaglio_linee": dettaglio_linee,
                    "dati_riepilogo": [
                        {
                            "aliquota_iva": vat_rate,
                            "imponibile_importo": imponibile,
                            "imposta": f"{vat_amount:.2f}",
                        }
                    ],
                },
                **(
                    {
                        "dati_pagamento": [
                            {
                                "condizioni_pagamento": (
                                    "TP01" if len(dettaglio_pagamento) > 1 else "TP02"
                                ),
                                "dettaglio_pagamento": dettaglio_pagamento,
                            }
                        ]
                    }
                    if dettaglio_pagamento
                    else {}
                ),
            }
        ],
    }
