"""Filtres : reconnaître la bonne manette, lire un prix, ne garder que des sites et vendeurs fiables."""
from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urlparse

from . import modeles as M

# ── Sites autorisés ──────────────────────────────────────────────────────────
# Toute offre dont l'URL n'est pas sur un de ces domaines est jetée, point.
DOMAINES_AUTORISES = {
    "direct.playstation.com": ("PlayStation Direct", M.OFFICIEL, 1),
    "store.playstation.com": ("PlayStation Store", M.OFFICIEL, 1),
    "www.playstation.com": ("PlayStation (officiel)", M.OFFICIEL, 1),
    "www.amazon.fr": ("Amazon.fr", M.ENSEIGNE, 1),
    "www.amazon.de": ("Amazon.de", M.ENSEIGNE, 2),
    "www.amazon.it": ("Amazon.it", M.ENSEIGNE, 2),
    "www.amazon.es": ("Amazon.es", M.ENSEIGNE, 2),
    "www.fnac.com": ("Fnac", M.ENSEIGNE, 1),
    "www.ebay.fr": ("eBay", M.EBAY_PRO, 3),
    "www.micromania.fr": ("Micromania", M.ENSEIGNE, 2),
    "www.e.leclerc": ("E.Leclerc", M.ENSEIGNE, 2),
    "www.boulanger.com": ("Boulanger", M.ENSEIGNE, 2),
    "www.cultura.com": ("Cultura", M.ENSEIGNE, 2),
    "www.carrefour.fr": ("Carrefour", M.ENSEIGNE, 2),
    "www.auchan.fr": ("Auchan", M.ENSEIGNE, 2),
    "www.darty.com": ("Darty", M.ENSEIGNE, 2),
    "www.cdiscount.com": ("Cdiscount", M.ENSEIGNE, 2),
    "www.ldlc.com": ("LDLC", M.ENSEIGNE, 2),
    "www.topachat.com": ("TopAchat", M.ENSEIGNE, 2),
    "www.alternate.fr": ("Alternate", M.ENSEIGNE, 2),
    # Dealabs n'est pas un vendeur : ses deals ne sont retenus que si le marchand est une enseigne ci-dessus.
    "www.dealabs.com": ("Dealabs", M.ENSEIGNE, 2),
    # idealo non plus : ses offres ne sont gardées que si le marchand est une enseigne ci-dessus.
    "www.idealo.fr": ("idealo", M.ENSEIGNE, 2),
}


