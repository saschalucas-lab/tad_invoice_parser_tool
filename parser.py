import re
from datetime import datetime
import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    full_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)

    return "\n".join(full_text)


def extract_lines(text: str):
    return [line.strip() for line in text.splitlines() if line.strip()]


def clean_value(value: str) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip(" :;-")


def normalize_amount(amount):
    if amount is None or amount == "":
        return None

    if isinstance(amount, (int, float)):
        return float(amount)

    value = str(amount)
    value = value.replace("€", "").replace("EUR", "").replace("\xa0", " ")
    value = value.strip()

    if "," in value:
        value = value.replace(" ", "").replace(".", "").replace(",", ".")
    else:
        value = value.replace(" ", "")

    try:
        return float(value)
    except ValueError:
        return None


def normalize_date(date_str: str) -> str:
    if not date_str:
        return ""

    value = clean_value(date_str)

    formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return value


def looks_like_company_name(line: str) -> bool:
    if not line:
        return False

    line = clean_value(line)
    low = line.lower()

    blocked_terms = [
        "invoice", "facture", "rechnung", "date", "payment", "iban", "bic", "siret", "tva",
        "cif", "email", "e-mail", "tel", "teléfono", "telefono", "fax",
        "cliente/customer", "client", "customer", "n°", "create date",
        "payment date", "ref.", "designation", "qty", "unit cost", "line total",
        "total ttc", "total ht", "balance due", "subtotal", "taxe", "autriche",
        "australie", "france", "españa", "spain", "germany", "deutschland",
        "virement", "transferencia", "comments", "payment method", "cl/"
    ]

    if any(term in low for term in blocked_terms):
        return False

    if re.search(r"\d", line):
        return False

    if len(line) < 2:
        return False

    return True


def first_valid_line_after(lines, anchor_predicate, max_offset=6):
    for i, line in enumerate(lines):
        if anchor_predicate(line):
            for j in range(i + 1, min(i + 1 + max_offset, len(lines))):
                candidate = clean_value(lines[j])
                if looks_like_company_name(candidate):
                    return candidate
    return ""


def detect_document_type(text: str, lines) -> str:
    upper_text = text.upper()

    if "KAOTIK O SL" in upper_text or "KAOTIKO" in upper_text:
        return "kaotiko"

    if "OXBOW" in upper_text or "RECHNUNG - ORIGINAL" in upper_text:
        return "oxbow"

    if "SAMPLES TOPO DESIGNS" in upper_text:
        return "french_albion_samples"

    if "SAMPLES SUNBUM" in upper_text or "SAMPLES SUN BUM" in upper_text:
        return "french_albion_samples"

    ktn_lines = sum(1 for line in lines if re.match(r"KTN[A-Z0-9]+", line.strip()))
    if "N°F-" in text or ktn_lines > 5:
        return "french_albion_wholesale"

    if "FRENCH ALBION" in upper_text:
        return "french_albion_samples"

    return "generic"


def detect_brand(text: str, lines, doc_type: str) -> str:
    upper_text = text.upper()

    if doc_type == "kaotiko":
        return "KAOTIKO"

    if doc_type == "oxbow" or "OXBOW" in upper_text:
        return "OXBOW"

    if "TOPO DESIGNS" in upper_text:
        return "TOPO DESIGNS"

    if "SUNBUM" in upper_text or "SUN BUM" in upper_text:
        return "SUN BUM"

    if any(re.match(r"KTN[A-Z0-9]+", line.strip()) for line in lines):
        return "KATIN"

    return ""


def detect_rechnungssteller(text: str, doc_type: str) -> str:
    upper_text = text.upper()

    if doc_type in ["french_albion_wholesale", "french_albion_samples"] or "FRENCH ALBION" in upper_text:
        return "French Albion"

    if doc_type == "kaotiko" or "KAOTIK O SL" in upper_text or "KAOTIKO" in upper_text:
        return "Kaotiko"

    if doc_type == "oxbow" or "OXBOW" in upper_text:
        return "Oxbow"

    return ""


