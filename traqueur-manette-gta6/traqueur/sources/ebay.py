"""eBay : uniquement achat immédiat, neuf, vendeurs très bien notés, expédié depuis l'UE."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..config import Config
from ..http import Navigateur
from . import ErreurSource

URL = "https://www.ebay.fr/sch/i.html"
REQUETES = ["manette dualsense gta vi", "manette ps5 gta 6 edition limitee"]

_RE_VENDEUR = re.compile(r"\(([\d\s  .,]+)\)\s*([\d]{2,3}(?:[.,]\d)?)\s?%")
_RE_VENDEUR_K = re.compile(r"([\d.,]+)\s?(k|K)?\s*\)?\s*·?\s*([\d]{2,3}(?:[.,]\d)?)\s?%\s*(?:d'évaluations positives|positive)")
_RE_VENDEUR_PCT = re.compile(r"([\d]{2,3}(?:[.,]\d)?)\s?%\s*(?:d'évaluations positives|positives?|positive feedback)?\s*"
                             r"\(([\d.,\s\u00a0\u202f]+)\s?(k|K)?\)")
_RE_PROVENANCE = re.compile(r"(?:Provenance|Expédié depuis|Situé|Localisation)\s*:?\s*([A-Za-zÀ-ÿ' -]+)", re.I)
_RE_PORT = re.compile(r"\+?\s*(\d+[.,]\d{2})\s?(?:€|EUR)\s*(?:de frais de |pour la )?livraison", re.I)


def rechercher(nav: Navigateur, cfg: Config) -> tuple[list[M.Offre], int]:
    """Renvoie (offres retenues, nb d'annonces écartées pour manque de fiabilité)."""
    offres: dict[str, M.Offre] = {}
    ecartees = 0
    reussi = False
    derniere_erreur = None
    for requete in REQUETES:
        params = {"_nkw": requete, "LH_BIN": "1", "_sop": "15", "_ipg": "120"}
        if not cfg.accepter_occasion:
            params["LH_ItemCondition"] = "1000"
        rep = nav.get(URL, params=params)
        if not rep.ok:
            derniere_erreur = rep
            continue
        reussi = True
        trouvees, ec = analyser_resultats(rep.texte, cfg)
        ecartees += ec
        for o in trouvees:
            offres.setdefault(o.url, o)
    if not reussi:
        raise ErreurSource(derniere_erreur.raison or f"HTTP {derniere_erreur.statut}", bloque=derniere_erreur.bloque)
    return list(offres.values()), ecartees


def analyser_resultats(html: str, cfg: Config) -> tuple[list[M.Offre], int]:
    soup = BeautifulSoup(html, "lxml")
    blocs = soup.select("li.s-item, li.s-card, div.s-item, div.s-card")
    offres, ecartees = [], 0
    for b in blocs:
        titre_el = b.select_one(".s-item__title, .s-card__title, [role=heading]")
        titre = (titre_el.get_text(" ", strip=True) if titre_el else "").replace("Nouvelle annonce", "").strip()
        if not titre or titre.lower().startswith("shop on ebay") or not F.est_la_manette(titre, strict=True):
            continue
        lien_el = b.select_one("a.s-item__link, a.s-card__link, a[href*='/itm/']")
        if not lien_el:
            continue
        m = re.search(r"/itm/(?:[^/]+/)?(\d{9,})", lien_el["href"])
        if not m:
            continue
        url = f"https://www.ebay.fr/itm/{m.group(1)}"
        texte = b.get_text(" ", strip=True)
        prix_el = b.select_one(".s-item__price, .s-card__price")
        prix_txt = prix_el.get_text(" ", strip=True) if prix_el else ""
        if " à " in prix_txt or " to " in prix_txt:   # annonce multi-variantes : prix ambigu
            ecartees += 1
            continue
        prix = F.lire_prix(prix_txt)
        if prix is None:
            continue

        # Frais de port
        if re.search(r"livraison gratuite|free (shipping|delivery)", texte, re.I):
            port = 0.0
        else:
            mp = _RE_PORT.search(texte)
            port = F.lire_prix(mp.group(1)) if mp else None

        # Fiabilité du vendeur
        nb_eval, note = _lire_vendeur(texte)
        top = bool(re.search(r"top fiabilit|top rated", texte, re.I))
        fiable = (note is not None and nb_eval is not None
                  and note >= cfg.ebay_note_min and nb_eval >= cfg.ebay_nb_eval_min) or top
        # Provenance (pas d'import hors UE)
        mprov = _RE_PROVENANCE.search(texte)
        provenance = (mprov.group(1).strip() if mprov else "France")
        provenance = re.split(r"\s{2,}| Livraison| \+| Achat| Économisez", provenance)[0].strip()
        pays_ok = any(p.lower() in provenance.lower() for p in cfg.ebay_pays) if mprov else True
        occasion = F.est_occasion(texte[:400])

        if not fiable or not pays_ok or prix < cfg.ebay_prix_min_credible or (occasion and not cfg.accepter_occasion):
            ecartees += 1
            continue
        vendeur = f"{nb_eval or '?'} avis, {note or '?'} % positifs" + (" · Top Fiabilité" if top else "")
        offres.append(M.Offre(site="eBay", edition=F.detecter_edition(titre), titre=titre[:120], url=url,
                              prix=prix, livraison=port, disponible=True,
                              etat_stock="Achat immédiat" + (" · occasion" if occasion else " · neuf"),
                              vendeur=vendeur, confiance=M.EBAY_PRO, neuf=not occasion, priorite_site=3,
                              remarque=f"Expédié depuis : {provenance}" + ("" if port is not None else " · port inconnu")))
    return offres, ecartees


def _lire_vendeur(texte: str) -> tuple[int | None, float | None]:
    m = _RE_VENDEUR.search(texte)
    if m:
        nb = int(re.sub(r"\D", "", m.group(1)) or 0)
        return nb, float(m.group(2).replace(",", "."))
    m = _RE_VENDEUR_PCT.search(texte)
    if m:
        base = float(re.sub(r"[\s\u00a0\u202f]", "", m.group(2)).replace(",", ".") or 0)
        nb = int(base * 1000) if m.group(3) else int(base)
        return nb, float(m.group(1).replace(",", "."))
    m = _RE_VENDEUR_K.search(texte)
    if m:
        base = float(m.group(1).replace(",", "."))
        nb = int(base * 1000) if m.group(2) else int(base)
        return nb, float(m.group(3).replace(",", "."))
    return None, None
