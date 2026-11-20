"""Mode diagnostic : interroge chaque site et affiche ce qu'on récupère vraiment.

Sert à vérifier depuis les serveurs GitHub quels sites répondent, lesquels bloquent,
et à quoi ressemblent les pages (pour ajuster les parseurs si un site change sa structure).
Lancement : python -m traqueur diagnostic [filtre]
"""
from __future__ import annotations

import json
import re
import sys

from bs4 import BeautifulSoup

from .http import Navigateur

URLS_TEST = {
    "amazon.fr fiche": "https://www.amazon.fr/dp/B0HHS4DKRM",
    "amazon.de fiche": "https://www.amazon.de/dp/B0HHS4DKRM?language=fr_FR",
    "amazon.it fiche": "https://www.amazon.it/dp/B0HHS4DKRM",
    "amazon.es fiche": "https://www.amazon.es/dp/B0HHS4DKRM",
    "amazon.fr recherche": "https://www.amazon.fr/s?k=manette+dualsense+gta+vi",
    "fnac fiche blanche": "https://www.fnac.com/a23608238/w-4",
    "fnac recherche": "https://www.fnac.com/SearchResult/ResultList.aspx?Search=dualsense+gta+vi",
    "psdirect blanche": "https://direct.playstation.com/fr-fr/buy-accessories/dualsense-wireless-controller-grand-theft-auto-vi-white-limited-edition-for-ps5-pc-mac-mobile",
    "psdirect noire": "https://direct.playstation.com/fr-fr/buy-accessories/dualsense-wireless-controller-grand-theft-auto-vi-black-limited-edition-for-ps5-pc-mac-mobile",
    "playstation.com noire": "https://www.playstation.com/fr-fr/accessories/dualsense-wireless-controller/buy-now/product/grand-theft-auto-vi-black-limited-edition/",
    "ps store blanche": "https://store.playstation.com/fr-fr/product/PSD001-PSDE02019_19-DUALSENSEG2TH2YE",
    "ebay recherche": "https://www.ebay.fr/sch/i.html?_nkw=manette+dualsense+gta+vi&LH_BIN=1&LH_ItemCondition=1000&_sop=15",
    "micromania recherche": "https://www.micromania.fr/on/demandware.store/Sites-Micromania-Site/fr_FR/Search-Show?q=dualsense+gta",
    "alternate fiche": "https://www.alternate.fr/html/product/100220501",
    "topachat fiche": "https://www.topachat.com/pages/detail2_cat_est_gaming_puis_rubrique_est_wg_pcgam_puis_ref_est_in20032780.html",
    "leclerc recherche": "https://www.e.leclerc/recherche?q=dualsense%20gta",
    "boulanger recherche": "https://www.boulanger.com/resultats?tr=dualsense+gta",
    "cultura recherche": "https://www.cultura.com/search/results?search_query=dualsense%20gta",
    "carrefour recherche": "https://www.carrefour.fr/s?q=dualsense+gta",
    "cdiscount recherche": "https://www.cdiscount.com/search/10/dualsense+gta+vi.html",
    "ldlc recherche": "https://www.ldlc.com/recherche/dualsense%20gta/",
    "auchan recherche": "https://www.auchan.fr/recherche?text=dualsense+gta",
    "darty recherche": "https://www.darty.com/nav/recherche?text=dualsense+gta",
    "idealo recherche": "https://www.idealo.fr/prechcat.html?q=dualsense+gta+vi",
    "ledenicheur recherche": "https://www.ledenicheur.fr/search?search=dualsense%20gta%20vi",
    "dealabs recherche": "https://www.dealabs.com/search?q=dualsense+gta",
}

_PRIX = re.compile(r"(\d{2,3}(?:[.,]\d{2})?)\s?(?:€|&euro;|EUR)")


