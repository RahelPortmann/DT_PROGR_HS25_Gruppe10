# -*- coding: utf-8 -*-
# KBOB Excel → bereinigte CSV (MIT DICHTE-MITTELWERT)

import pandas as pd
import os
import re


# ---------------------------------------------------------
# 1) Excel-Datei laden
# ---------------------------------------------------------

FILE = "Oekobilanzdaten_ Baubereich_Donne_ecobilans_construction_2009-1-2022_v7.0.xlsx"
SHEET = "Baumaterialien Matériaux"
OUTPUT = "data/kbob_materialien.csv"

print("📄 Lade KBOB Excel-Datei...")

df = pd.read_excel(FILE, sheet_name=SHEET)
print("✔️ Datei erfolgreich geladen!")


# ---------------------------------------------------------
# 2) Benötigte Spalten extrahieren
# ---------------------------------------------------------

COLUMNS = [0, 2, 5, 6, 25]

df_clean = df.iloc[:, COLUMNS]

df_clean.columns = [
    "Material_ID",
    "Material",
    "Dichte_raw",
    "Einheit",
    "CO2_Faktor"
]


# ---------------------------------------------------------
# 3) Leere Zeilen entfernen
# ---------------------------------------------------------

df_clean = df_clean.dropna(subset=["Material"])
df_clean["Material"] = df_clean["Material"].astype(str).str.strip()
df_clean = df_clean[df_clean["Material"] != ""]


# ---------------------------------------------------------
# 4) Dichte korrekt parsen (MITTELWERT!)
# ---------------------------------------------------------

def parse_density(value):
    """
    - '32-160'  -> 96
    - '100–165' -> 132.5
    - '2300'    -> 2300
    """
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = value.replace("–", "-")  # langer Gedankenstrich

    # Bereich
    if "-" in value:
        try:
            a, b = value.split("-")
            return (float(a) + float(b)) / 2
        except:
            return None

    # Einzelwert
    try:
        return float(value)
    except:
        return None


df_clean["Dichte"] = df_clean["Dichte_raw"].apply(parse_density)


# ---------------------------------------------------------
# 5) CO₂-Faktor numerisch machen
# ---------------------------------------------------------

df_clean["CO2_Faktor"] = pd.to_numeric(df_clean["CO2_Faktor"], errors="coerce")


# ---------------------------------------------------------
# 6) Aufräumen & speichern
# ---------------------------------------------------------

df_clean = df_clean.drop(columns=["Dichte_raw"])

os.makedirs("data", exist_ok=True)
df_clean.to_csv(OUTPUT, index=False, encoding="utf-8")

print("\n🎉 FERTIG!")
print("➡️ KBOB CSV mit Dichte-Mittelwert gespeichert:")
print(OUTPUT)