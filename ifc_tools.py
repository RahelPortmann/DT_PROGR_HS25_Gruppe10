import re
import pandas as pd
import ifcopenshell

# Optional: Geometrie-Engine (für Volumen von IfcBuildingElementPart)
try:
    import ifcopenshell.geom
    _HAS_GEOM = True
except Exception:
    _HAS_GEOM = False


# ==================================================
# KBOB: Dichte robust parsen
# ==================================================
def parse_density(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = value.replace("–", "-").replace("—", "-")

    m = re.match(r"^\s*(\d+(\.\d+)?)\s*-\s*(\d+(\.\d+)?)\s*$", value)
    if m:
        return (float(m.group(1)) + float(m.group(3))) / 2

    try:
        return float(value)
    except Exception:
        return None


# ==================================================
# Text-Normalisierung fürs Mapping
# ==================================================
_UMLAUTS = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue"
})

def normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().translate(_UMLAUTS).lower()
    s = s.replace(",", " ").replace("|", " ").replace("/", " ").replace(";", " ")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def token_set(s: str) -> set:
    s = normalize_text(s)
    if not s:
        return set()
    return set(s.split())

def token_similarity(a: str, b: str) -> float:
    """
    Robuster Score (0..100) basierend auf Token-Overlap.
    """
    A = token_set(a)
    B = token_set(b)
    if not A or not B:
        return 0.0

    inter = len(A & B)
    union = len(A | B)
    jaccard = inter / union  # 0..1

    subset_bonus = 0.10 if (A <= B or B <= A) else 0.0
    score = (jaccard + subset_bonus) * 100.0
    return min(100.0, score)

def expand_query(raw: str) -> str:
    """
    Heuristiken/Synonyme: macht Material_raw "kbob-freundlicher".
    """
    r = normalize_text(raw)

    replacements = [
        ("stahlbeton", "beton stahlbeton"),
        ("beton", "beton"),
        ("mw", "mauerwerk"),
        ("backstein", "ziegel backstein"),
        ("ziegel", "ziegel backstein"),
        ("daemmung", "daemmung mineralwolle steinwolle"),
        ("steinwolle", "steinwolle mineralwolle"),
        ("mineralwolle", "mineralwolle steinwolle"),
        ("trittschall", "trittschall daemmung"),
        ("unterlagsboden", "unterlagsboden estrich"),
        ("estrich", "unterlagsboden estrich"),
        ("belag", "bodenbelag"),
        ("bodenbelag", "bodenbelag"),
        ("vollholzwerkstoff", "holz vollholz holzwerkstoff"),
        ("vollholz", "holz vollholz"),
        ("sperrschicht", "sperrschicht dampfbremse"),
        ("dampfbremse", "dampfbremse sperrschicht"),
        ("dachbekleidung", "dachbekleidung"),
    ]

    for src, dst in replacements:
        if src in r:
            r = r.replace(src, dst)

    return r.strip()


# ==================================================
# IFC: Volumen aus Quantities
# ==================================================
def get_volume_from_quantities(element):
    if not getattr(element, "IsDefinedBy", None):
        return None

    for rel in element.IsDefinedBy:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue

        prop = rel.RelatingPropertyDefinition
        if not prop or not prop.is_a("IfcElementQuantity"):
            continue

        for q in prop.Quantities:
            if q.is_a("IfcQuantityVolume"):
                return q.VolumeValue

    return None


# ==================================================
# IFC: Volumen aus Geometrie (Mesh) - Fallback
# ==================================================
def _mesh_volume(verts, faces):
    V = [(verts[i], verts[i+1], verts[i+2]) for i in range(0, len(verts), 3)]
    vol = 0.0
    for i in range(0, len(faces), 3):
        a = V[faces[i]]
        b = V[faces[i+1]]
        c = V[faces[i+2]]
        vol += (
            a[0] * (b[1]*c[2] - b[2]*c[1]) -
            a[1] * (b[0]*c[2] - b[2]*c[0]) +
            a[2] * (b[0]*c[1] - b[1]*c[0])
        )
    return abs(vol) / 6.0

def get_volume_from_geometry(ifc, element):
    if not _HAS_GEOM:
        return None

    try:
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        shape = ifcopenshell.geom.create_shape(settings, element)
        geom = shape.geometry

        verts = list(geom.verts)
        faces = list(geom.faces)

        if not verts or not faces:
            return None

        return _mesh_volume(verts, faces)
    except Exception:
        return None

def get_volume(ifc, element):
    v = get_volume_from_quantities(element)
    if v is not None:
        return float(v)
    return get_volume_from_geometry(ifc, element)


