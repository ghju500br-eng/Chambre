"""Couche HTTP : imite un vrai navigateur (empreinte TLS Chrome) et détecte les blocages anti-bot."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from curl_cffi import requests as creq

# Empreintes navigateur proposées par curl_cffi : on en tire une au hasard par session,
# ça passe beaucoup mieux qu'un simple `requests` face à DataDome / Akamai / Cloudflare.
_EMPREINTES = ["chrome", "chrome131", "chrome124", "safari18_0"]

_ENTETES = {
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

# Indices qu'une page est un mur anti-bot et pas la vraie page.
_MARQUEURS_BLOCAGE = [
    ("captcha-delivery.com", "DataDome"),
    ("datadome", "DataDome"),
    ("/errors/validateCaptcha", "captcha Amazon"),
    ("api-services-support@amazon.com", "anti-bot Amazon"),
    ("Robot Check", "captcha"),
    ("Pardon Our Interruption", "anti-bot (Distil/Imperva)"),
    ("cf-chl-", "Cloudflare"),
    ("Just a moment...", "Cloudflare"),
    ("px-captcha", "PerimeterX"),
    ("Access Denied</title>", "Akamai"),
    ("Request unsuccessful. Incapsula", "Imperva"),
    ("_Incapsula_Resource", "Imperva"),
]


@dataclass
class Reponse:
    url: str
    statut: int
    texte: str
    bloque: bool = False
    raison: str = ""

    @property
    def ok(self) -> bool:
        return self.statut == 200 and not self.bloque


class Navigateur:
    """Une session HTTP qui garde ses cookies (utile : certains sites posent un cookie au 1er passage)."""

    def __init__(self) -> None:
        self.empreinte = random.choice(_EMPREINTES)
        self.session = creq.Session(impersonate=self.empreinte)

    def get(self, url: str, *, params: dict | None = None, entetes: dict | None = None,
            timeout: int = 25, essais: int = 2, json_attendu: bool = False) -> Reponse:
        h = dict(_ENTETES)
        if json_attendu:
            h["Accept"] = "application/json, text/plain, */*"
        if entetes:
            h.update(entetes)
        derniere: Reponse | None = None
        for i in range(essais):
            try:
                r = self.session.get(url, params=params, headers=h, timeout=timeout, allow_redirects=True)
                rep = Reponse(url=str(r.url), statut=r.status_code, texte=r.text or "")
            except Exception as e:  # réseau, TLS, timeout...
                rep = Reponse(url=url, statut=0, texte="", bloque=False, raison=f"erreur réseau : {type(e).__name__}")
            _diagnostiquer(rep)
            if rep.ok:
                return rep
            derniere = rep
            # Inutile d'insister sur un 404, on réessaie seulement sur blocage/erreur temporaire.
            if rep.statut == 404:
                break
            time.sleep(2 + 3 * i + random.random() * 2)
        assert derniere is not None
        return derniere

    def post_json(self, url: str, donnees: dict, *, entetes: dict | None = None, timeout: int = 25) -> Reponse:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if entetes:
            h.update(entetes)
        try:
            r = self.session.post(url, json=donnees, headers=h, timeout=timeout)
            rep = Reponse(url=str(r.url), statut=r.status_code, texte=r.text or "")
        except Exception as e:
            rep = Reponse(url=url, statut=0, texte="", raison=f"erreur réseau : {type(e).__name__}")
        _diagnostiquer(rep)
        return rep


def _diagnostiquer(rep: Reponse) -> None:
    if rep.raison:
        return
    debut = rep.texte[:20000]
    for marqueur, nom in _MARQUEURS_BLOCAGE:
        if marqueur in debut:
            rep.bloque = True
            rep.raison = f"bloqué par {nom}"
            return
    if rep.statut in (401, 403, 429, 503):
        rep.bloque = True
        rep.raison = f"bloqué (HTTP {rep.statut})"
    elif rep.statut != 200:
        rep.raison = f"HTTP {rep.statut}"
