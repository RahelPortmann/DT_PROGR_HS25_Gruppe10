import ifcopenshell
import pandas as pd


# ==================================================
# Hilfsfunktion: Dichte bereinigen (MITTELWERT)
# ==================================================
def parse_density(value):
    """
    Wandelt KBOB-Dichtewerte um:
    - '32-160'  -> 96
    - '2300'    -> 2300
    - leer / NaN -> None
    """
    if pd.isna(value):
        return None

    value = str(value).strip()

    if "-" in value:
        try:
            a, b = value.split("-")
            return (float(a) + float(b)) / 2
        except:
            return None

    try:
        return float(value)
    except:
        return None


# ==================================================
# Volumen robust aus IFC lesen (WÄNDE + DECKEN)
# ==================================================
def get_volume(element):
    if not element.IsDefinedBy:
        return None

    for rel in element.IsDefinedBy:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue

        prop = rel.RelatingPropertyDefinition
        if not prop.is_a("IfcElementQuantity"):
            continue

        for q in prop.Quantities:
            if q.is_a("IfcQuantityVolume"):
                return q.VolumeValue

    return None


# ==================================================
# IFC Materialien + Volumen laden
# ==================================================
def load_ifc_materials(ifc_path):
    ifc = ifcopenshell.open(ifc_path)
    rows = []

    elements = (
        ifc.by_type("IfcWall")
        + ifc.by_type("IfcWallStandardCase")
        + ifc.by_type("IfcSlab")      # DECKEN
        + ifc.by_type("IfcRoof")
        + ifc.by_type("IfcBeam")
        + ifc.by_type("IfcColumn")
    )

    for element in elements:
        element_id = element.GlobalId
        ifc_type = element.is_a()

        # -------------------------
        # MATERIAL (ALLE IFC-FÄLLE)
        # -------------------------
        material = None

        if element.HasAssociations:
            for rel in element.HasAssociations:
                if not rel.is_a("IfcRelAssociatesMaterial"):
                    continue

                mat = rel.RelatingMaterial

                # 1) Einfaches Material
                if mat.is_a("IfcMaterial"):
                    material = mat.Name

                # 2) LayerSetUsage (typisch bei Slabs!)
                elif mat.is_a("IfcMaterialLayerSetUsage"):
                    layers = mat.ForLayerSet.MaterialLayers
                    if layers:
                        material = layers[0].Material.Name

                # 3) LayerSet
                elif mat.is_a("IfcMaterialLayerSet"):
                    layers = mat.MaterialLayers
                    if layers:
                        material = layers[0].Material.Name

        if not material:
            continue

        # -------------------------
        # VOLUMEN
        # -------------------------
        volume = get_volume(element)
        if volume is None:
            continue

        rows.append({
            "Element_ID": element_id,
            "Ifc_Typ": ifc_type,
            "Material_raw": material.strip(),
            "Menge": volume,
            "Einheit_IFC": "m3"
        })

    return pd.DataFrame(rows)


# ==================================================
# KBOB CSV laden + Dichte bereinigen
# ==================================================
def load_kbob(csv_path):
    df = pd.read_csv(csv_path)

    df["Material"] = df["Material"].astype(str).str.strip()
    df["Dichte"] = df["Dichte"].apply(parse_density)

    return df


# ==================================================
# 1:1 Mapping über Materialnamen
# ==================================================
def apply_mapping(df_ifc, kbob):
    return df_ifc.merge(
        kbob,
        left_on="Material_raw",
        right_on="Material",
        how="left"
    )


# ==================================================
# CO₂ Berechnung
# ==================================================
def merge_and_compute(mapped_df):
    df = mapped_df.copy()

    # Masse
    df["Masse_kg"] = df.apply(
        lambda r: r["Menge"] * r["Dichte"]
        if pd.notna(r["Dichte"])
        else None,
        axis=1
    )

    # CO₂
    df["CO2_total_kg"] = df.apply(
        lambda r:
            r["Masse_kg"] * r["CO2_Faktor"]
            if pd.notna(r["Masse_kg"]) and pd.notna(r["CO2_Faktor"])
            else None,
        axis=1
    )

    return df
