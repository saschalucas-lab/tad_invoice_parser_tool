import os
import tempfile
import streamlit as st
import pandas as pd

from parser import extract_invoice_data, normalize_amount

from excel_writer import append_to_excel

OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "rechnungen.xlsx")

st.set_page_config(page_title="Rechnungs-Parser", layout="wide")

st.title("PDF-Rechnungen zu Excel")
st.write(
    "Lade eine oder mehrere PDF-Rechnungen hoch. "
    "Das Tool erkennt Kundenname, Marke, Rechnungssteller, Datum, "
    "Rechnungsnummer und Betrag."
)

uploaded_files = st.file_uploader(
    "Rechnungen hochladen",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    results = []

    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        try:
            data = extract_invoice_data(tmp_path)
            data["Dateiname"] = uploaded_file.name
            results.append(data)
        except Exception as e:
            results.append({
                "Kundenname": "",
                "Marke": "",
                "Rechnungssteller": "",
                "Datum": "",
                "Rechnungsnummer": "",
                "Betrag": None,
                "Status": f"Fehler: {str(e)}",
                "Dateiname": uploaded_file.name
            })
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    df = pd.DataFrame(results)

    expected_columns = [
        "Kundenname",
        "Marke",
        "Rechnungssteller",
        "Datum",
        "Rechnungsnummer",
        "Betrag",
        "Status",
        "Dateiname"
    ]

    for col in expected_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[expected_columns].copy()

    # Harte Normalisierung vor Anzeige
    df["Kundenname"] = df["Kundenname"].fillna("").astype(str).str.strip()
    df["Marke"] = df["Marke"].fillna("").astype(str).str.strip()
    df["Rechnungssteller"] = df["Rechnungssteller"].fillna("").astype(str).str.strip()
    df["Datum"] = df["Datum"].fillna("").astype(str).str.strip()
    df["Rechnungsnummer"] = df["Rechnungsnummer"].fillna("").astype(str).str.strip()
    df["Status"] = df["Status"].fillna("").astype(str).str.strip()
    df["Dateiname"] = df["Dateiname"].fillna("").astype(str).str.strip()

    # Betrag robust normalisieren
    df["Betrag"] = df["Betrag"].apply(normalize_amount)

    st.subheader("Erkannte Daten")
    st.write("Du kannst die Werte vor dem Speichern direkt in der Tabelle korrigieren.")

    edited_df = st.data_editor(
        df,
        width="stretch",
        num_rows="fixed",
        hide_index=True,
        column_config={
            "Kundenname": st.column_config.TextColumn("Kundenname"),
"Marke": st.column_config.SelectboxColumn(
    "Marke",
    options=["", "KATIN", "SUN BUM", "TOPO DESIGNS", "KAOTIKO", "OXBOW"]
),
"Rechnungssteller": st.column_config.SelectboxColumn(
    "Rechnungssteller",
    options=["", "French Albion", "Kaotiko", "Oxbow"]
),
            "Datum": st.column_config.TextColumn("Datum"),
            "Rechnungsnummer": st.column_config.TextColumn("Rechnungsnummer"),
            "Betrag": st.column_config.NumberColumn(
                "Betrag",
                format="%.2f"
            ),
            "Status": st.column_config.TextColumn("Status"),
            "Dateiname": st.column_config.TextColumn("Dateiname"),
        }
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("In Excel speichern"):
            save_df = edited_df.copy()
            save_df["Betrag"] = save_df["Betrag"].apply(normalize_amount)

            saved_count, skipped_count = append_to_excel(save_df, OUTPUT_FILE)

            if skipped_count == 0:
                st.success(f"{saved_count} Rechnung(en) gespeichert.")
            else:
                st.warning(
                    f"{saved_count} Rechnung(en) gespeichert, "
                    f"{skipped_count} Dublette(n) übersprungen."
                )

    with col2:
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "rb") as f:
                st.download_button(
                    "Excel herunterladen",
                    data=f,
                    file_name="rechnungen.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
else:
    st.info("Noch keine PDFs hochgeladen.")