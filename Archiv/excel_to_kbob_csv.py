# -*- coding: utf-8 -*-
# KBOB Excel → bereinigte CSV

import pandas as pd
import os

# ---------------------------------------------------------
# 1) Excel-Datei laden
# ---------------------------------------------------------

# ⚠️ Achtung: Im Dateinamen ist ein Leerzeichen nach dem Unterstrich!
FILE = "Oekobilanzdaten_ Baubereich_Donne_ecobilans_construction_2009-1-2022_v7.0.xlsx"

# Tabellenblatt mit den Materialien
SHEET = "Baumaterialien Matériaux"

# Ausgabe-Ziel
OUTPUT = "data/kbob_materialien.csv"

print("📄 Lade KBOB Excel-Datei...")

try:
    df = pd.read_excel(FILE, sheet_name=SHEET)
except Exception as e:
    print("❌ Fehler beim Laden der Datei oder Sheet:")
    print(e)
    quit()

print("✔️ Datei erfolgreich geladen!")


# ---------------------------------------------------------
# 2) Benötigte Spalten extrahieren
#    A, C, F, G, Z → Index 0, 2, 5, 6, 25
# ---------------------------------------------------------

COLUMNS = [0, 2, 5, 6, 25]

df_clean = df.iloc[:, COLUMNS]

df_clean.columns = [
    "Material_ID",   # Spalte A
    "Material",      # Spalte C
    "Dichte",        # Spalte F
    "Einheit",       # Spalte G
    "CO2_Faktor"     # Spalte Z
]


# ---------------------------------------------------------
# 3) Leere oder ungültige Zeilen entfernen
# ---------------------------------------------------------

df_clean = df_clean.dropna(subset=["Material"])
df_clean = df_clean[df_clean["Material"].astype(str).str.strip() != ""]


# ---------------------------------------------------------
# 4) Zahlen korrekt konvertieren
# ---------------------------------------------------------

df_clean["Dichte"] = pd.to_numeric(df_clean["Dichte"], errors="coerce")
df_clean["CO2_Faktor"] = pd.to_numeric(df_clean["CO2_Faktor"], errors="coerce")


# ---------------------------------------------------------
# 5) Als CSV speichern
# ---------------------------------------------------------

os.makedirs("data", exist_ok=True)

df_clean.to_csv(OUTPUT, index=False, encoding="utf-8")

print("\n🎉 FERTIG!")
print("Die bereinigte KBOB-Datei wurde gespeichert unter:")
print(f"➡️ {OUTPUT}")