def domaine(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def domaine_autorise(url: str) -> bool:
    return domaine(url) in DOMAINES_AUTORISES


def priorite_site(url: str) -> int:
    return DOMAINES_AUTORISES.get(domaine(url), ("", 0, 9))[2]


# Vendeurs considérés comme "l'enseigne elle-même" quand ils apparaissent comme vendeur.
_VENDEURS_ENSEIGNE = ["amazon", "fnac", "playstation", "sony", "micromania", "leclerc", "boulanger",
                      "cultura", "carrefour", "auchan", "darty", "cdiscount", "ldlc", "topachat", "alternate"]


def vendeur_est_enseigne(vendeur: str) -> bool:
    v = sans_accents(vendeur).lower()
    if not v:
        return False
    # "Amazon EU S.à r.l.", "Amazon.fr", "Fnac.com", "Vendu et expédié par Cdiscount"...
    return any(re.search(rf"\b{nom}\b", v) for nom in _VENDEURS_ENSEIGNE)


# ── Texte ────────────────────────────────────────────────────────────────────
def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def normaliser(s: str) -> str:
    s = sans_accents(s).lower().replace("®", " ").replace("™", " ")
    return re.sub(r"\s+", " ", s).strip()


# ── Prix ─────────────────────────────────────────────────────────────────────
_RE_PRIX = re.compile(r"(\d{1,3}(?:[   .]\d{3})*|\d+)(?:\s*[.,€]\s*(\d{2}))?")


def lire_prix(texte) -> float | None:
    """'84,99 €' → 84.99 ; '1 234,56' → 1234.56 ; '84€99' → 84.99 ; 84.99 → 84.99"""
    if texte is None:
        return None
    if isinstance(texte, (int, float)):
        return float(texte) if texte > 0 else None
    t = str(texte).strip()
    if not t:
        return None
    # Format machine "84.99" ou "84"
    if re.fullmatch(r"\d+(\.\d+)?", t):
        v = float(t)
        return v if v > 0 else None
    m = _RE_PRIX.search(t)
    if not m:
        return None
    entier = re.sub(r"[   .]", "", m.group(1))
    try:
        v = float(f"{entier}.{m.group(2) or '00'}")
    except ValueError:
        return None
    return v if v > 0 else None


# ── Reconnaître la manette ───────────────────────────────────────────────────
_RE_GTA = re.compile(r"\b(gta ?(vi|6)|grand theft auto ?(vi|6))\b")
_RE_MANETTE = re.compile(r"\b(dual ?sense|manette|controller|mando|controllo|controle)\b")

# Mots qui trahissent un accessoire, un pack, ou autre chose que la manette elle-même.
_EXCLUS_COMMUNS = [
    r"\bcoques?\b", r"\bskins?\b", r"\bstickers?\b", r"\bautocollants?\b", r"\bhousses?\b", r"\betuis?\b",
    r"\bcases?\b", r"\bsupports?\b", r"\bstand\b", r"\bchargeurs?\b", r"\bcharging\b",
    r"\bstation de charge\b", r"\bdocking\b", r"\bfacades?\b", r"\bfaceplates?\b", r"\bplaques?\b",
    r"\bgrips?\b", r"\bcapuchons?\b", r"\bboite vide\b", r"\bbox only\b", r"\bempty box\b",
    r"\bsans manette\b", r"\bboite seule\b", r"\breplique\b", r"\breplica\b", r"\bcustom\b",
    r"\bpersonnalis", r"\bpour pieces\b", r"\bhors service\b", r"\bdefectueu", r"\bcasse\b",
    r"(?<!pour )(?<!for )\bconsoles?\b", r"\bcode de telechargement\b", r"\btelechargement\b",
    r"\bdownload code\b", r"\bbundle\b", r"\bposter\b", r"\baffiche\b", r"\bfigurines?\b",
    r"\bacryl", r"\bvitrine\b", r"\bdisplay\b", r"\bsilicone\b", r"\bps4\b", r"\bxbox\b",
    r"\bswitch\b", r"\bvinyle?\b", r"\bdecal\b", r"\bwrap\b", r"\bjeu ps5\b", r"\bsteelbook\b",
]
# Pour eBay on est plus strict (contrefaçons et annonces piège).
_EXCLUS_EBAY = _EXCLUS_COMMUNS + [
    r"\bcompatible\b", r"\bimitation\b", r"\bgenerique\b", r"\bnon officiel", r"\bunofficial\b",
    r"\bpack\b", r"\blot\b", r"\bphoto\b", r"\bimage\b", r"\bhs\b", r"\bpieces?\b",
    r"\blocation\b", r"\bpre ?-?commande\b", r"\bpre ?-?order\b", r"\bcasque\b", r"\bheadset\b",
]
_RE_EXCLUS = re.compile("|".join(_EXCLUS_COMMUNS))
_RE_EXCLUS_EBAY = re.compile("|".join(_EXCLUS_EBAY))


def est_la_manette(titre: str, strict: bool = False) -> bool:
    t = normaliser(titre)
    if not _RE_GTA.search(t) or not _RE_MANETTE.search(t):
        return False
    return not (_RE_EXCLUS_EBAY if strict else _RE_EXCLUS).search(t)


_BLANC = re.compile(r"\b(blanc|blanche|white|bianco|bianca|blanco|blanca|weiss|weib)\b")
_NOIR = re.compile(r"\b(noir|noire|black|nero|nera|negro|negra|schwarz)\b")


def detecter_edition(titre: str) -> str:
    t = normaliser(titre).replace("ß", "ss")
    b, n = bool(_BLANC.search(t)), bool(_NOIR.search(t))
    if b and not n:
        return "blanche"
    if n and not b:
        return "noire"
    return "?"


def est_occasion(texte: str) -> bool:
    t = normaliser(texte)
    return bool(re.search(r"\b(occasion|d'occasion|reconditionne|used|usagee?|comme neuf|tres bon etat|"
                          r"bon etat|etat correct|deballe)\b", t))


# ── JSON-LD (données produit standardisées que beaucoup de sites embarquent) ──
def produits_jsonld(soup) -> list[dict]:
    produits = []
    for s in soup.find_all("script", type="application/ld+json"):
        brut = (s.string or s.get_text() or "").strip()
        if not brut:
            continue
        try:
            d = json.loads(brut)
        except Exception:
            try:  # certains sites mettent des retours ligne illégaux dans les chaînes
                d = json.loads(re.sub(r"[\r\n\t]+", " ", brut))
            except Exception:
                continue
        pile = d if isinstance(d, list) else [d]
        while pile:
            x = pile.pop()
            if isinstance(x, list):
                pile.extend(x)
                continue
            if not isinstance(x, dict):
                continue
            if "@graph" in x:
                pile.extend(x["@graph"] if isinstance(x["@graph"], list) else [x["@graph"]])
            t = x.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Product" in types or "ProductGroup" in types:
                produits.append(x)
            elif "ItemList" in types:
                for el in x.get("itemListElement", []) or []:
                    if isinstance(el, dict):
                        pile.append(el.get("item", el))
    return produits


def offres_jsonld(produit: dict) -> list[dict]:
    o = produit.get("offers") or []
    if isinstance(o, dict):
        if o.get("@type") == "AggregateOffer" and o.get("offers"):
            o = o["offers"]
        else:
            o = [o]
    return [x for x in o if isinstance(x, dict)]


def dispo_schema(valeur: str) -> tuple[bool, str]:
    """Traduit https://schema.org/InStock & co → (commandable, libellé)."""
    v = (valeur or "").rsplit("/", 1)[-1].lower()
    table = {
        "instock": (True, "En stock"),
        "limitedavailability": (True, "Stock limité"),
        "onlineonly": (True, "En stock (en ligne)"),
        "preorder": (True, "Précommande"),
        "presale": (True, "Prévente"),
        "backorder": (True, "Sur commande"),
        "instoreonly": (False, "En magasin uniquement"),
        "outofstock": (False, "Rupture de stock"),
        "soldout": (False, "Épuisé"),
        "discontinued": (False, "Plus vendu"),
    }
    return table.get(v, (False, valeur or "inconnu"))
