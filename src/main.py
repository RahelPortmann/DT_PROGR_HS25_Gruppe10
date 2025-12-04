# 1) KBOB-CSV laden
import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
KBOB_CSV = os.path.join(DATA_DIR, "kbob_materialien.csv")

def load_kbob(path: str) -> pd.DataFrame:
    """
    Liest die KBOB-CSV.
    Erwartete Spalten: Material, Einheit, CO2_Faktor
    """
    df = pd.read_csv(path, encoding="utf-8")
    df["Material"] = df["Material"].astype(str).str.strip()
    return df

# Testaufruf
if __name__ == "__main__":
    kbob = load_kbob(KBOB_CSV)
    print("KBOB Vorschau:")
    print(kbob.head().to_string(index=False))

# 2) Testdaten (Material + Menge) vorbereiten
def make_demo_ifc_like() -> pd.DataFrame:
    """
    Simuliert das Ergebnis eines IFC-Imports.
    Spalten: Material_raw, Menge, Einheit
    """
    return pd.DataFrame([
        {"Material_raw": "Beton", "Menge": 2.5, "Einheit": "m3"},
        {"Material_raw": "Stahl", "Menge": 120.0, "Einheit": "kg"},
        {"Material_raw": "Holz",  "Menge": 0.8, "Einheit": "m3"},
    ])

if __name__ == "__main__":
    demo = make_demo_ifc_like()
    print("\nDemo-Daten:")
    print(demo.to_string(index=False))

# 3) Mapping auf KBOB-Materialnamen
def build_mapping() -> dict:
    return {
        "Concrete": "Beton",
        "Beton": "Beton",
        "Steel": "Stahl",
        "Stahl": "Stahl",
        "Timber": "Holz",
        "Wood": "Holz",
    }

def apply_mapping(df_ifc: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    df = df_ifc.copy()
    df["Material"] = df["Material_raw"].map(mapping).fillna(df["Material_raw"])
    return df

if __name__ == "__main__":
    mapping = build_mapping()
    demo_mapped = apply_mapping(make_demo_ifc_like(), mapping)
    print("\nDemo mit Mapping:")
    print(demo_mapped.to_string(index=False))

    # 4) Merge + Berechnung
def merge_and_compute(df_ifc: pd.DataFrame, df_kbob: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(df_ifc, df_kbob, on="Material", how="left")
    merged["CO2_total_kg"] = merged["Menge"] * merged["CO2_Faktor"]
    return merged

if __name__ == "__main__":
    kbob = load_kbob(KBOB_CSV)
    mapping = build_mapping()
    ifc_like = apply_mapping(make_demo_ifc_like(), mapping)
    result = merge_and_compute(ifc_like, kbob)

    print("\nErgebnis (erste Zeilen):")
    print(result.head().to_string(index=False))

    summe = result.groupby("Material", as_index=False)["CO2_total_kg"].sum() \
                  .sort_values("CO2_total_kg", ascending=False)
    print("\nSumme pro Material:")
    print(summe.to_string(index=False))

    # 5) Export
EXPORT_CSV = os.path.join(DATA_DIR, "ergebnis_co2.csv")

def export_results(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"\nCSV exportiert: {path}")

if __name__ == "__main__":
    # … result wie oben berechnet
    export_results(result, EXPORT_CSV)