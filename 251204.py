import os
import pandas as pd
import ifcopenshell
from ifcopenshell.util import element as ifc_element
import tkinter as tk
from tkinter import filedialog


# --------------------------------------------------------
# 1) IFC-Datei über Dialog auswählen
# --------------------------------------------------------
def select_ifc_file() -> str:
    """
    Öffnet ein Fenster, in dem du eine IFC-Datei auswählen kannst.
    Gibt den vollständigen Pfad zur ausgewählten Datei zurück.
    """
    root = tk.Tk()
    root.withdraw()  # Hauptfenster ausblenden

    file_path = filedialog.askopenfilename(
        title="IFC-Datei auswählen",
        filetypes=[("IFC-Dateien", "*.ifc"), ("Alle Dateien", "*.*")]
    )

    if not file_path:
        raise ValueError("Keine IFC-Datei ausgewählt!")

    print(f"Ausgewählte IFC-Datei:\n{file_path}\n")
    return file_path


# --------------------------------------------------------
# 2) KBOB-CSV laden
# --------------------------------------------------------
def load_kbob(path: str) -> pd.DataFrame:
    """
    Liest die KBOB-CSV.
    Erwartete Spalten: Material, Einheit, CO2_Faktor
    """
    df = pd.read_csv(path, encoding="utf-8")
    df["Material"] = df["Material"].astype(str).str.strip()
    return df


# --------------------------------------------------------
# 3) IFC-Modelldaten laden
# --------------------------------------------------------
def load_ifc_elements(ifc_path: str) -> pd.DataFrame:
    """
    Liest ein IFC-Modell und erzeugt einen DataFrame mit:
    - ElementGUID: GlobalId des Elements
    - ElementType: IFC-Typ, z.B. IfcWall
    - Material_raw: Name des Materials (aus IFC)
    - Menge: Volumen (NetVolume oder GrossVolume)
    - Einheit: "m3"

    Es werden typische Tragwerks-/Bauteil-Typen ausgewertet.
    """
    model = ifcopenshell.open(ifc_path)

    element_types = [
        "IfcWall",
        "IfcWallStandardCase",
        "IfcSlab",
        "IfcColumn",
        "IfcBeam",
        "IfcRoof",
        "IfcFooting",
    ]

    rows = []

    for etype in element_types:
        for elem in model.by_type(etype):

            # 3.1 Materialname holen
            mat_info = ifc_element.get_material(elem)
            if mat_info is None:
                mat_name = "UNBEKANNT"
            elif isinstance(mat_info, list):
                first = mat_info[0]
                mat_name = getattr(first, "Name", str(first))
            else:
                mat_name = getattr(mat_info, "Name", str(mat_info))

            mat_name = str(mat_name).strip()

            # 3.2 Mengen (Quantities) holen
            try:
                qtos = ifc_element.get_psets(elem, qtos_only=True)
            except Exception:
                qtos = {}

            volume = None
            for qto_name, qto_data in qtos.items():
                # erst NetVolume, dann GrossVolume
                if isinstance(qto_data, dict):
                    if "NetVolume" in qto_data:
                        volume = qto_data["NetVolume"]
                        break
                    if "GrossVolume" in qto_data:
                        volume = qto_data["GrossVolume"]
                        break

            # Wenn kein Volumen gefunden -> Element überspringen
            if volume is None:
                continue

            rows.append(
                {
                    "ElementGUID": elem.GlobalId,
                    "ElementType": etype,
                    "Material_raw": mat_name,
                    "Menge": float(volume),
                    "Einheit": "m3",
                }
            )

    df = pd.DataFrame(rows)
    return df


