import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

# IFC Tools importieren
from ifc_tools import (
    load_ifc_materials,
    load_kbob,
    apply_mapping,
    merge_and_compute
)

# --------------------------------------------------------
# Streamlit Layout
# --------------------------------------------------------
st.set_page_config(page_title="IFC Material- und CO₂-Analyse", layout="wide")
st.title("IFC Material- und CO₂-Analyse")

# --------------------------------------------------------
# IFC-Datei Upload
# --------------------------------------------------------
uploaded_file = st.file_uploader("Wähle eine IFC-Datei aus", type=["ifc"])

if uploaded_file:
    temp_path = "temp.ifc"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.read())

    st.success("Die IFC-Datei wurde erfolgreich hochgeladen.")

    # --------------------------------------------------------
    # 1) IFC Materialien
    # --------------------------------------------------------
    st.header("Materialien aus der IFC-Datei")

    df_ifc = load_ifc_materials(temp_path)
    st.dataframe(df_ifc)

    # Kleineres Diagramm
    st.subheader("Materialvolumen (m³)")
    fig, ax = plt.subplots(figsize=(3, 2))   # kleineres Diagramm
    df_ifc.groupby("Material_raw")["Menge"].sum().plot(kind="bar", ax=ax)
    ax.set_ylabel("Volumen (m³)")
    ax.tick_params(axis='x', rotation=45)
    st.pyplot(fig, use_container_width=False)  # verhindert Großziehen

    # --------------------------------------------------------
    # 2) KBOB Zuordnung
    # --------------------------------------------------------
    st.header("KBOB Zuordnung")

    kbob = load_kbob("data/kbob_materialien.csv")
    mapped = apply_mapping(df_ifc, kbob)
    st.dataframe(mapped)

    # --------------------------------------------------------
    # 3) CO₂ Berechnung
    # --------------------------------------------------------
    st.header("CO₂-Berechnung")

    result = merge_and_compute(mapped, kbob)
    st.dataframe(result)

    # Kleineres CO₂-Diagramm
    st.subheader("CO₂ nach Material (kg)")
    fig2, ax2 = plt.subplots(figsize=(3, 2))
    result.groupby("Material")["CO2_total_kg"].sum().plot(kind="bar", ax=ax2)
    ax2.set_ylabel("CO₂ (kg)")
    ax2.tick_params(axis='x', rotation=45)
    st.pyplot(fig2, use_container_width=False)

    # --------------------------------------------------------
    # 4) Export – CSV / Excel / PDF
    # --------------------------------------------------------
    st.header("Export")

    # CSV Export
    st.download_button(
        "CSV herunterladen",
        result.to_csv(index=False),
        file_name="co2_ergebnis.csv",
        mime="text/csv"
    )

    # Excel Export
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        result.to_excel(writer, index=False, sheet_name="CO2 Ergebnisse")

    st.download_button(
        "Excel herunterladen",
        excel_buffer.getvalue(),
        file_name="co2_ergebnis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --------------------------------------------------------
    # PDF Export
    # --------------------------------------------------------
    def create_pdf(df):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        
        width, height = A4
        x = 2 * cm
        y = height - 2 * cm

        c.setFont("Helvetica-Bold", 14)
        c.drawString(x, y, "CO₂-Auswertung")
        y -= 1 * cm

        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y, "Material")
        c.drawString(x + 6*cm, y, "Masse (kg)")
        c.drawString(x + 10*cm, y, "CO₂ (kg)")
        y -= 0.6 * cm

        c.setFont("Helvetica", 10)

        for _, row in df.iterrows():
            if y < 2 * cm:
                c.showPage()
                y = height - 2 * cm

            c.drawString(x, y, str(row["Material"]))
            c.drawString(x + 6*cm, y, f"{row['Masse_kg']:.1f}")
            c.drawString(x + 10*cm, y, f"{row['CO2_total_kg']:.1f}")
            y -= 0.5 * cm

        c.save()
        buffer.seek(0)
        return buffer

    pdf_bytes = create_pdf(result)

    st.download_button(
        "PDF herunterladen",
        pdf_bytes,
        file_name="co2_ergebnis.pdf",
        mime="application/pdf"
    )

else:
    st.info("Bitte lade eine IFC-Datei hoch, um die Analyse zu starten.")