def parse_french_albion_wholesale(text: str, lines, brand: str, issuer: str) -> dict:
    invoice_number = ""
    date = ""
    customer = ""
    amount = None

    m = re.search(r"N°\s*(F-\d+)", text)
    if m:
        invoice_number = m.group(1)

    m = re.search(r"DATE\s*:\s*(\d{2}-\d{2}-\d{4})", text)
    if m:
        date = normalize_date(m.group(1))

    raw_lines = text.splitlines()

    for i, raw_line in enumerate(raw_lines):
        if "PAYMENT DATE" in raw_line.upper():
            for j in range(i + 1, min(i + 8, len(raw_lines))):
                candidate = clean_value(raw_lines[j])

                if not candidate:
                    continue

                low = candidate.lower()

                if (
                    low.startswith("taxe")
                    or low.startswith("b2b")
                    or low.startswith("ref.")
                    or low.startswith("devis")
                    or candidate in ["Allemagne", "Autriche", "France"]
                ):
                    continue

                if low in ["sas french albion", "french albion"]:
                    continue

                customer = candidate
                break
            break

    if not customer:
        m = re.search(r"PAYMENT DATE\s*:\s*[^\n]+\n([^\n]+)", text, re.IGNORECASE)
        if m:
            candidate = clean_value(m.group(1))
            low = candidate.lower()
            if (
                candidate
                and low not in ["sas french albion", "french albion"]
                and not low.startswith("taxe")
                and not low.startswith("b2b")
                and not low.startswith("ref.")
                and not low.startswith("devis")
            ):
                customer = candidate

    for line in lines:
        if "BALANCE DUE" in line.upper():
            m = re.search(r"([0-9\s]+,\d{2})", line)
            if m:
                amount = normalize_amount(m.group(1))
                break

    if amount is None:
        for line in lines:
            if line.upper().startswith("TOTAL"):
                m = re.search(r"([0-9\s]+,\d{2})", line)
                if m:
                    amount = normalize_amount(m.group(1))
                    break

    return {
        "Kundenname": customer,
        "Marke": brand,
        "Rechnungssteller": issuer,
        "Datum": date,
        "Rechnungsnummer": invoice_number,
        "Betrag": amount,
    }


def parse_french_albion_samples(text: str, lines, brand: str, issuer: str) -> dict:
    invoice_number = ""
    date = ""
    customer = ""
    amount = None

    m = re.search(r"N°\s*:\s*(FAC\d+)", text, re.IGNORECASE)
    if m:
        invoice_number = m.group(1)

    m = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        date = normalize_date(m.group(1))

    customer = first_valid_line_after(
        lines,
        lambda line: "N° client" in line or "N° CLIENT" in line,
        max_offset=5
    )

    for line in lines:
        if "TOTAL TTC" in line.upper():
            m = re.search(r"([0-9\s]+,\d{2})", line)
            if m:
                amount = normalize_amount(m.group(1))
                break

    return {
        "Kundenname": customer,
        "Marke": brand,
        "Rechnungssteller": issuer,
        "Datum": date,
        "Rechnungsnummer": invoice_number,
        "Betrag": amount,
    }