# ==================================================
# IFC: Material Associations lesen
# ==================================================
def _layers_from_relating_material(mat):
    if mat.is_a("IfcMaterial") and getattr(mat, "Name", None):
        return [{"name": mat.Name, "thickness": None}]

    if mat.is_a("IfcMaterialLayerSetUsage"):
        layers = mat.ForLayerSet.MaterialLayers
        out = []
        for layer in layers:
            name = layer.Material.Name if layer.Material and getattr(layer.Material, "Name", None) else None
            thk = getattr(layer, "LayerThickness", None)
            if name:
                out.append({"name": name, "thickness": thk})
        return out if out else None

    if mat.is_a("IfcMaterialLayerSet"):
        layers = mat.MaterialLayers
        out = []
        for layer in layers:
            name = layer.Material.Name if layer.Material and getattr(layer.Material, "Name", None) else None
            thk = getattr(layer, "LayerThickness", None)
            if name:
                out.append({"name": name, "thickness": thk})
        return out if out else None

    return None

def get_material_layers(element):
    if getattr(element, "HasAssociations", None):
        for rel in element.HasAssociations:
            if not rel.is_a("IfcRelAssociatesMaterial"):
                continue
            layers = _layers_from_relating_material(rel.RelatingMaterial)
            if layers:
                return layers
    return []


# ==================================================
# IFC: Decomposition -> Parts
# ==================================================
def get_decomposed_parts(element):
    parts = []
    if getattr(element, "IsDecomposedBy", None):
        for rel in element.IsDecomposedBy:
            if not rel.is_a("IfcRelAggregates"):
                continue
            for obj in rel.RelatedObjects:
                parts.append(obj)
    return parts


# ==================================================
# IFC Load: Materialien + Volumen
# ==================================================
def load_ifc_materials(ifc_path):
    ifc = ifcopenshell.open(ifc_path)
    rows = []
    seen = set()  # (Element_ID, Material_raw, Menge)

    elements = (
        ifc.by_type("IfcWall")
        + ifc.by_type("IfcSlab")
        + ifc.by_type("IfcRoof")
        + ifc.by_type("IfcBeam")
        + ifc.by_type("IfcColumn")
    )

    for element in elements:
        parent_id = element.GlobalId
        ifc_type = element.is_a()

        parts = get_decomposed_parts(element)
        parts = [p for p in parts if p.is_a("IfcBuildingElementPart")]

        # Fall: Archicad "exploded" -> Parts auswerten
        if parts:
            for p in parts:
                layers = get_material_layers(p)

                if not layers:
                    pname = (getattr(p, "Name", None) or "").strip()
                    if pname:
                        layers = [{"name": pname, "thickness": None}]

                if not layers:
                    continue

                v_part = get_volume(ifc, p)
                if v_part is None:
                    v_parent = get_volume(ifc, element)
                    if v_parent is None:
                        continue
                    v_part = float(v_parent) / len(parts)

                # Layer-Aufteilung innerhalb des Parts
                if len(layers) > 1:
                    thks = [l["thickness"] for l in layers if l.get("thickness") is not None]
                    t_sum = sum(thks) if thks else None

                    if not t_sum or t_sum == 0:
                        share = float(v_part) / len(layers)
                        for l in layers:
                            name = str(l["name"]).strip()
                            vol = float(share)
                            key = (p.GlobalId, name, vol)
                            if key in seen:
                                continue
                            seen.add(key)
                            rows.append({
                                "Element_ID": p.GlobalId,
                                "Parent_ID": parent_id,
                                "Ifc_Typ": p.is_a(),
                                "Material_raw": name,
                                "Menge": vol,
                                "Einheit_IFC": "m3"
                            })
                    else:
                        for l in layers:
                            name = str(l["name"]).strip()
                            t = float(l["thickness"]) if l.get("thickness") is not None else 0.0
                            vol = float(v_part) * (t / t_sum)
                            key = (p.GlobalId, name, vol)
                            if key in seen:
                                continue
                            seen.add(key)
                            rows.append({
                                "Element_ID": p.GlobalId,
                                "Parent_ID": parent_id,
                                "Ifc_Typ": p.is_a(),
                                "Material_raw": name,
                                "Menge": vol,
                                "Einheit_IFC": "m3"
                            })
                else:
                    name = str(layers[0]["name"]).strip()
                    vol = float(v_part)
                    key = (p.GlobalId, name, vol)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "Element_ID": p.GlobalId,
                        "Parent_ID": parent_id,
                        "Ifc_Typ": p.is_a(),
                        "Material_raw": name,
                        "Menge": vol,
                        "Einheit_IFC": "m3"
                    })

            continue

        # Normaler Fall: Material am Element
        v_total = get_volume(ifc, element)
        if v_total is None:
            continue

        layers = get_material_layers(element)

        if not layers:
            fallback = (getattr(element, "Name", None) or "").strip()
            if fallback:
                layers = [{"name": fallback, "thickness": None}]
            else:
                continue

        if len(layers) > 1:
            thks = [l["thickness"] for l in layers if l.get("thickness") is not None]
            t_sum = sum(thks) if thks else None

            if not t_sum or t_sum == 0:
                share = float(v_total) / len(layers)
                for l in layers:
                    name = str(l["name"]).strip()
                    vol = float(share)
                    key = (parent_id, name, vol)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "Element_ID": parent_id,
                        "Parent_ID": parent_id,
                        "Ifc_Typ": ifc_type,
                        "Material_raw": name,
                        "Menge": vol,
                        "Einheit_IFC": "m3"
                    })
            else:
                for l in layers:
                    name = str(l["name"]).strip()
                    t = float(l["thickness"]) if l.get("thickness") is not None else 0.0
                    vol = float(v_total) * (t / t_sum)
                    key = (parent_id, name, vol)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "Element_ID": parent_id,
                        "Parent_ID": parent_id,
                        "Ifc_Typ": ifc_type,
                        "Material_raw": name,
                        "Menge": vol,
                        "Einheit_IFC": "m3"
                    })
        else:
            name = str(layers[0]["name"]).strip()
            vol = float(v_total)
            key = (parent_id, name, vol)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "Element_ID": parent_id,
                "Parent_ID": parent_id,
                "Ifc_Typ": ifc_type,
                "Material_raw": name,
                "Menge": vol,
                "Einheit_IFC": "m3"
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["Element_ID", "Parent_ID", "Ifc_Typ", "Material_raw", "Menge", "Einheit_IFC"])

    df = df.drop_duplicates(subset=["Element_ID", "Material_raw", "Menge"], keep="first").reset_index(drop=True)
    return df