# --------------------------------------------------------
# 4) Mapping auf KBOB-Materialnamen
# --------------------------------------------------------
def build_mapping() -> dict:
    """
    Mapping von IFC-Materialnamen auf KBOB-Materialnamen.
    Hier kannst du einfach ergänzen, wenn du andere Namen hast.
    """
    return {
        "Concrete": "Beton",
        "Beton": "Beton",
        "C30/37": "Beton",
        "C25/30": "Beton",

        "Steel": "Stahl",
        "Stahl": "Stahl",
        "Reinforcement": "Stahl",

        "Timber": "Holz",
        "Wood": "Holz",
        "Holz": "Holz",
    }


def apply_mapping(df_ifc: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Wendet das Mapping auf die Spalte Material_raw an
    und schreibt das Ergebnis in eine neue Spalte Material.
    """
    df = df_ifc.copy()
    df["Material"] = df["Material_raw"].map(mapping).fillna(df["Material_raw"])
    return df


# --------------------------------------------------------
# 5) Merge mit KBOB + CO2-Berechnung
# --------------------------------------------------------
def merge_and_compute(df_ifc: pd.DataFrame, df_kbob: pd.DataFrame) -> pd.DataFrame:
    """
    Verknüpft IFC-Daten mit KBOB-Tabelle über Material
    und berechnet CO2_total_kg = Menge * CO2_Faktor
    """
    merged = pd.merge(df_ifc, df_kbob, on="Material", how="left")

    # Falls einige Materialien keinen KBOB-Eintrag haben:
    if merged["CO2_Faktor"].isna().any():
        print("\nWARNUNG: Für einige Materialien wurde kein CO2_Faktor gefunden:")
        print(merged[merged["CO2_Faktor"].isna()][["Material"]].drop_duplicates().to_string(index=False))

    merged["CO2_total_kg"] = merged["Menge"] * merged["CO2_Faktor"]
    return merged


# --------------------------------------------------------
# 6) Export
# --------------------------------------------------------
def export_results(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"\nErgebnis als CSV exportiert nach:\n{path}")


# --------------------------------------------------------
# 7) Hauptprogramm
# --------------------------------------------------------
if __name__ == "__main__":

    # 7.1 IFC-Datei auswählen
    ifc_path = select_ifc_file()

    # 7.2 Pfad zur KBOB-CSV setzen
    # Annahme: Deine kbob_materialien.csv liegt im Unterordner "data" neben dieser Datei.
    SCRIPT_DIR = os.path.dirname(__file__)
    DATA_DIR = os.path.join(SCRIPT_DIR, "data")
    KBOB_CSV = os.path.join(DATA_DIR, "kbob_materialien.csv")

    if not os.path.exists(KBOB_CSV):
        raise FileNotFoundError(f"KBOB-CSV nicht gefunden unter:\n{KBOB_CSV}")

    kbob = load_kbob(KBOB_CSV)
    print("KBOB-Daten (Vorschau):")
    print(kbob.head().to_string(index=False))

    # 7.3 IFC-Daten einlesen
    ifc_df = load_ifc_elements(ifc_path)
    print("\nIFC-Rohdaten (erste Zeilen):")
    print(ifc_df.head().to_string(index=False))

    # 7.4 Mapping anwenden
    mapping = build_mapping()
    mapped_df = apply_mapping(ifc_df, mapping)
    print("\nIFC mit gemappten KBOB-Materialnamen (erste Zeilen):")
    print(mapped_df.head().to_string(index=False))

    # 7.5 Merge + CO2-Berechnung
    result = merge_and_compute(mapped_df, kbob)
    print("\nErgebnis (erste Zeilen):")
    print(result.head().to_string(index=False))

    # 7.6 Summen pro Material
    summe = (
        result.groupby("Material", as_index=False)["CO2_total_kg"]
        .sum()
        .sort_values("CO2_total_kg", ascending=False)
    )
    print("\nCO2-Summe pro Material:")
    print(summe.to_string(index=False))

    # 7.7 Export
    EXPORT_CSV = os.path.join(DATA_DIR, "ergebnis_co2.csv")
    export_results(result, EXPORT_CSV)

    print("\nFERTIG ✔️")








