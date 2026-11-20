"""idealo.fr (comparateur) : récupère les offres des marchands référencés, dont Amazon et la Fnac.

idealo ne vend rien : une offre n'est retenue que si le marchand est une enseigne de la liste blanche
(Amazon, Fnac, Micromania, Leclerc…). Les petites boutiques inconnues sont écartées.
"""
from __future__ import annotations

import html as html_lib
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource

# Noms de champs possibles pour le marchand dans les données de la page (format variable).
_RE_SHOP = [
    re.compile(r'"shopName"\s*:\s*(?:\[\s*0\s*,\s*)?"([^"]{2,60})"'),
    re.compile(r'"shop_name"\s*:\s*(?:\[\s*0\s*,\s*)?"([^"]{2,60})"'),
    re.compile(r'"merchantName"\s*:\s*(?:\[\s*0\s*,\s*)?"([^"]{2,60})"'),
    re.compile(r'data-shop-name="([^"]{2,60})"'),
    re.compile(r'Marchand\s*:?\s*(?:<[^>]+>\s*)*([^<]{2,60})<'),
    re.compile(r'Vendu par\s*:?\s*(?:<[^>]+>\s*)*([^<]{2,60})<'),
]
_RE_PORT = re.compile(r'(?:"shippingCosts?"|"deliveryCosts?")\s*:\s*(?:\[\s*0\s*,\s*)?"?([\d.,]+)')


def verifier(nav: Navigateur, url: str, edition: str) -> tuple[list[M.Offre], str]:
    rep = nav.get(url)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    offres, ecartees, marchands = analyser(rep.texte, url, edition)
    detail = f"{len(offres) + len(ecartees)} offre(s) : {len(offres)} chez des enseignes fiables"
    if ecartees:
        detail += " · écartées (marchand non vérifié) : " + ", ".join(sorted(set(ecartees)))[:120]
    return offres, detail


def analyser(page: str, url: str, edition: str) -> tuple[list[M.Offre], list[str], dict]:
    soup = BeautifulSoup(page, "lxml")
    brut = html_lib.unescape(page)
    vues: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        if "relocator" not in a["href"]:
            continue
        q = parse_qs(urlparse(a["href"]).query)
        cle = (q.get("offerKey") or [""])[0]
        prix = F.lire_prix((q.get("price") or [""])[0])
        if not cle or prix is None:
            continue
        o = vues.setdefault(cle, {"prix": prix, "titre": "", "marchand": ""})
        texte = a.get_text(" ", strip=True).replace("­", "")
        classes = " ".join(a.get("class") or [])
        parent_classes = " ".join(a.parent.get("class") or []) if a.parent else ""
        if "shop" in classes.lower() or "shop" in parent_classes.lower():
            o["marchand"] = o["marchand"] or texte
        elif len(texte) > len(o["titre"]) and not re.fullmatch(r"[\d\s,.€]+", texte) and "Voir" not in texte:
            o["titre"] = texte

    # Marchand manquant : on le cherche dans les données autour de l'identifiant de l'offre.
    for cle, o in vues.items():
        if o["marchand"]:
            continue
        for m in re.finditer(re.escape(cle), brut):
            zone = brut[max(0, m.start() - 2500):m.end() + 2500]
            for r in _RE_SHOP:
                t = r.search(zone)
                if t and t.group(1).strip():
                    o["marchand"] = t.group(1).strip()
                    break
            if o["marchand"]:
                mp = _RE_PORT.search(zone)
                o["port"] = F.lire_prix(mp.group(1)) if mp else None
                break

    offres, ecartees = [], []
    for o in vues.values():
        marchand = o["marchand"] or "marchand inconnu"
        if o["titre"] and not F.est_la_manette(o["titre"]):
            continue
        if not F.vendeur_est_enseigne(marchand):
            ecartees.append(marchand)
            continue
        marketplace = "marketplace" in marchand.lower() or "vendeur tiers" in marchand.lower()
        offres.append(M.Offre(
            site=f"idealo → {marchand}", edition=edition, titre=o["titre"] or "Manette GTA VI", url=url,
            prix=o["prix"], livraison=o.get("port"), disponible=True, etat_stock="En vente (selon idealo)",
            vendeur=marchand, confiance=M.MARKETPLACE if marketplace else M.ENSEIGNE, priorite_site=2,
            remarque="Prix relevé par idealo : vérifie sur le site du marchand avant de payer."))
    return offres, ecartees, vues
