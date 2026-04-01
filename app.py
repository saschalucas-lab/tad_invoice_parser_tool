import streamlit as st
import pandas as pd
import tempfile
import os

from parser import extract_invoice_data

st.set_page_config(page_title="Invoice Parser Tool", layout="wide")

st.title("📄 Invoice Parser Tool")

uploaded_files = st.file_uploader(
    "Rechnungen hochladen (PDF)",
    type=["pdf"],
    accept_multiple_files=True
)

results = []

if uploaded_files:
    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name

        try:
            data = extract_invoice_data(tmp_path)
            data["Dateiname"] = uploaded_file.name
            results.append(data)
        except Exception as e:
            st.error(f"Fehler bei Datei {uploaded_file.name}: {e}")

        finally:
            os.remove(tmp_path)

    if results:
        df = pd.DataFrame(results)

        st.subheader("Erkannte Daten")

        edited_df = st.data_editor(
            df,
            use_container_width=True
        )

        # Download als Excel
        excel_file = "output.xlsx"
        edited_df.to_excel(excel_file, index=False)

        with open(excel_file, "rb") as f:
            st.download_button(
                label="📥 Excel herunterladen",
                data=f,
                file_name="rechnungen.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )