import re
from datetime import datetime

import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def extract_lines(text: str):
    return [line.strip() for line in text.splitlines() if line.strip()]


def clean_value(value: str) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip(" :;-")


def normalize_amount(amount):
    if amount is None or amount == "":
        return None

    value = str(amount)
    value = value.replace("€", "").replace("EUR", "").replace("\xa0", " ")
    value = re.sub(r"\s+", "", value)

    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def normalize_date(date_str: str) -> str:
    if not date_str:
        return ""

    value = clean_value(date_str)
    formats = ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y")

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return value


def detect_document_type(text: str) -> str:
    t = text.upper()
    if "KAOTIKO" in t or "KAOTIK O SL" in t:
        return "kaotiko"
    if "OXBOW" in t or "RECHNUNG - ORIGINAL" in t or "RECHNUNG-ORIGINAL" in t:
        return "oxbow"
    if "FRENCH ALBION" in t:
        return "french_albion"
    return "generic"


def detect_brand(text: str) -> str:
    t = text.upper()
    if "KAOTIKO" in t:
        return "KAOTIKO"
    if "OXBOW" in t:
        return "OXBOW"
    if "SUN BUM" in t or "SUNBUM" in t:
        return "SUN BUM"
    if "TOPO" in t:
        return "TOPO DESIGNS"
    if "KTN" in t:
        return "KATIN"
    return ""


def detect_issuer(text: str) -> str:
    t = text.upper()
    if "FRENCH ALBION" in t:
        return "French Albion"
    if "KAOTIKO" in t or "KAOTIK O SL" in t:
        return "Kaotiko"
    if "OXBOW" in t:
        return "Oxbow"
    return ""


def parse_french_albion(text: str, lines):
    data = {
        "Kundenname": "",
        "Datum": "",
        "Rechnungsnummer": "",
        "Betrag": None,
    }

    m = re.search(r"(F-\d+)", text)
    if m:
        data["Rechnungsnummer"] = m.group(1)

    m = re.search(r"DATE\s*:\s*(\d{2}-\d{2}-\d{4})", text, re.IGNORECASE)
    if m:
        data["Datum"] = normalize_date(m.group(1))

    for i, line in enumerate(lines):
        if "PAYMENT DATE" in line.upper():
            if i + 1 < len(lines):
                candidate = clean_value(lines[i + 1])
                if candidate and "FRENCH ALBION" not in candidate.upper():
                    data["Kundenname"] = candidate
                    break

    for line in lines:
        if "BALANCE DUE" in line.upper():
            m = re.search(r"([0-9\s]+,\d{2})", line)
            if m:
                data["Betrag"] = normalize_amount(m.group(1))
                break

    return data


def parse_kaotiko(text: str, lines):
    data = {
        "Kundenname": "",
        "Datum": "",
        "Rechnungsnummer": "",
        "Betrag": None,
    }

    m = re.search(r"\bJOOR\s+(\d{6})", text, re.IGNORECASE)
    if m:
        data["Rechnungsnummer"] = m.group(1)

    m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if m:
        data["Datum"] = normalize_date(m.group(1))

    for line in lines:
        if "FAX:" in line.upper():
            candidate = clean_value(line.split(":", 1)[-1])
            if candidate and not candidate.upper().startswith("CL/") and not re.search(r"\d", candidate):
                data["Kundenname"] = candidate
                break

    m = re.search(r"T\.Invoice\s*\(€\)\s*:\s*([0-9]+,\d{2})", text, re.IGNORECASE)
    if m:
        data["Betrag"] = normalize_amount(m.group(1))
    else:
        m = re.search(r"([0-9]+,\d{2})", text)
        if m:
            data["Betrag"] = normalize_amount(m.group(1))

    return data


def parse_oxbow(text: str, lines):
    data = {
        "Kundenname": "",
        "Datum": "",
        "Rechnungsnummer": "",
        "Betrag": None,
    }

    compact = re.sub(r"(?<=\w)\s+(?=\w)", "", text)

    m = re.search(
        r"RECHNUNG\s*-\s*ORIGINAL\s*No\s*(\d+)\s*Vom\s*(\d{2}/\d{2}/\d{2})",
        compact,
        re.IGNORECASE,
    )
    if m:
        data["Rechnungsnummer"] = m.group(1)
        data["Datum"] = normalize_date(m.group(2))

    if not data["Rechnungsnummer"]:
        m = re.search(r"Beleg-Nr\.\s*:\s*(\d+)", compact, re.IGNORECASE)
        if m:
            data["Rechnungsnummer"] = m.group(1)

    if not data["Datum"]:
        m = re.search(r"Vom\s*(\d{2}/\d{2}/\d{2})", compact, re.IGNORECASE)
        if m:
            data["Datum"] = normalize_date(m.group(1))

    m = re.search(r"(MICHAEL\s*FRITSCH/\s*FRITTBOARDS)", compact, re.IGNORECASE)
    if m:
        data["Kundenname"] = "MICHAEL FRITSCH/ FRITTBOARDS"

    amount_patterns = [
        r"ZU\s*ZAHLEN\s*([0-9]+\.[0-9]{2})\s*EUR",
        r"BETRAG\s*o\.?\s*MwST\.?\s*([0-9]+\.[0-9]{2})",
        r"F[ÄA]LLIG\s*\d{2}/\d{2}/\d{2}\s*([0-9]+\.[0-9]{2})",
    ]
    for pattern in amount_patterns:
        m = re.search(pattern, compact, re.IGNORECASE)
        if m:
            data["Betrag"] = normalize_amount(m.group(1))
            break

    return data


def extract_invoice_data(pdf_path: str) -> dict:
    text = extract_text_from_pdf(pdf_path)
    lines = extract_lines(text)

    doc_type = detect_document_type(text)

    if doc_type == "oxbow":
        data = parse_oxbow(text, lines)
    elif doc_type == "kaotiko":
        data = parse_kaotiko(text, lines)
    elif doc_type == "french_albion":
        data = parse_french_albion(text, lines)
    else:
        data = {
            "Kundenname": "",
            "Datum": "",
            "Rechnungsnummer": "",
            "Betrag": None,
        }

    data["Marke"] = detect_brand(text)
    data["Rechnungssteller"] = detect_issuer(text)

    missing = [k for k in ["Kundenname", "Datum", "Rechnungsnummer", "Betrag"] if not data.get(k)]
    data["Status"] = "OK" if not missing else "Prüfen: " + ", ".join(missing)

    return data