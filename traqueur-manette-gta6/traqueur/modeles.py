"""Objets manipulés par le traqueur."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Niveaux de confiance des vendeurs, du plus sûr au moins sûr.
OFFICIEL = 1        # PlayStation Direct / Sony
ENSEIGNE = 2        # vendu ET expédié par l'enseigne elle-même (Amazon, Fnac, Micromania, Leclerc...)
MARKETPLACE = 3     # vendeur tiers sur une plateforme qui garantit le remboursement (Amazon, Fnac, Cdiscount)
EBAY_PRO = 4        # vendeur eBay très bien noté (garantie client eBay)

LIBELLE_CONFIANCE = {
    OFFICIEL: "Officiel Sony",
    ENSEIGNE: "Enseigne (vendu par le site)",
    MARKETPLACE: "Vendeur tiers garanti par le site",
    EBAY_PRO: "Vendeur eBay très bien noté",
}

EDITIONS = {"blanche": "Blanche", "noire": "Noire", "?": "Édition à confirmer"}


@dataclass
class Offre:
    site: str                 # "Amazon.fr", "Fnac", "PlayStation Direct", "eBay"...
    edition: str              # "blanche" | "noire" | "?"
    titre: str
    url: str
    prix: float | None        # prix de l'article en €
    livraison: float | None = 0.0   # frais de port en € (None = inconnus)
    disponible: bool = False  # commandable maintenant (en stock ou précommande ouverte)
    etat_stock: str = ""      # libellé brut : "En stock", "Précommande", "Rupture"...
    vendeur: str = ""
    confiance: int = ENSEIGNE
    neuf: bool = True
    remarque: str = ""
    priorite_site: int = 9    # 1 = site prioritaire (PS Direct, Amazon, Fnac)

    @property
    def total(self) -> float | None:
        if self.prix is None:
            return None
        return round(self.prix + (self.livraison or 0.0), 2)

    @property
    def cle(self) -> str:
        """Identifiant stable d'une offre (pour ne pas t'alerter 10 fois pour la même)."""
        base = self.url.split("?")[0].rstrip("/")
        return f"{self.site}|{self.edition}|{self.vendeur}|{base}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        return d


@dataclass
class ResultatSource:
    nom: str
    statut: str = "ok"        # ok | bloque | erreur | introuvable
    detail: str = ""
    offres: list[Offre] = field(default_factory=list)
    duree: float = 0.0
