# -*- coding: utf-8 -*-
# IFC → KBOB → CO2 Berechnung

import os
import pandas as pd
import ifcopenshell


# ---------------------------------------------------------
# 1) IFC einlesen und Material + Mengen extrahieren
# ---------------------------------------------------------

def load_ifc_materials(ifc_path: str) -> pd.DataFrame:
    ifc = ifcopenshell.open(ifc_path)
    elements = []

    for product in ifc.by_type("IfcBuildingElement"):

        mats = product.HasAssociations
        if not mats:
            continue

        # Material extrahieren
        material_name = None
        for assoc in mats:
            if assoc.is_a("IfcRelAssociatesMaterial"):
                mat = assoc.RelatingMaterial
                if mat.is_a("IfcMaterial"):
                    material_name = mat.Name
                elif mat.is_a("IfcMaterialLayerSet"):
                    try:
                        material_name = mat.MaterialLayers[0].Material.Name
                    except:
                        pass

        if not material_name:
            continue

        # Volumen extrahieren
        volume = None
        quantity_sets = product.IsDefinedBy
        if quantity_sets:
            for rel in quantity_sets:
                if rel.is_a("IfcRelDefinesByProperties"):
                    props = rel.RelatingPropertyDefinition
                    if props.is_a("IfcElementQuantity"):
                        for q in props.Quantities:
                            if q.is_a("IfcQuantityVolume"):
                                volume = q.VolumeValue

        if volume is None:
            continue

        elements.append({
            "Material_raw": str(material_name),
            "Menge": float(volume),     # m³
            "Einheit_IFC": "m3"
        })

    return pd.DataFrame(elements)


# ---------------------------------------------------------
# 2) KBOB laden (Material, Dichte, CO2-Faktor)
# ---------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
KBOB_CSV = os.path.join(DATA_DIR, "kbob_materialien.csv")

def load_kbob(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8")

    df["Material"] = df["Material"].astype(str).str.strip()
    df["CO2_Faktor"] = pd.to_numeric(df["CO2_Faktor"], errors="coerce")
    df["Dichte"] = pd.to_numeric(df["Dichte"], errors="coerce")

    df = df.dropna(subset=["Material"])
    return df


# ---------------------------------------------------------
# 3) Material-Mapping
# ---------------------------------------------------------

def build_mapping():
    return {
        "stahlbeton": "hochbaubeton",
        "beton": "hochbaubeton",
        "mauerwerk": "backstein",
        "backstein": "backstein",
        "ziegel": "backstein",
    }


def apply_mapping(df_ifc, df_kbob):
    df = df_ifc.copy()
    keywords = build_mapping()

    def match_material(raw):
        raw_lower = str(raw).lower()

        for key, kb_keyword in keywords.items():
            if key in raw_lower:

                candidates = df_kbob[df_kbob["Material"].str.lower().str.contains(kb_keyword)]

                # Tiefgründungen vermeiden
                candidates = candidates[
                    ~candidates["Material"].str.lower().str.contains("tief")
                ]
                candidates = candidates[
                    ~candidates["Material"].str.lower().str.contains("pfahl")
                ]

                if not candidates.empty:
                    return candidates.iloc[0]["Material"]

        return raw

    df["Material"] = df["Material_raw"].apply(match_material)
    return df


# ---------------------------------------------------------
# 4) Merge + korrekte CO2 Berechnung
# ---------------------------------------------------------

def merge_and_compute(df_ifc, df_kbob):

    merged = pd.merge(df_ifc, df_kbob, on="Material", how="left")

    # Numerische Felder sicherstellen
    merged["Dichte"] = pd.to_numeric(merged["Dichte"], errors="coerce")
    merged["CO2_Faktor"] = pd.to_numeric(merged["CO2_Faktor"], errors="coerce")

    # Masse (kg) = Volumen (m3) × Dichte (kg/m3)
    merged["Masse_kg"] = merged["Menge"] * merged["Dichte"]

    # CO2 total = Masse × Faktor
    merged["CO2_total_kg"] = merged["Masse_kg"] * merged["CO2_Faktor"]

    merged["Einheit_KBOB"] = "kg"

    return merged


# ---------------------------------------------------------
# 5) Exportfunktion
# ---------------------------------------------------------

EXPORT_CSV = os.path.join(DATA_DIR, "ergebnis_co2.csv")

def export_results(df, path=EXPORT_CSV):
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"CSV exportiert nach: {path}")


# ---------------------------------------------------------
# Ende
# ---------------------------------------------------------