# ==================================================
# KBOB CSV laden + "gültige" Zeilen filtern
# ==================================================
def _is_heading_id(material_id) -> bool:
    if material_id is None or pd.isna(material_id):
        return True
    s = str(material_id).strip()
    if s.isdigit() and len(s) <= 2:
        return True
    return False

def load_kbob(csv_path):
    df = pd.read_csv(csv_path)

    df["Material"] = df["Material"].astype(str).str.strip()
    df["Dichte"] = df["Dichte"].apply(parse_density)
    df["CO2_Faktor"] = pd.to_numeric(df["CO2_Faktor"], errors="coerce")

    if "Material_ID" in df.columns:
        df = df[~df["Material_ID"].apply(_is_heading_id)].copy()

    df = df[df["Material"].notna() & (df["Material"].astype(str).str.strip() != "")].copy()

    return df.reset_index(drop=True)


# ==================================================
# Mapping-Regeln: Blacklist + Specials
# ==================================================
_BLACKLIST_KBOB_KEYWORDS = [
    "tuer", "tuere", "tür", "fenster", "verglas", "rahmen", "beschlag"
]

def _is_blacklisted_kbob_material(mat_name: str) -> bool:
    m = normalize_text(mat_name)
    return any(k in m for k in _BLACKLIST_KBOB_KEYWORDS)

def _is_air_material(raw_name: str) -> bool:
    r = normalize_text(raw_name)
    return "luft" in r


# ==================================================
# Auto-Mapping: Kandidaten + Best-Match
# ==================================================
def suggest_kbob_candidates(raw_name: str, kbob_df: pd.DataFrame, top_n: int = 10):
    if _is_air_material(raw_name):
        return []

    query = expand_query(raw_name)

    candidates = []
    for _, row in kbob_df.iterrows():
        mat = row["Material"]
        if _is_blacklisted_kbob_material(mat):
            continue

        score = token_similarity(query, mat)
        if score <= 0:
            continue
        candidates.append((mat, score, row.get("Material_ID", None)))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]


def apply_mapping(df_ifc: pd.DataFrame, kbob_df: pd.DataFrame, min_score: float = 18.0):
    unique_raw = sorted(df_ifc["Material_raw"].dropna().unique().tolist())

    best_map = {}
    score_map = {}

    for raw in unique_raw:
        if _is_air_material(raw):
            best_map[raw] = None
            score_map[raw] = 0.0
            continue

        cands = suggest_kbob_candidates(raw, kbob_df, top_n=1)
        if cands:
            best_mat, best_score, _ = cands[0]
            if best_score >= min_score:
                best_map[raw] = best_mat
                score_map[raw] = best_score
            else:
                best_map[raw] = None
                score_map[raw] = best_score
        else:
            best_map[raw] = None
            score_map[raw] = 0.0

    df = df_ifc.copy()
    df["KBOB_best"] = df["Material_raw"].map(best_map)
    df["Match_score"] = df["Material_raw"].map(score_map)

    mapped = df.merge(
        kbob_df,
        left_on="KBOB_best",
        right_on="Material",
        how="left",
        suffixes=("", "_kbob")
    )

    return mapped


# ==================================================
# CO₂ Berechnung
# ==================================================
def merge_and_compute(mapped_df):
    df = mapped_df.copy()

    df["Masse_kg"] = df.apply(
        lambda r: r["Menge"] * r["Dichte"] if pd.notna(r.get("Dichte")) else None,
        axis=1
    )

    df["CO2_total_kg"] = df.apply(
        lambda r: r["Masse_kg"] * r["CO2_Faktor"]
        if pd.notna(r.get("Masse_kg")) and pd.notna(r.get("CO2_Faktor"))
        else None,
        axis=1
    )

    return df


