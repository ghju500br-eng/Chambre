"""Mémoire du traqueur entre deux vérifications (fichiers versionnés dans le repo)."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import RACINE

PARIS = ZoneInfo("Europe/Paris")
DOSSIER = RACINE / "etat"
FICHIER_ETAT = DOSSIER / "etat.json"
FICHIER_HISTO = DOSSIER / "historique.csv"
COLONNES_HISTO = ["date", "edition", "meilleur_dispo", "site", "vendeur", "nb_offres_dispo",
                  "sources_ok", "sources_total"]


def maintenant() -> datetime:
    return datetime.now(PARIS)


def charger() -> dict:
    if FICHIER_ETAT.exists():
        try:
            return json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def sauver(etat: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER_ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def ajouter_historique(lignes: list[dict]) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    nouveau = not FICHIER_HISTO.exists()
    with open(FICHIER_HISTO, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES_HISTO)
        if nouveau:
            w.writeheader()
        for l in lignes:
            w.writerow({k: l.get(k, "") for k in COLONNES_HISTO})


def lire_historique() -> list[dict]:
    if not FICHIER_HISTO.exists():
        return []
    with open(FICHIER_HISTO, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
