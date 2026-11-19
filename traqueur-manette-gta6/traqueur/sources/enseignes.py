"""Grandes enseignes françaises : on cherche la manette sur leur moteur de recherche, puis on lit les fiches."""
from __future__ import annotations

from ..http import Navigateur
from .. import modeles as M
from . import ErreurSource
from .fiche import analyser_fiche, liens_produits

# (nom, URL de recherche). Certaines enseignes affichent leurs résultats en JavaScript :
# dans ce cas le bilan l'indique honnêtement ("aucune fiche lisible").
RECHERCHES = [
    ("Fnac", "https://www.fnac.com/SearchResult/ResultList.aspx?Search=dualsense+gta+vi"),
    ("Micromania", "https://www.micromania.fr/on/demandware.store/Sites-Micromania-Site/fr_FR/Search-Show?q=dualsense+gta"),
    ("E.Leclerc", "https://www.e.leclerc/recherche?q=dualsense%20gta"),
    ("Boulanger", "https://www.boulanger.com/resultats?tr=dualsense+gta"),
    ("Cultura", "https://www.cultura.com/search/results?search_query=dualsense%20gta"),
    ("Carrefour", "https://www.carrefour.fr/s?q=dualsense+gta"),
    ("Auchan", "https://www.auchan.fr/recherche?text=dualsense+gta"),
    ("Darty", "https://www.darty.com/nav/recherche?text=dualsense+gta"),
    ("Cdiscount", "https://www.cdiscount.com/search/10/dualsense+gta+vi.html"),
    ("LDLC", "https://www.ldlc.com/recherche/dualsense%20gta/"),
]


def chercher(nav: Navigateur, nom: str, url_recherche: str, deja_vues: set[str]) -> tuple[list[M.Offre], str]:
    rep = nav.get(url_recherche)
    if not rep.ok:
        raise ErreurSource(rep.raison or f"HTTP {rep.statut}", bloque=rep.bloque)
    liens = [l for l in liens_produits(rep.texte, rep.url) if l not in deja_vues]
    if not liens:
        # Parfois la page de recherche est elle-même une fiche (redirection directe) ou contient du JSON-LD.
        offres, _ = analyser_fiche(rep.texte, rep.url, site=nom)
        return offres, "" if offres else "aucune fiche lisible (pas référencée ou page dynamique)"
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