def parse_kaotiko(text: str, lines, brand: str, issuer: str) -> dict:
    invoice_number = ""
    date = ""
    customer = ""
    amount = None

    m = re.search(r"\bJOOR\s+(\d{6})\s+\d{2}/\d{2}/\d{4}\s+\d+\b", text, re.IGNORECASE)
    if m:
        invoice_number = m.group(1)

    m = re.search(r"Fecha de la operación:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        date = normalize_date(m.group(1))

    m = re.search(r"Fax:\s*([A-Z][A-Z\s&.\-]+)", text)
    if m:
        customer = clean_value(m.group(1))

    if customer:
        if customer.upper().startswith("CL/") or re.search(r"\d", customer):
            customer = ""

    if not customer:
        for line in lines:
            if "Fax:" in line:
                candidate = line.split("Fax:", 1)[-1].strip()
                candidate = clean_value(candidate)

                if not re.search(r"\d", candidate) and not candidate.upper().startswith("CL/"):
                    customer = candidate
                    break

    m = re.search(r"T\.Invoice\s*\(€\)\s*:\s*([0-9]+,\d{2})", text, re.IGNORECASE)
    if m:
        amount = normalize_amount(m.group(1))

    if amount is None:
        m = re.search(
            r"Líquido\(EUR\)\s*:\s*/\s*T\.Invoice\s*\(€\)\s*:\s*([0-9]+,\d{2})",
            text,
            re.IGNORECASE
        )
        if m:
            amount = normalize_amount(m.group(1))

    return {
        "Kundenname": customer,
        "Marke": brand,
        "Rechnungssteller": issuer,
        "Datum": date,
        "Rechnungsnummer": invoice_number,
        "Betrag": amount,
    }


def parse_oxbow(text: str, lines, brand: str, issuer: str) -> dict:
    invoice_number = ""
    date = ""
    customer = ""
    amount = None

    # Für Oxbow: Buchstaben-/Ziffernabstände entfernen
    compact_text = re.sub(r"(?<=\w)\s+(?=\w)", "", text)

    # Rechnungsnummer + Datum
    m = re.search(
        r"RECHNUNG\s*-\s*ORIGINAL\s*No\s*(\d+)\s*Vom\s*(\d{2}/\d{2}/\d{2})",
        compact_text,
        re.IGNORECASE
    )
    if m:
        invoice_number = clean_value(m.group(1))
        date = normalize_date(m.group(2))

    # Fallback
    if not invoice_number:
        m_num = re.search(r"Beleg-Nr\.\s*:\s*(\d+)", compact_text, re.IGNORECASE)
        if m_num:
            invoice_number = clean_value(m_num.group(1))

    if not date:
        m_date = re.search(r"Vom\s*(\d{2}/\d{2}/\d{2})", compact_text, re.IGNORECASE)
        if m_date:
            date = normalize_date(m_date.group(1))

    # Kunde
    m_customer = re.search(
        r"(MICHAEL\s*FRITSCH/\s*FRITTBOARDS)(?:\s+\1)?",
        compact_text,
        re.IGNORECASE
    )
    if m_customer:
        customer = "MICHAEL FRITSCH/ FRITTBOARDS"

    if not customer:
        header_text = compact_text.split("RECHNUNG-ORIGINAL")[0]
        if header_text == compact_text:
            header_text = compact_text.split("RECHNUNG - ORIGINAL")[0]

        header_lines = [clean_value(x) for x in header_text.splitlines() if clean_value(x)]

        blocked = {
            "OXBOW",
            "FRANCE",
            "GERMANY",
            "ALLEMAGNE",
            "DPD",
            "DEBITOR",
            "WARENEMPFÄNGER",
            "SPEDITEUR",
            "VAT KRED.",
            "VAT DEB.",
        }

        candidates = []
        for line in header_lines:
            upper = line.upper()

            if upper in blocked:
                continue
            if "OXBOW" in upper:
                continue
            if "VAT" in upper:
                continue
            if re.search(r"\d{4,}", line):
                continue
            if len(line) < 4:
                continue

            if "/" in line or "FRITT" in upper or "MICHAEL" in upper:
                candidates.append(line)

        if candidates:
            customer = candidates[0]

    # Betrag robuster erkennen
    amount_patterns = [
        r"ZU\s*ZAHLEN\s*([0-9\s]+\.\d{2})",
        r"ZU\s*ZAHLEN\s*([0-9\s\.]+,\d{2})",
        r"BETRAG\s*o\.?\s*MwST\.?\s*([0-9\s]+\.\d{2})",
        r"BETRAG\s*o\.?\s*MwST\.?\s*([0-9\s\.]+,\d{2})",
        r"FÄLLIG\s*\d{2}/\d{2}/\d{2}\s*([0-9\s]+\.\d{2})",
    ]

    for pattern in amount_patterns:
        m_amount = re.search(pattern, text, re.IGNORECASE)
        if m_amount:
            raw = m_amount.group(1)
            raw = raw.replace(" ", "")
            if "," in raw:
                raw = raw.replace(".", "")
            amount = normalize_amount(raw)
            if amount is not None:
                break

    return {
        "Kundenname": customer,
        "Marke": brand,
        "Rechnungssteller": issuer,
        "Datum": date,
        "Rechnungsnummer": invoice_number,
        "Betrag": amount,
    }


def parse_generic(text: str, lines, brand: str, issuer: str) -> dict:
    invoice_number = ""
    date = ""
    customer = ""
    amount = None

    invoice_patterns = [
        r"N°\s*:\s*([A-Z0-9-]+)",
        r"N°\s*([A-Z0-9-]+)",
        r"Invoice\s*(?:No\.?|Number)?\s*[:#]?\s*([A-Z0-9-]+)",
        r"Rechnungsnummer\s*[:#]?\s*([A-Z0-9-]+)",
        r"Beleg-Nr\.\s*:\s*(\d+)",
    ]
    for pattern in invoice_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            invoice_number = clean_value(m.group(1))
            break

    date_patterns = [
        r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"DATE\s*:\s*(\d{2}-\d{2}-\d{4})",
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{2}-\d{2}-\d{4})",
        r"(\d{2}/\d{2}/\d{2})",
    ]
    for pattern in date_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            date = normalize_date(m.group(1))
            break

    for line in lines:
        if "BALANCE DUE" in line.upper() or "TOTAL TTC" in line.upper():
            m = re.search(r"([0-9\s]+,\d{2})", line)
            if m:
                amount = normalize_amount(m.group(1))
                break

    if amount is None:
        for line in lines:
            if line.upper().startswith("TOTAL"):
                m = re.search(r"([0-9\s]+[.,]\d{2})", line)
                if m:
                    amount = normalize_amount(m.group(1))
                    break

    for line in lines:
        if looks_like_company_name(line):
            customer = clean_value(line)
            break

    return {
        "Kundenname": customer,
        "Marke": brand,
        "Rechnungssteller": issuer,
        "Datum": date,
        "Rechnungsnummer": invoice_number,
        "Betrag": amount,
    }


