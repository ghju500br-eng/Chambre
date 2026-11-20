"""idealo.fr (comparateur) : récupère les offres des marchands référencés, dont Amazon et la Fnac.

idealo ne vend rien : une offre n'est retenue que si le marchand est une enseigne de la liste blanche
(Amazon, Fnac, Cdiscount, Micromania, Leclerc…). Les boutiques inconnues sont écartées.

Structure de la page (vérifiée le 20/11/2026) : chaque offre est un <li class="productOffers-listItem">
avec un attribut data-mtrx-click='{"shop_name": "...", "products": [{"price": 249.99, ...}]}'.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource

# Frais de port affichés comme « + 4,99 € frais de livraison ». Sans le « + », on ne devine pas
# (le prix de l'article est souvent juste avant le mot « Livraison »).
_RE_PORT = re.compile(r"\+\s*(\d+[.,]\d{2})\s?€\s*(?:de\s+)?(?:frais de (?:port|livraison)|livraison)", re.I)


def verifier(nav: Navigateur, url: str, edition: str) -> tuple[list[M.Offre], str]:
    rep = nav.get(url)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    offres, ecartees = analyser(rep.texte, url, edition)
    total = len(offres) + len(ecartees)
    detail = f"{total} offre(s), {len(offres)} chez des enseignes fiables"
    if ecartees:
        detail += " · écartées (marchand non vérifié) : " + ", ".join(sorted(set(ecartees)))
    return offres, detail[:200]


def analyser(page: str, url: str, edition: str) -> tuple[list[M.Offre], list[str]]:
    soup = BeautifulSoup(page, "lxml")
    lignes = []   # (marchand, prix, titre, texte de la ligne)
    for li in soup.select("li.productOffers-listItem"):
        try:
            data = json.loads(li.get("data-mtrx-click") or "{}")
        except Exception:
            data = {}
        marchand = str(data.get("shop_name") or "").strip()
        produits = data.get("products") or [{}]
        prix = F.lire_prix(produits[0].get("price"))
        if prix is None:
            lien = li.select_one("a[href*='relocator']")
            m = re.search(r"[?&]price=([\d.]+)", lien["href"]) if lien else None
            prix = F.lire_prix(m.group(1)) if m else None
        titre_el = li.select_one(".productOffers-listItemTitleInner")
        titre = (titre_el.get("title") or titre_el.get_text(" ", strip=True)) if titre_el else ""
        if marchand and prix is not None:
            lignes.append((marchand, prix, titre.replace("­", ""), li.get_text(" ", strip=True)))

    if not lignes:
        # Repli : encart "meilleur prix" en haut de page.
        boite = soup.select_one(".leadoutbox")
        if boite:
            marchand = boite.select_one(".leadoutbox-shop a")
            prix = boite.select_one(".leadoutbox-priceAmount")
            if marchand and prix and F.lire_prix(prix.get_text()):
                lignes.append((marchand.get_text(strip=True), F.lire_prix(prix.get_text()), "", boite.get_text(" ")))

    offres, ecartees = [], []
    for marchand, prix, titre, texte in lignes:
        if titre and not F.est_la_manette(titre):
            continue
        if not F.vendeur_est_enseigne(marchand):
            ecartees.append(marchand)
            continue
        if re.search(r"livraison gratuite|frais de (?:port|livraison) offerts", texte, re.I):
            port = 0.0
        else:
            mp = _RE_PORT.search(texte)
            port = F.lire_prix(mp.group(1)) if mp else None
            if port is not None and abs(port - prix) < 0.01:
                port = None
        marketplace = "marketplace" in marchand.lower()
        offres.append(M.Offre(
            site=f"idealo → {marchand}", edition=edition, titre=titre or "Manette DualSense GTA VI", url=url,
            prix=prix, livraison=port, disponible=True, etat_stock="En vente (selon idealo)", vendeur=marchand,
            confiance=M.MARKETPLACE if marketplace else M.ENSEIGNE, neuf=not F.est_occasion(texte[:300]),
            priorite_site=2, remarque="Prix relevé par idealo : vérifie sur le site du marchand avant de payer."))
    return offres, ecartees
