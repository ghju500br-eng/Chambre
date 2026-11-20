"""PlayStation (vendeur officiel Sony, seul à vendre la noire en France).

Depuis 2026, PlayStation Direct France est intégré à playstation.com / PlayStation Store : chaque fiche
contient un bloc JSON-LD « Product » avec la disponibilité, et le bouton d'achat (« CTA ») dans les
données de la page. Quand la manette n'est pas en vente, la page affiche « Non disponible à l'achat ».
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M
from ..http import Navigateur
from . import ErreurSource

PRIX_OFFICIEL = 84.99
_CTA_ACHAT = ("ADD_TO_CART", "PREORDER", "PRE_ORDER", "BUY_NOW", "PURCHASE")


def verifier_fiche(nav: Navigateur, url: str, edition: str) -> tuple[list[M.Offre], str]:
    site = "PlayStation Store" if "store.playstation.com" in url else "PlayStation (officiel)"
    rep = nav.get(url)
    if "queue-it" in rep.url or "queue-it.net" in rep.texte[:5000]:
        # File d'attente virtuelle : Sony l'active pendant les grosses mises en vente.
        return [_offre(site, edition, url, PRIX_OFFICIEL, True, "File d'attente active (vente en cours !)",
                       "File d'attente PlayStation active : une vente est probablement en cours.")], "file d'attente active"
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    return analyser(rep.texte, url, site, edition)


def analyser(html: str, url: str, site: str, edition: str) -> tuple[list[M.Offre], str]:
    soup = BeautifulSoup(html, "lxml")
    produits = [p for p in F.produits_jsonld(soup) if F.est_la_manette(str(p.get("name") or ""))]
    if not produits:
        raise ErreurSource("fiche PlayStation illisible (structure changée ?)")
    p = produits[0]

    # 1) Disponibilité et prix déclarés dans le JSON-LD
    dispo_ld, prix_ld = None, None
    for o in F.offres_jsonld(p):
        if o.get("availability"):
            dispo_ld = F.dispo_schema(str(o["availability"]))
        prix_ld = prix_ld or F.lire_prix(o.get("price"))

    # 2) Si le JSON-LD ne dit rien du stock : bouton d'achat + texte de la page. Seulement sur le
    #    PlayStation Store (une fiche = un produit). Sur playstation.com, la page affiche aussi d'autres
    #    manettes en promo : leurs boutons et leurs prix fausseraient le résultat.
    if dispo_ld:
        dispo, libelle = dispo_ld
    elif site == "PlayStation Store":
        ctas = set(re.findall(r'"type"\s*:\s*"([A-Z_]+)"', html))
        texte = F.normaliser(soup.get_text(" ", strip=True))
        non_dispo = "non disponible a l'achat" in texte or "actuellement indisponible" in texte
        dispo = any(c in ctas for c in _CTA_ACHAT) and not non_dispo
        libelle = "Bouton d'achat actif" if dispo else ("Non disponible à l'achat" if non_dispo else "Indisponible")
    else:
        dispo, libelle = False, "État inconnu (fiche sans info de stock)"
    if libelle == "Rupture de stock":
        libelle = "Non disponible à l'achat"
    return [_offre(site, edition, url, prix_ld or PRIX_OFFICIEL, dispo, libelle)], ""


def _offre(site, edition, url, prix, dispo, libelle, remarque="") -> M.Offre:
    return M.Offre(site=site, edition=edition, titre=f"Manette DualSense GTA VI {M.EDITIONS.get(edition, '')} (officielle)",
                   url=url, prix=prix, livraison=0.0, disponible=dispo, etat_stock=libelle, vendeur="Sony",
                   confiance=M.OFFICIEL, priorite_site=1, remarque=remarque)
