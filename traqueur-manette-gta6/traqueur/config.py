"""Lecture de config.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    seuil_alerte: float = 100.0
    seuil_compromis: float = 110.0
    editions: list[str] = field(default_factory=lambda: ["blanche", "noire"])
    accepter_occasion: bool = False
    ebay_note_min: float = 98.0
    ebay_nb_eval_min: int = 100
    ebay_prix_min_credible: float = 55.0
    ebay_pays: list[str] = field(default_factory=list)
    amazon_europe: bool = True
    amazon_direct: bool = False
    ebay_direct: bool = False
    amazon_port_europe: float = 7.0
    bilan_horaire: bool = True
    heure_bilan_quotidien: int = 20
    fiches: list[dict] = field(default_factory=list)
    amazon_asins: list[dict] = field(default_factory=list)


def charger(chemin: Path | None = None) -> Config:
    chemin = chemin or RACINE / "config.toml"
    with open(chemin, "rb") as f:
        d = tomllib.load(f)
    o, e, a, b = d.get("objectif", {}), d.get("ebay", {}), d.get("amazon", {}), d.get("bilans", {})
    c = Config()
    c.seuil_alerte = float(o.get("seuil_alerte", c.seuil_alerte))
    c.seuil_compromis = float(o.get("seuil_compromis", c.seuil_compromis))
    c.editions = [x.lower() for x in o.get("editions", c.editions)]
    c.accepter_occasion = bool(o.get("accepter_occasion", c.accepter_occasion))
    c.ebay_note_min = float(e.get("note_min_pourcent", c.ebay_note_min))
    c.ebay_nb_eval_min = int(e.get("nb_evaluations_min", c.ebay_nb_eval_min))
    c.ebay_prix_min_credible = float(e.get("prix_min_credible", c.ebay_prix_min_credible))
    c.ebay_pays = list(e.get("pays_acceptes", []))
    c.amazon_europe = bool(a.get("surveiller_europe", c.amazon_europe))
    c.amazon_direct = bool(a.get("acces_direct", c.amazon_direct))
    c.ebay_direct = bool(e.get("acces_direct", c.ebay_direct))
    c.amazon_port_europe = float(a.get("port_estime_europe", c.amazon_port_europe))
    c.bilan_horaire = bool(b.get("bilan_horaire", c.bilan_horaire))
    c.heure_bilan_quotidien = int(b.get("heure_bilan_quotidien", c.heure_bilan_quotidien))
    c.fiches = list(d.get("fiches", []))
    c.amazon_asins = list(d.get("amazon_asin", []))
    return c
