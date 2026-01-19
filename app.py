import os
import glob
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm

import plotly.graph_objects as go

from ifc_tools import (
    load_ifc_materials,
    load_kbob,
    apply_mapping,
    merge_and_compute
)

# --------------------------------------------------------
# Streamlit Layout
# --------------------------------------------------------
st.set_page_config(page_title="IFC-basierte Material- und CO₂-Analyse", layout="wide")

# --------------------------------------------------------
# Logo (robust)
# --------------------------------------------------------
LOGO_CANDIDATES = [
    "assets/logo.png",
    "a5bbbb81-5733-4e62-8f31-5b200359f115.png",
]

def find_logo_path():
    for p in LOGO_CANDIDATES:
        if os.path.exists(p):
            return p
    root_pngs = glob.glob("*.png")
    return root_pngs[0] if root_pngs else None

col_logo, col_title = st.columns([1, 6], vertical_alignment="center")
with col_logo:
    lp = find_logo_path()
    if lp:
        st.image(lp, width=120)
with col_title:
    st.title("IFC-basierte Material- und CO₂-Analyse")
    st.caption("Auswertung von IFC-Modellen mit KBOB-Zuordnung und vereinfachter Ökobilanzierung")

# --------------------------------------------------------
# 3D IFC Preview
# --------------------------------------------------------
def show_ifc_3d(ifc_path: str):
    try:
        import ifcopenshell
        import ifcopenshell.geom
    except Exception as e:
        st.warning(
            "3D-Preview nicht verfügbar: ifcopenshell.geom konnte nicht geladen werden.\n\n"
            f"Fehler: {e}"
        )
        return

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    try:
        ifc = ifcopenshell.open(ifc_path)
    except Exception as e:
        st.error(f"IFC konnte nicht geöffnet werden: {e}")
        return

    xs, ys, zs = [], [], []
    I, J, K = [], [], []
    idx_offset = 0

    products = (
        ifc.by_type("IfcWall")
        + ifc.by_type("IfcSlab")
        + ifc.by_type("IfcRoof")
        + ifc.by_type("IfcBeam")
        + ifc.by_type("IfcColumn")
        + ifc.by_type("IfcBuildingElementPart")
    )

    for element in products:
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            geom = shape.geometry
            verts = geom.verts
            faces = geom.faces

            for n in range(0, len(verts), 3):
                xs.append(verts[n])
                ys.append(verts[n + 1])
                zs.append(verts[n + 2])

            for n in range(0, len(faces), 3):
                I.append(faces[n] + idx_offset)
                J.append(faces[n + 1] + idx_offset)
                K.append(faces[n + 2] + idx_offset)

            idx_offset += int(len(verts) / 3)
        except Exception:
            continue

    if len(xs) == 0 or len(I) == 0:
        st.warning("Keine Geometrie für die 3D-Vorschau gefunden.")
        return

    fig = go.Figure(
        data=[go.Mesh3d(x=xs, y=ys, z=zs, i=I, j=J, k=K, opacity=0.55)]
    )

    fig.update_layout(
        height=520,
        scene=dict(
            xaxis_visible=False,
            yaxis_visible=False,
            zaxis_visible=False,
            aspectmode="data"
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------
# Upload
# --------------------------------------------------------
uploaded_file = st.file_uploader("Wähle eine IFC-Datei aus", type=["ifc"])

if uploaded_file:
    temp_path = "temp.ifc"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.read())

    st.success("Die IFC-Datei wurde erfolgreich hochgeladen.")

    # --------------------------------------------------------
    # 0) 3D Vorschau
    # --------------------------------------------------------
    st.subheader("3D-Modell (IFC-Vorschau)")
    show_ifc_3d(temp_path)

    # --------------------------------------------------------
    # 1) IFC Materialien
    # --------------------------------------------------------
    st.header("Materialien und Mengen aus der IFC-Datei")

    df_ifc = load_ifc_materials(temp_path)
    if df_ifc.empty:
        st.warning("Keine auswertbaren Elemente gefunden.")
        st.stop()

    st.dataframe(df_ifc, use_container_width=True)

    # --------------------------------------------------------
    # Qualitätsprüfung (JETZT VOR DER GRAFIK)
    # --------------------------------------------------------
    st.subheader("Qualitätsprüfung der IFC-Daten")
    st.write("Zeilen:", len(df_ifc))
    st.write("Eindeutige Element_ID:", df_ifc["Element_ID"].nunique())
    dup_rows = df_ifc.duplicated(subset=["Element_ID", "Material_raw", "Menge"]).sum()
    st.write("Duplikate (Element_ID + Material + Menge):", int(dup_rows))

    # --------------------------------------------------------
    # Grafik Materialvolumen (danach)
    # --------------------------------------------------------
    st.subheader("Materialvolumen (m³)")
    vol = df_ifc.groupby("Material_raw")["Menge"].sum().sort_values(ascending=True)

    col_plot, col_space = st.columns([1, 2])
    with col_plot:
        fig, ax = plt.subplots(figsize=(4.0, 2.4), dpi=120)
        ax.barh(vol.index, vol.values)
        ax.set_xlabel("Volumen (m³)", fontsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=9)
        fig.subplots_adjust(left=0.38, right=0.96, top=0.92, bottom=0.22)
        st.pyplot(fig, use_container_width=False)

    # --------------------------------------------------------
    # 2) KBOB Zuordnung
    # --------------------------------------------------------
    st.header("KBOB-Zuordnung der IFC-Materialien")
    st.caption(
        "Automatische Zuordnung der IFC-Materialien zu KBOB-Materialien "
        "mit der Möglichkeit zur manuellen Korrektur."
    )

    kbob = load_kbob("data/kbob_materialien.csv")
    mapped_auto = apply_mapping(df_ifc, kbob)

    kbob_material_list = sorted(kbob["Material"].dropna().astype(str).unique().tolist())
    NOT_MAPPED = "(0) Nicht zugeordnet"
    dropdown_options = [NOT_MAPPED] + kbob_material_list

    mapped_auto["KBOB_Material"] = mapped_auto["KBOB_best"].fillna(NOT_MAPPED)
    mapped_auto.loc[~mapped_auto["KBOB_Material"].isin(dropdown_options), "KBOB_Material"] = NOT_MAPPED

    edited = st.data_editor(
        mapped_auto[[
            "Ifc_Typ", "Material_raw", "Menge", "Einheit_IFC",
            "KBOB_Material", "Match_score"
        ]],
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "KBOB_Material": st.column_config.SelectboxColumn(
                "KBOB_Material",
                help="Ausgewähltes KBOB-Material (manuell anpassbar)",
                options=dropdown_options
            ),
            "Match_score": st.column_config.NumberColumn(
                "Match_score",
                help="Automatischer Matching-Score (0..100)",
                format="%.1f"
            )
        },
        key="kbob_editor"
    )

    # --------------------------------------------------------
    # Zusammenfassung / Merge
    # --------------------------------------------------------
    final = mapped_auto.copy()
    final["KBOB_Material"] = edited["KBOB_Material"].values

    final = final.drop(columns=[
        "Material_ID", "Material", "Einheit", "CO2_Faktor", "Dichte"
    ], errors="ignore").copy()

    final = final.merge(
        kbob,
        left_on="KBOB_Material",
        right_on="Material",
        how="left"
    )

    mask_not = final["KBOB_Material"] == NOT_MAPPED
    final.loc[mask_not, ["Material_ID", "Material", "Einheit", "CO2_Faktor", "Dichte"]] = None

    st.subheader("Zusammengefasste KBOB-Materialien")
    kbob_view = (
        final.drop(columns=["Element_ID"], errors="ignore")
        .groupby(["Ifc_Typ", "Material_raw", "KBOB_Material"], as_index=False)
        .agg({
            "Menge": "sum",
            "Einheit_IFC": "first",
            "Material_ID": "first",
            "Material": "first",
            "Einheit": "first",
            "CO2_Faktor": "first",
            "Dichte": "first",
        })
        .sort_values(["Ifc_Typ", "Material_raw", "KBOB_Material"])
    )

    st.dataframe(
        kbob_view.rename(columns={
            "Material_raw": "IFC_Material",
            "Menge": "Menge (IFC)",
            "Einheit_IFC": "Einheit (IFC)",
            "CO2_Faktor": "CO₂-Faktor (kg CO₂-eq / kg)"
        }),
        use_container_width=True
    )

    # --------------------------------------------------------
    # 3) CO₂ Berechnung (letzte Tabelle)
    # --------------------------------------------------------
    st.header("CO₂-Berechnung")

    result = merge_and_compute(final)

    co2_table = (
        result
        .groupby(["Material"], as_index=False)
        .agg({
            "Menge": "sum",
            "Einheit_IFC": "first",
            "Einheit": "first",
            "CO2_Faktor": "first",
            "Dichte": "first",
            "Masse_kg": "sum",
            "CO2_total_kg": "sum"
        })
        .rename(columns={
            "Material": "KBOB_Material",
            "Menge": "Menge (IFC)",
            "Einheit_IFC": "Einheit (IFC)",
            "Einheit": "KBOB-Einheit",
            "CO2_Faktor": "CO₂-Faktor (kg CO₂-eq / kg)",
            "Dichte": "Dichte",
            "Masse_kg": "Masse (kg)",
            "CO2_total_kg": "CO₂ gesamt (kg CO₂-eq)"
        })
        .sort_values("CO₂ gesamt (kg CO₂-eq)", ascending=False)
    )

    st.dataframe(co2_table, use_container_width=True)

    # --------------------------------------------------------
    # CO₂-Grafik (wieder vor Export)
    # --------------------------------------------------------
    st.subheader("CO₂ nach Material (kg CO₂-eq)")
    co2_sum = co2_table.set_index("KBOB_Material")["CO₂ gesamt (kg CO₂-eq)"].sort_values(ascending=True)

    col_plot2, col_space2 = st.columns([1, 2])
    with col_plot2:
        fig2, ax2 = plt.subplots(figsize=(4.0, 2.4), dpi=120)
        ax2.barh(co2_sum.index.astype(str), co2_sum.values)
        ax2.set_xlabel("CO₂ (kg CO₂-eq)", fontsize=9)
        ax2.tick_params(axis="x", labelsize=8)
        ax2.tick_params(axis="y", labelsize=9)
        fig2.subplots_adjust(left=0.38, right=0.96, top=0.92, bottom=0.22)
        st.pyplot(fig2, use_container_width=False)

    # --------------------------------------------------------
    # 4) Export (immer co2_table)
    # --------------------------------------------------------
    st.header("Export")

    st.download_button(
        label="CSV herunterladen",
        data=co2_table.to_csv(index=False),
        file_name="co2_berechnung_materialien.csv",
        mime="text/csv"
    )

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        co2_table.to_excel(writer, index=False, sheet_name="CO2 Berechnung")

    st.download_button(
        label="Excel herunterladen",
        data=excel_buffer.getvalue(),
        file_name="co2_berechnung_materialien.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --------------------------------------------------------
    # PDF Export (Querformat, kein Überschreiben, Unicode-fest)
    # - ReportLab/Helvetica kann "₂" nicht zuverlässig -> im PDF schreiben wir "CO2"
    # --------------------------------------------------------
    def create_pdf_landscape(df: pd.DataFrame) -> BytesIO:
        # Für PDF: Spaltennamen ohne tiefgestelltes ₂ (damit kein CO■)
        df_pdf = df.copy()
        df_pdf.columns = [
            c.replace("CO₂", "CO2").replace("₂", "2") for c in df_pdf.columns
        ]

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=landscape(A4))
        width, height = landscape(A4)

        left = 1.4 * cm
        top = height - 1.4 * cm

        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, top, "CO2-Berechnung nach Material")
        y = top - 1.0 * cm

        cols = list(df_pdf.columns)

        # Fixe Spaltenbreiten (damit nichts überschreibt)
        # -> passt gut für deine Tabelle
        col_widths = [
            6.0 * cm,  # KBOB_Material
            2.6 * cm,  # Menge (IFC)
            2.6 * cm,  # Einheit (IFC)
            2.8 * cm,  # KBOB-Einheit
            3.5 * cm,  # CO2-Faktor ...
            2.3 * cm,  # Dichte
            3.0 * cm,  # Masse
            3.6 * cm,  # CO2 gesamt
        ]
        # Falls mehr/weniger Spalten: automatisch gleich verteilen
        if len(col_widths) != len(cols):
            col_widths = [(width - 2.8 * cm) / len(cols)] * len(cols)

        c.setFont("Helvetica-Bold", 9)
        x = left
        for col, w in zip(cols, col_widths):
            c.drawString(x, y, str(col)[:40])
            x += w

        y -= 0.55 * cm
        c.setFont("Helvetica", 9)

        def fmt(v):
            if pd.isna(v):
                return "-"
            if isinstance(v, float):
                return f"{v:.2f}"
            return str(v)

        for _, row in df_pdf.iterrows():
            if y < 1.4 * cm:
                c.showPage()
                c.setFont("Helvetica-Bold", 16)
                c.drawString(left, top, "CO2-Berechnung nach Material (Fortsetzung)")
                y = top - 1.0 * cm

                c.setFont("Helvetica-Bold", 9)
                x = left
                for col, w in zip(cols, col_widths):
                    c.drawString(x, y, str(col)[:40])
                    x += w
                y -= 0.55 * cm
                c.setFont("Helvetica", 9)

            x = left
            for col, w in zip(cols, col_widths):
                c.drawString(x, y, fmt(row[col])[:40])
                x += w
            y -= 0.48 * cm

        c.save()
        buf.seek(0)
        return buf

    pdf_bytes = create_pdf_landscape(co2_table)

    st.download_button(
        label="PDF herunterladen (Querformat)",
        data=pdf_bytes,
        file_name="co2_berechnung_materialien.pdf",
        mime="application/pdf"
    )

