"""Dealabs : la communauté française repère les retours en stock en quelques minutes.

On ne s'en sert que comme signal : un deal n'est retenu que si le marchand est une enseigne fiable.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import time

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource

URL = "https://www.dealabs.com/search"
FRAICHEUR_MAX_H = 48


def rechercher(nav: Navigateur) -> list[M.Offre]:
    rep = nav.get(URL, params={"q": "dualsense gta"})
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    return analyser(rep.texte)


def analyser(page: str) -> list[M.Offre]:
    soup = BeautifulSoup(page, "lxml")
    threads: dict[str, dict] = {}
    for el in soup.select("[data-vue3], [data-vue2]"):
        brut = el.get("data-vue3") or el.get("data-vue2") or ""
        try:
            d = json.loads(html_lib.unescape(brut))
        except Exception:
            continue
        for t in _trouver_threads(d):
            threads.setdefault(str(t.get("threadId")), t)
    offres = []
    for t in threads.values():
        titre = str(t.get("title") or "")
        if not F.est_la_manette(titre):
            continue
        if t.get("isExpired") or t.get("expired"):
            continue
        publie = t.get("publishedAt") or t.get("published_at")
        if isinstance(publie, (int, float)) and time.time() - publie > FRAICHEUR_MAX_H * 3600:
            continue
        marchand = ((t.get("merchant") or {}).get("merchantName") if isinstance(t.get("merchant"), dict)
                    else "") or ""
        if not F.vendeur_est_enseigne(marchand):
            continue
        prix = F.lire_prix(t.get("price"))
        if prix is None:
            continue
        lien = t.get("shareableLink") or t.get("link") or ""
        if not lien.startswith("http"):
            lien = f"https://www.dealabs.com/bons-plans/{t.get('titleSlug', '')}-{t.get('threadId')}"
        port = F.lire_prix(t.get("shipping", {}).get("price")) if isinstance(t.get("shipping"), dict) else 0.0
        offres.append(M.Offre(site=f"Dealabs → {marchand}", edition=F.detecter_edition(titre), titre=titre[:120],
                              url=lien, prix=prix, livraison=port or 0.0, disponible=True,
                              etat_stock="Deal signalé par la communauté", vendeur=marchand,
                              confiance=M.ENSEIGNE, priorite_site=2,
                              remarque="Signalé sur Dealabs : vérifie que c'est bien vendu par l'enseigne."))
    return offres


def _trouver_threads(d):
    pile = [d]
    while pile:
        x = pile.pop()
        if isinstance(x, dict):
            if "threadId" in x and "title" in x:
                yield x
            pile.extend(x.values())
        elif isinstance(x, list):
            pile.extend(x)
