#!/usr/bin/env python3
"""
ARTECI — Démonstration locale du moteur de normalisation des dates.

Ce script reproduit exactement ce que fait l'API en prenant le fichier CSV
fourni, en normalisant les colonnes de dates, et en affichant les résultats.

Utilisation :
    python demo_local.py

Aucun serveur MinIO requis — tout tourne en local.
"""

import io
import time
import sys
import pandas as pd
from pathlib import Path

# ── Ajout du répertoire parent au path pour importer app/ ─────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.services.date_service import normalize_date_columns

# ─────────────────────────────────────────────────────────────────────────────
# Configuration du fichier de test
# ─────────────────────────────────────────────────────────────────────────────

# Collez ici le chemin vers votre fichier CSV
# (le fichier lst_of_users_anon_1.csv du challenge)
CSV_PATH = "lst_of_users_anon_1.csv"

# Colonnes de dates identifiées dans le fichier
DATE_COLUMNS = ["DATE_CREATION", "DATE_DESACTIVATION"]
DATE_FORMATS = ["MDY", "MDY"]     # MDY = Mois/Jour/Année (format anglais)

# ─────────────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════════════╗
║          ARTECI — Démonstration Locale de Normalisation            ║
║          Format cible : JJ-MM-AAAA HH:mm:ss                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""


def print_section(title: str):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def run_demo():
    print(BANNER)

    # ── 1. Lecture du fichier ──────────────────────────────────────────────
    print_section("1. Lecture du fichier CSV")
    csv_path = Path(CSV_PATH)
    if not csv_path.exists():
        print(f"❌ Fichier introuvable : {CSV_PATH}")
        print("   → Placez le fichier lst_of_users_anon_1.csv dans le répertoire courant")
        print("     ou modifiez la variable CSV_PATH dans ce script.")
        sys.exit(1)

    content = csv_path.read_bytes()

    # Détection du séparateur
    sample = content[:4096].decode("utf-8", errors="replace")
    sep = ";" if sample.count(";") > sample.count(",") else ","

    df_original = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str,
                               keep_default_na=False, na_values=[""])

    print(f"  ✅ Fichier lu : {csv_path.name}")
    print(f"     Lignes    : {len(df_original):,}")
    print(f"     Colonnes  : {len(df_original.columns)}")
    print(f"     Séparateur: '{sep}'")
    print(f"\n  Colonnes disponibles :")
    for i, col in enumerate(df_original.columns, 1):
        print(f"     {i:2d}. {col}")

    # ── 2. Aperçu avant traitement ─────────────────────────────────────────
    print_section("2. Aperçu AVANT normalisation (5 premières lignes)")
    preview_cols = [c for c in DATE_COLUMNS if c in df_original.columns]
    if not preview_cols:
        print(f"  ⚠️  Colonnes {DATE_COLUMNS} absentes du fichier.")
        print(f"     Colonnes disponibles : {df_original.columns.tolist()}")
        # Tenter une détection automatique des colonnes de dates
        print("\n  → Tentative de détection automatique des colonnes de dates...")
        date_like = [
            col for col in df_original.columns
            if any(k in col.upper() for k in ["DATE", "TIME", "CREATION", "MODIF", "ACTIV"])
        ]
        if date_like:
            print(f"     Colonnes détectées : {date_like}")
            preview_cols = date_like
            global DATE_COLUMNS, DATE_FORMATS
            DATE_COLUMNS = date_like
            DATE_FORMATS = ["AUTO"] * len(date_like)
        else:
            print("  ❌ Aucune colonne de date détectée. Arrêt.")
            sys.exit(1)

    display_before = df_original[preview_cols].head(5)
    print(display_before.to_string(index=True))

    # ── 3. Normalisation ───────────────────────────────────────────────────
    print_section(f"3. Normalisation des colonnes {DATE_COLUMNS}")
    print(f"   Formats appliqués : {DATE_FORMATS}")
    print(f"   Format de sortie  : JJ-MM-AAAA HH:mm:ss")
    print(f"\n   Traitement en cours...")

    t0 = time.perf_counter()
    try:
        processed_bytes, preview, content_type = normalize_date_columns(
            content=content,
            file_path=csv_path.name,
            date_columns=DATE_COLUMNS,
            date_formats=DATE_FORMATS,
        )
    except Exception as e:
        print(f"\n  ❌ Erreur lors du traitement : {e}")
        sys.exit(1)

    elapsed = time.perf_counter() - t0

    # ── 4. Résultats ──────────────────────────────────────────────────────
    print_section("4. Résultats APRÈS normalisation (10 premières lignes)")
    df_result = pd.read_csv(io.BytesIO(processed_bytes), sep=sep, dtype=str,
                             keep_default_na=False, na_values=[""])

    display_after = df_result[DATE_COLUMNS].head(10)
    print(display_after.to_string(index=True))

    # ── 5. Statistiques ────────────────────────────────────────────────────
    print_section("5. Statistiques de traitement")
    for col in DATE_COLUMNS:
        if col not in df_result.columns:
            continue
        total = len(df_result[col])
        non_vide = df_result[col].notna() & (df_result[col].astype(str).str.strip() != "")
        # Détecter les valeurs normalisées (format JJ-MM-AAAA HH:mm:ss)
        normalized_mask = df_result[col].str.match(
            r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}$", na=False
        )
        n_normalized = normalized_mask.sum()
        n_non_vide = non_vide.sum()
        taux = (n_normalized / n_non_vide * 100) if n_non_vide > 0 else 0.0

        print(f"\n  Colonne : {col}  (format: {DATE_FORMATS[DATE_COLUMNS.index(col)]})")
        print(f"    Total de lignes      : {total:,}")
        print(f"    Valeurs non vides    : {n_non_vide:,}")
        print(f"    Valeurs normalisées  : {n_normalized:,}")
        print(f"    Taux de succès       : {taux:.1f}%")
        if n_non_vide - n_normalized > 0:
            # Afficher quelques valeurs non normalisées
            non_norm = df_result[col][non_vide & ~normalized_mask].head(3).tolist()
            print(f"    Exemples non normalisés : {non_norm}")

    print(f"\n  ⏱  Durée totale du traitement : {elapsed:.3f} secondes")
    print(f"  📄 Lignes traitées           : {len(df_result):,}")
    print(f"  📁 Taille du fichier traité  : {len(processed_bytes) / 1024:.1f} KB")

    # ── 6. Sauvegarde du fichier résultat ─────────────────────────────────
    output_path = Path(f"arteci_output_{csv_path.stem}.csv")
    output_path.write_bytes(processed_bytes)
    print(f"\n  💾 Fichier résultat sauvegardé : {output_path}")

    print_section("✅ Démonstration terminée avec succès")
    print("""
  Prochaines étapes :
    1. Démarrez l'API complète :  docker compose up --build
    2. Accédez à la doc Swagger :  http://localhost:8000/docs
    3. Appelez l'endpoint :        POST http://localhost:8000/processDate
    4. Consultez les traces :      http://localhost:4318 (OpenTelemetry)
    """)


if __name__ == "__main__":
    run_demo()