def _apercu(rep_texte: str) -> dict:
    soup = BeautifulSoup(rep_texte, "lxml")
    titre = (soup.title.get_text(strip=True) if soup.title else "")[:140]
    jsonld = []
    for s in soup.find_all("script", type="application/ld+json"):
        brut = (s.string or s.get_text() or "").strip()
        try:
            d = json.loads(brut)
            types = [x.get("@type") for x in (d if isinstance(d, list) else d.get("@graph", [d]))
                     if isinstance(x, dict)]
        except Exception:
            types = ["(invalide)"]
        jsonld.append({"types": types, "extrait": brut[:900]})
    texte = soup.get_text(" ", strip=True)
    prix = []
    for m in _PRIX.finditer(texte):
        a, b = max(0, m.start() - 70), min(len(texte), m.end() + 30)
        prix.append(texte[a:b])
        if len(prix) >= 8:
            break
    gta = []
    for m in re.finditer(r"(?i)(grand theft auto|gta ?vi|gta ?6)", texte):
        a, b = max(0, m.start() - 60), min(len(texte), m.end() + 90)
        gta.append(texte[a:b])
        if len(gta) >= 5:
            break
    dispo = sorted({m.group(0).lower() for m in re.finditer(
        r"(?i)(rupture de stock|en stock|indisponible|ajouter au panier|précommander|pré-commander|"
        r"currently unavailable|épuisé|non disponible|bientôt disponible|out of stock|add to cart)", texte)})
    scripts_interessants = []
    for motif in ("__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__", "__APOLLO_STATE__",
                  "productCode", "data-product-code", "skuId", "availability"):
        if motif in rep_texte:
            i = rep_texte.find(motif)
            scripts_interessants.append(f"{motif} @ {i}: {rep_texte[i:i + 300]!r}")
    return {"titre": titre, "jsonld": jsonld, "prix": prix, "gta": gta, "dispo": dispo,
            "scripts": scripts_interessants[:6], "taille": len(rep_texte)}


def lancer(filtre: str = "") -> None:
    nav = Navigateur()
    print(f"Empreinte navigateur : {nav.empreinte}\n")
    for nom, url in URLS_TEST.items():
        if filtre and filtre.lower() not in nom.lower():
            continue
        rep = nav.get(url, essais=1)
        print("=" * 100)
        print(f"[{nom}] HTTP {rep.statut} | bloqué={rep.bloque} {rep.raison} | final={rep.url[:150]}")
        if rep.texte:
            a = _apercu(rep.texte)
            print(f"  taille={a['taille']} titre={a['titre']!r}")
            print(f"  dispo={a['dispo']}")
            for j in a["jsonld"][:4]:
                print(f"  JSON-LD {j['types']}: {j['extrait'][:600]}")
            for p in a["prix"]:
                print(f"  prix~ {p}")
            for g in a["gta"]:
                print(f"  gta~ {g}")
            for s in a["scripts"]:
                print(f"  script~ {s}")
        sys.stdout.flush()


def detail(urls: list[str]) -> None:
    """Analyse approfondie d'URLs précises (pour écrire / réparer un parseur)."""
    import json as _json
    for url in urls:
        for empreinte in ("chrome", "safari18_0"):
            nav = Navigateur()
            nav.session = __import__("curl_cffi").requests.Session(impersonate=empreinte)
            rep = nav.get(url, essais=1)
            print("#" * 100)
            print(f"[{empreinte}] {url}\n  → HTTP {rep.statut} bloqué={rep.bloque} {rep.raison} final={rep.url[:160]} taille={len(rep.texte)}")
            if rep.ok:
                break
        if not rep.texte:
            continue
        soup = BeautifulSoup(rep.texte, "lxml")
        print(f"  titre={(soup.title.get_text(strip=True) if soup.title else '')[:150]!r}")
        for s in soup.find_all("script", type="application/ld+json"):
            brut = (s.string or s.get_text() or "").strip()
            if '"Product"' in brut or '"Offer"' in brut:
                print(f"  JSON-LD: {brut[:2500]}")
        n = 0
        for a in soup.find_all("a", href=True):
            t = " ".join(filter(None, [a.get_text(" ", strip=True), a.get("title", ""), a.get("aria-label", "")]))
            if re.search(r"(?i)(grand theft auto|gta ?vi|gta ?6)", t):
                print(f"  lien: {a['href'][:200]} | {t[:160]}")
                n += 1
                if n >= 15:
                    break
        brut = rep.texte
        vus = 0
        for m in re.finditer(r"(?i)(grand theft auto vi|gta vi)", brut):
            a = max(0, m.start() - 250)
            print(f"  html~ {brut[a:m.end() + 350]!r}")
            vus += 1
            if vus >= 5:
                break
        for motif in ("data-vue3", "offerList", "productOffers", "Prix total", "s-card", "s-item", "aod-offer",
                      "productTile", "product-tile", "basePrice", "discountedPrice", "addToCart", "ADD_TO_CART"):
            i = brut.find(motif)
            if i >= 0:
                print(f"  motif {motif} @ {i}: {brut[max(0, i - 150):i + 450]!r}")
        sys.stdout.flush()