def extract_invoice_data(pdf_path: str) -> dict:
    text = extract_text_from_pdf(pdf_path)
    lines = extract_lines(text)

    doc_type = detect_document_type(text, lines)
    brand = detect_brand(text, lines, doc_type)
    issuer = detect_rechnungssteller(text, doc_type)

    if doc_type == "french_albion_wholesale":
        data = parse_french_albion_wholesale(text, lines, brand, issuer)
    elif doc_type == "french_albion_samples":
        data = parse_french_albion_samples(text, lines, brand, issuer)
    elif doc_type == "kaotiko":
        data = parse_kaotiko(text, lines, brand, issuer)
    elif doc_type == "oxbow":
        data = parse_oxbow(text, lines, brand, issuer)
    else:
        data = parse_generic(text, lines, brand, issuer)

    # Harter Schutz für French Albion
    if data.get("Rechnungssteller") == "French Albion":
        kundenname = str(data.get("Kundenname", "")).strip().lower()
        if kundenname in ["sas french albion", "french albion"]:
            data["Kundenname"] = ""

    # Harter Schutz für KAOTIKO
    if data.get("Rechnungssteller") == "Kaotiko":
        kundenname = str(data.get("Kundenname", "")).strip()
        if kundenname.upper().startswith("CL/") or re.search(r"\d", kundenname):
            data["Kundenname"] = ""

    # Harter Schutz für Oxbow
    if data.get("Rechnungssteller") == "Oxbow":
        kundenname = str(data.get("Kundenname", "")).strip().lower()
        if kundenname in ["oxbow", "oxbow s.a.s.", "oxbow sas"]:
            data["Kundenname"] = ""

    missing = [key for key, value in data.items() if value in ("", None)]
    data["Status"] = "OK" if not missing else "Prüfen: " + ", ".join(missing)

    return data