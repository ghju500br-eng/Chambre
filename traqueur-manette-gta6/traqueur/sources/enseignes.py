"""Grandes enseignes françaises : on cherche la manette sur leur moteur de recherche, puis on lit les fiches."""
from __future__ import annotations

from ..http import Navigateur
from .. import modeles as M
from . import ErreurSource
from .fiche import analyser_fiche, liens_produits

# (nom, URL de recherche). Seulement les enseignes qui acceptent qu'on lise leurs pages : Fnac, Cultura,
# Carrefour, Darty et Cdiscount refusent les robots (vérifié le 20/11/2026), on respecte et on ne les
# interroge pas. Leurs prix remontent quand même via idealo quand elles y sont référencées.
RECHERCHES = [
    ("Micromania", "https://www.micromania.fr/on/demandware.store/Sites-Micromania-Site/fr_FR/Search-Show?q=manette+gta+vi"),
    ("E.Leclerc", "https://www.e.leclerc/recherche?q=manette%20dualsense%20gta%20vi"),
    ("Boulanger", "https://www.boulanger.com/resultats?tr=manette+dualsense+gta+vi"),
    ("Auchan", "https://www.auchan.fr/recherche?text=manette+dualsense+gta+vi"),
    ("LDLC", "https://www.ldlc.com/recherche/dualsense%20gta%20vi/"),
]


def chercher(nav: Navigateur, nom: str, url_recherche: str, deja_vues: set[str]) -> tuple[list[M.Offre], str]:
    rep = nav.get(url_recherche)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    liens = [l for l in liens_produits(rep.texte, rep.url) if l not in deja_vues]
    if not liens:
        # Une page de résultats n'est jamais une fiche (Boulanger y met un faux "Product" à 19 €) :
        # on ne la lit comme fiche que si le site nous a redirigés directement vers un produit.
        if rep.url.split("?")[0] != url_recherche.split("?")[0]:
            offres, _ = analyser_fiche(rep.texte, rep.url, site=nom)
            if offres:
                return offres, "redirigé vers la fiche"
        return [], "pas référencée pour l'instant"
    offres: list[M.Offre] = []
    for lien in liens:
        deja_vues.add(lien)
        r = nav.get(lien, essais=1)
        if r.ok:
            o, _ = analyser_fiche(r.texte, lien, site=nom)
            offres.extend(o)
    return offres, f"{len(liens)} fiche(s) trouvée(s)"


def verifier_fiche(nav: Navigateur, site: str, url: str, edition: str) -> list[M.Offre]:
    rep = nav.get(url)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    offres, _ = analyser_fiche(rep.texte, url, site=site, edition=edition, exiger_gta=True)
    return offres
