"""Amazon (.fr en priorité, + .de/.it/.es qui livrent en France)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource

PAYS = {
    "fr": ("Amazon.fr", 1),
    "de": ("Amazon.de", 2),
    "it": ("Amazon.it", 2),
    "es": ("Amazon.es", 2),
}

_SELECTEURS_PRIX = [
    "#corePrice_feature_div .a-price .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#apex_desktop .priceToPay .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#tp_price_block_total_price_ww .a-offscreen",
    "#price_inside_buybox", "#newBuyBoxPrice", "#priceblock_ourprice", "#priceblock_preorderprice",
    "#buybox .a-price .a-offscreen",
]
_DISPO_OK = ["en stock", "auf lager", "disponibilita immediata", "disponible", "in stock",
             "il ne reste plus", "nur noch", "solo", "quedan"]
_DISPO_PRECO = ["precommande", "pre-commande", "vorbestell", "preordin", "reserva", "pre-order"]
_DISPO_KO = ["actuellement indisponible", "derzeit nicht verfugbar", "non disponibile", "no disponible",
             "currently unavailable", "temporairement en rupture", "nicht verfugbar"]


def verifier_asin(nav: Navigateur, asin: str, edition: str, tld: str, port: float) -> list[M.Offre]:
    site, prio = PAYS[tld]
    url = f"https://www.amazon.{tld}/dp/{asin}"
    rep = nav.get(url)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    soup = BeautifulSoup(rep.texte, "lxml")
    titre = _texte(soup.select_one("#productTitle")) or f"Manette GTA VI ({asin})"
    if not F.est_la_manette(titre):
        # ASIN réattribué ou page inattendue : on ne prend pas le risque.
        return []
    offres: list[M.Offre] = []
    principale = _offre_principale(soup, url, site, prio, edition, titre, tld, port)
    if principale:
        offres.append(principale)

    # Toutes les offres (vendeurs tiers inclus) via le panneau "Autres vendeurs".
    aod = nav.get(f"https://www.amazon.{tld}/gp/product/ajax/aodAjaxMain/",
                  params={"asin": asin, "pc": "dp", "experienceId": "aodAjaxMain"}, essais=1,
                  entetes={"Referer": url, "X-Requested-With": "XMLHttpRequest"})
    if aod.ok:
        for o in _offres_aod(aod.texte, url, site, prio, edition, titre, tld, port):
            meme = next((x for x in offres if x.prix is not None and abs(x.prix - (o.prix or 0)) < 0.01), None)
            if meme is None:
                offres.append(o)
            elif meme.vendeur.endswith("(à confirmer)"):
                # Le panneau des vendeurs nous dit qui vend vraiment l'offre principale.
                meme.vendeur, meme.confiance = o.vendeur, o.confiance
    return offres


def _offre_principale(soup, url, site, prio, edition, titre, tld, port) -> M.Offre | None:
    prix = None
    for sel in _SELECTEURS_PRIX:
        el = soup.select_one(sel)
        if el and (prix := F.lire_prix(_texte(el))):
            break
    if prix is None:
        for name in ("twister-plus-price-data-price", "attach-base-product-price"):
            el = soup.find("input", id=name) or soup.find("input", attrs={"name": name})
            if el and (prix := F.lire_prix(el.get("value"))):
                break
    dispo_txt = F.normaliser(_texte(soup.select_one("#availability")) or _texte(soup.select_one("#outOfStock")))
    a_bouton = bool(soup.select_one("#add-to-cart-button, #buy-now-button, #add-to-cart-button-ubb"))
    if any(k in dispo_txt for k in _DISPO_KO) or soup.select_one("#outOfStock"):
        dispo, libelle = False, "Rupture de stock"
    elif any(k in dispo_txt for k in _DISPO_PRECO) or soup.select_one("#preorder_feature_div #add-to-cart-button"):
        dispo, libelle = a_bouton, "Précommande"
    elif a_bouton or any(k in dispo_txt for k in _DISPO_OK):
        dispo, libelle = a_bouton and prix is not None, "En stock" if a_bouton else dispo_txt[:60]
    else:
        dispo, libelle = False, dispo_txt[:60] or "Indisponible"
    if prix is None:
        if not dispo:
            # Pas de prix affiché = pas d'offre en vente. On garde une ligne pour le bilan.
            return M.Offre(site=site, edition=edition, titre=titre, url=url, prix=None, disponible=False,
                           etat_stock=libelle, vendeur="Amazon", confiance=M.ENSEIGNE, priorite_site=prio)
        return None
    vendeur = _vendeur(soup)
    confiance = M.ENSEIGNE if (not vendeur or F.vendeur_est_enseigne(vendeur)) else M.MARKETPLACE
    return M.Offre(site=site, edition=edition, titre=titre, url=url, prix=prix,
                   livraison=0.0 if tld == "fr" else port, disponible=dispo, etat_stock=libelle,
                   vendeur=vendeur or "Amazon (à confirmer)", confiance=confiance, priorite_site=prio,
                   remarque="" if tld == "fr" else "Frais de port vers la France estimés ; vérifie que la livraison en France est possible.")


def _vendeur(soup) -> str:
    for sel in ("#merchantInfoFeature_feature_div .offer-display-feature-text-message",
                "#sellerProfileTriggerId", "#merchant-info a", "#merchant-info",
                "#tabular-buybox .tabular-buybox-text[tabular-attribute-name='Vendu par']",
                "#tabular-buybox"):
        t = _texte(soup.select_one(sel))
        if t:
            m = re.search(r"(?:vendu par|verkauf durch|venduto da|vendido por|sold by)\s*:?\s*([^.\n]+)", t, re.I)
            return (m.group(1) if m else t).strip()[:60]
    return ""


def _offres_aod(html, url, site, prio, edition, titre, tld, port) -> list[M.Offre]:
    soup = BeautifulSoup(html, "lxml")
    offres = []
    for bloc in soup.select("#aod-pinned-offer, #aod-offer"):
        prix = F.lire_prix(_texte(bloc.select_one(".a-price .a-offscreen")))
        if prix is None:
            continue
        etat = _texte(bloc.select_one("#aod-offer-heading")) or ""
        vendeur = _texte(bloc.select_one("#aod-offer-soldBy a, #aod-offer-soldBy .a-col-right span")) or ""
        livraison_txt = F.normaliser(_texte(bloc.select_one("#mir-layout-DELIVERY_BLOCK, .aod-delivery-promise")))
        livraison = 0.0
        m = re.search(r"(\d+[.,]\d{2}) ?€", livraison_txt)
        if m and ("livraison" in livraison_txt or "lieferung" in livraison_txt or "spedizione" in livraison_txt
                  or "envio" in livraison_txt):
            livraison = F.lire_prix(m.group(1)) or 0.0
        elif tld != "fr":
            livraison = port
        confiance = M.ENSEIGNE if F.vendeur_est_enseigne(vendeur) else M.MARKETPLACE
        offres.append(M.Offre(site=site, edition=edition, titre=titre, url=url, prix=prix, livraison=livraison,
                              disponible=True, etat_stock=etat or "En vente", vendeur=vendeur or "Vendeur tiers",
                              confiance=confiance, neuf=not F.est_occasion(etat), priorite_site=prio))
    return offres


def rechercher(nav: Navigateur, tld: str, requete: str) -> tuple[list[tuple[str, str, float | None]], bool]:
    """Recherche Amazon → [(asin, titre, prix)] des résultats qui sont la bonne manette."""
    rep = nav.get(f"https://www.amazon.{tld}/s", params={"k": requete})
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    soup = BeautifulSoup(rep.texte, "lxml")
    res = []
    for item in soup.select('div[data-component-type="s-search-result"][data-asin]'):
        asin = item.get("data-asin")
        titre = _texte(item.select_one("h2")) or ""
        if asin and F.est_la_manette(titre):
            res.append((asin, titre, F.lire_prix(_texte(item.select_one(".a-price .a-offscreen")))))
    return res, True


def _texte(el) -> str:
    return el.get_text(" ", strip=True) if el else ""
