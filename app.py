import io
import os
import tempfile

import pandas as pd
import streamlit as st

from parser import extract_invoice_data

st.set_page_config(page_title="Invoice Parser Tool", layout="wide")
st.title("Invoice Parser Tool")

uploaded_files = st.file_uploader(
    "Rechnungen hochladen (PDF)",
    type=["pdf"],
    accept_multiple_files=True,
)

if uploaded_files:
    results = []

    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name

        try:
            data = extract_invoice_data(tmp_path)
            data["Dateiname"] = uploaded_file.name
            results.append(data)
        except Exception as e:
            results.append(
                {
                    "Kundenname": "",
                    "Marke": "",
                    "Rechnungssteller": "",
                    "Datum": "",
                    "Rechnungsnummer": "",
                    "Betrag": None,
                    "Status": f"Fehler: {e}",
                    "Dateiname": uploaded_file.name,
                }
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    df = pd.DataFrame(results)

    # Spalten-Reihenfolge absichern
    expected_columns = [
        "Kundenname",
        "Marke",
        "Rechnungssteller",
        "Datum",
        "Rechnungsnummer",
        "Betrag",
        "Status",
        "Dateiname",
    ]
    for col in expected_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[expected_columns]

    st.subheader("Erkannte Daten")
    edited_df = st.data_editor(
        df,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Marke": st.column_config.SelectboxColumn(
                "Marke",
                options=["", "KATIN", "SUN BUM", "TOPO DESIGNS", "KAOTIKO", "OXBOW"],
            ),
            "Rechnungssteller": st.column_config.SelectboxColumn(
                "Rechnungssteller",
                options=["", "French Albion", "Kaotiko", "Oxbow"],
            ),
            "Betrag": st.column_config.NumberColumn("Betrag", format="%.2f"),
        },
    )

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        edited_df.to_excel(writer, index=False, sheet_name="Rechnungen")
    excel_buffer.seek(0)

    st.download_button(
        label="Excel herunterladen",
        data=excel_buffer,
        file_name="rechnungen.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Bitte eine oder mehrere PDF-Rechnungen hochladen.")