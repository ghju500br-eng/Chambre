"""PlayStation Direct / PlayStation Store : le vendeur officiel Sony (seul à vendre la noire en France)."""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource
from .fiche import analyser_fiche

# API de stock utilisée par les pages PlayStation Direct (on essaie plusieurs identifiants de boutique).
_API = "https://api.direct.playstation.com/commercewebservices/{base}/users/anonymous/products/productList"
_BASES = ["ps-direct-fr", "ps-direct-fr-fr", "ps-direct-eu"]

_RE_CODES = [
    re.compile(r'data-product-code="(\w+)"'),
    re.compile(r'"productCode"\s*:\s*"(\w+)"'),
    re.compile(r'data-sku="(\w+)"'),
    re.compile(r'"sku"\s*:\s*"(\w+)"'),
]


def verifier_fiche(nav: Navigateur, url: str, edition: str) -> tuple[list[M.Offre], str]:
    """Renvoie (offres, remarque). Une remarque non vide = info utile pour le bilan."""
    site = "PlayStation Store" if "store.playstation.com" in url else "PlayStation Direct"
    rep = nav.get(url)
    if "queue-it" in rep.url or "queue-it.net" in rep.texte[:5000]:
        # File d'attente virtuelle = Sony l'active pendant les grosses mises en vente.
        return [M.Offre(site=site, edition=edition, titre=f"Manette GTA VI {M.EDITIONS[edition]}", url=url,
                        prix=84.99, disponible=True, etat_stock="File d'attente active (vente en cours !)",
                        vendeur="Sony", confiance=M.OFFICIEL, priorite_site=1,
                        remarque="File d'attente PlayStation Direct active : une vente est probablement en cours.")], \
            "file d'attente active"
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)

    offres, _ = analyser_fiche(rep.texte, url, site=site, edition=edition, exiger_gta=True)
    for o in offres:
        o.confiance, o.vendeur, o.priorite_site = M.OFFICIEL, "Sony", 1
    if offres and any(o.etat_stock != "disponibilité inconnue" for o in offres):
        return offres, ""

    # Pas de données structurées exploitables : on interroge l'API de stock.
    code = next((m.group(1) for r in _RE_CODES for m in [r.search(rep.texte)] if m), None)
    if code:
        for base in _BASES:
            api = nav.get(_API.format(base=base), params={"fields": "BASIC", "productCodes": code},
                          json_attendu=True, essais=1, entetes={"Origin": "https://direct.playstation.com",
                                                               "Referer": url})
            if not api.ok:
                continue
            try:
                produit = (json.loads(api.texte).get("products") or [None])[0]
            except Exception:
                produit = None
            if not produit:
                continue
            statut = ((produit.get("stock") or {}).get("stockLevelStatus") or "").lower()
            prix = F.lire_prix((produit.get("price") or {}).get("value"))
            dispo = statut in ("instock", "lowstock")
            libelle = {"instock": "En stock", "lowstock": "Stock faible", "outofstock": "Rupture de stock"}.get(
                statut, statut or "inconnu")
            return [M.Offre(site=site, edition=edition, titre=produit.get("name") or f"Manette GTA VI {edition}",
                            url=url, prix=prix or 84.99, disponible=dispo, etat_stock=libelle, vendeur="Sony",
                            confiance=M.OFFICIEL, priorite_site=1)], ""

    # Dernier recours : lecture du texte de la page (moins fiable, on ne déclenche pas d'alerte dessus).
    soup = BeautifulSoup(rep.texte, "lxml")
    texte = F.normaliser(soup.get_text(" ", strip=True))
    prix = F.lire_prix(re.search(r"(\d{2,3},\d{2}) ?€", texte).group(1)) if re.search(r"(\d{2,3},\d{2}) ?€", texte) else None
    rupture = any(m in texte for m in ("actuellement indisponible", "rupture de stock", "epuise", "bientot disponible"))
    libelle = "Indisponible (lecture du texte)" if rupture else "État incertain (lecture du texte)"
    return [M.Offre(site=site, edition=edition, titre=f"Manette GTA VI {M.EDITIONS[edition]}", url=url,
                    prix=prix or 84.99, disponible=False, etat_stock=libelle, vendeur="Sony",
                    confiance=M.OFFICIEL, priorite_site=1,
                    remarque="Stock non confirmé par Sony : vérifie la page à la main si besoin.")], \
        "stock lu dans le texte (incertain)"

