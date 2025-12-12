import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

# --------------------------------------------------------
# IFC Tools importieren
# --------------------------------------------------------
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

uploaded_file = st.file_uploader("Wähle eine IFC-Datei aus", type=["ifc"])

if uploaded_file:
    temp_path = "temp.ifc"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.read())

    st.success("Die IFC-Datei wurde erfolgreich hochgeladen.")

    # --------------------------------------------------------
    # 1) Materialien aus der IFC-Datei (so lassen)
    # --------------------------------------------------------
    st.header("Materialien aus der IFC-Datei")
    df_ifc = load_ifc_materials(temp_path)
    st.dataframe(df_ifc)

    # --------------------------------------------------------
    # Diagramm: Materialvolumen (m³) - kleiner + nicht über ganze Seite
    # --------------------------------------------------------
    st.subheader("Materialvolumen (m³)")

    # Daten für Plot
    vol = df_ifc.groupby("Material_raw")["Menge"].sum().sort_values(ascending=True)

    # WICHTIG: Diagramm in schmaler Column anzeigen, damit es nicht Full-Width wird
    col_plot, col_space = st.columns([1, 2])  # links schmal, rechts "leer"

    with col_plot:
        fig, ax = plt.subplots(figsize=(4.0, 2.4), dpi=120)

        # Balken horizontal
        ax.barh(vol.index, vol.values)

        # Kleine Schrift (Materialnamen bleiben!)
        ax.set_xlabel("Volumen (m³)", fontsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=9)

        # Wichtig: Layout kontrollieren (statt huge left margin)
        fig.subplots_adjust(left=0.38, right=0.96, top=0.92, bottom=0.22)

        st.pyplot(fig, use_container_width=False)

    # --------------------------------------------------------
    # 2) KBOB Zuordnung (Element_ID weg + zusammenfassen nach Ifc_Typ & Material_raw)
    # --------------------------------------------------------
    st.header("KBOB Zuordnung")

    kbob = load_kbob("data/kbob_materialien.csv")
    mapped = apply_mapping(df_ifc, kbob)

    kbob_view = (
        mapped.drop(columns=["Element_ID"], errors="ignore")
        .groupby(["Ifc_Typ", "Material_raw"], as_index=False)
        .agg({
            "Menge": "sum",
            "Einheit_IFC": "first",
            "Material_ID": "first",
            "Material": "first",
            "Einheit": "first",
            "CO2_Faktor": "first",
            "Dichte": "first",
        })
        .sort_values(["Ifc_Typ", "Material_raw"])
    )

    st.dataframe(kbob_view)

    # --------------------------------------------------------
    # 3) CO₂ Berechnung (intern erst rechnen, dann Ansicht zusammenfassen nach Material)
    # --------------------------------------------------------
    st.header("CO₂-Berechnung")

    result = merge_and_compute(mapped)

    co2_view = (
        result
        .groupby(["Material"], as_index=False)
        .agg({
            "Einheit": "first",
            "CO2_Faktor": "first",
            "Dichte": "first",
            "Masse_kg": "sum",
            "CO2_total_kg": "sum"
        })
        .sort_values("CO2_total_kg", ascending=False)
    )

    st.dataframe(co2_view)

    # --------------------------------------------------------
    # CO₂ nach Material (kg) - so lassen, aber auch nicht Full-Width
    # --------------------------------------------------------
    st.subheader("CO₂ nach Material (kg)")

    co2_sum = result.groupby("Material")["CO2_total_kg"].sum().sort_values(ascending=True)

    col_plot2, col_space2 = st.columns([1, 2])

    with col_plot2:
        fig2, ax2 = plt.subplots(figsize=(4.0, 2.4), dpi=120)
        ax2.barh(co2_sum.index, co2_sum.values)

        ax2.set_xlabel("CO₂ (kg)", fontsize=9)
        ax2.tick_params(axis="x", labelsize=8)
        ax2.tick_params(axis="y", labelsize=9)

        fig2.subplots_adjust(left=0.38, right=0.96, top=0.92, bottom=0.22)

        st.pyplot(fig2, use_container_width=False)

    # --------------------------------------------------------
    # 4) Export (so lassen: exportiert result)
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

    # PDF Export (aus result wie bisher)
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
        c.drawString(x + 7 * cm, y, "Masse (kg)")
        c.drawString(x + 11 * cm, y, "CO₂ (kg)")
        y -= 0.6 * cm

        c.setFont("Helvetica", 10)

        # für PDF: lieber aggregiert, sonst wird es endlos lang
        pdf_df = (
            df.groupby("Material", as_index=False)[["Masse_kg", "CO2_total_kg"]]
            .sum()
            .sort_values("CO2_total_kg", ascending=False)
        )

        for _, row in pdf_df.iterrows():
            if y < 2 * cm:
                c.showPage()
                y = height - 2 * cm

            c.drawString(x, y, str(row["Material"]))
            c.drawString(x + 7 * cm, y, f"{row['Masse_kg']:.1f}")
            c.drawString(x + 11 * cm, y, f"{row['CO2_total_kg']:.1f}")
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


