"""Lecture générique d'une fiche produit (marche sur la plupart des sites grâce au JSON-LD)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import filtres as F
from .. import modeles as M


def analyser_fiche(html: str, url: str, *, site: str | None = None, edition: str | None = None,
                   exiger_gta: bool = True) -> tuple[list[M.Offre], str]:
    """Renvoie (offres, nom_produit). Si `edition` est fournie, la fiche est considérée comme connue."""
    soup = BeautifulSoup(html, "lxml")
    nom_site, confiance_site, prio = F.DOMAINES_AUTORISES.get(F.domaine(url), (site or F.domaine(url), M.ENSEIGNE, 9))
    site = site or nom_site
    offres: list[M.Offre] = []
    nom_produit = ""
    vendeur_page = _vendeur_affiche(soup)

    for p in F.produits_jsonld(soup):
        nom = str(p.get("name") or "")
        if exiger_gta and nom and not F.est_la_manette(nom):
            continue
        nom_produit = nom_produit or nom
        ed = edition or F.detecter_edition(nom)
        if ed == "?":   # nom sans couleur (ex. Auchan) : on regarde la description
            ed = F.detecter_edition(str(p.get("description") or ""))
        for o in F.offres_jsonld(p):
            prix = F.lire_prix(o.get("price") or o.get("lowPrice")
                               or (o.get("priceSpecification") or {}).get("price"))
            dispo, libelle = F.dispo_schema(str(o.get("availability") or ""))
            if prix is None and not o.get("availability"):
                continue
            if prix is None:
                dispo = False   # pas de prix affiché = pas commandable (on garde la ligne pour le bilan)
            vendeur = o.get("seller") or {}
            vendeur = str(vendeur.get("name", "") if isinstance(vendeur, dict) else vendeur) or vendeur_page
            livraison = _livraison_jsonld(o)
            etat_produit = str(o.get("itemCondition") or "")
            confiance = confiance_site
            if vendeur and not F.vendeur_est_enseigne(vendeur) and confiance_site == M.ENSEIGNE:
                confiance = M.MARKETPLACE
            if o.get("@type") == "AggregateOffer" or (o.get("lowPrice") and not o.get("price")):
                libelle += " (prix le plus bas, tous vendeurs)"
                confiance = max(confiance, M.MARKETPLACE)
            offres.append(M.Offre(
                site=site, edition=ed, titre=nom or site, url=url, prix=prix, livraison=livraison,
                disponible=dispo, etat_stock=libelle, vendeur=vendeur or site, confiance=confiance,
                neuf="Used" not in etat_produit and "Refurbished" not in etat_produit, priorite_site=prio))

    if not offres:
        offres = _repli_meta(soup, url, site, edition, confiance_site, prio, exiger_gta)
        if offres:
            nom_produit = nom_produit or offres[0].titre
    return offres, nom_produit


def _livraison_jsonld(o: dict) -> float | None:
    sd = o.get("shippingDetails")
    if isinstance(sd, list) and sd:
        sd = sd[0]
    if isinstance(sd, dict):
        taux = sd.get("shippingRate") or {}
        if isinstance(taux, dict) and "value" in taux:
            try:
                return float(taux["value"])
            except (TypeError, ValueError):
                return None
    return None   # frais de port non indiqués : inconnus (on ne suppose pas « offerts »)


_RE_VENDU_PAR = re.compile(r"Vendu (?:et expédié )?par\s*:?\s*([A-Za-z0-9][\w.&' -]{1,40}?)(?=\s{2}|\s*[|,·]|\s+(?:Expédi|Livr|Voir|\d)|$)")


def _vendeur_affiche(soup) -> str:
    """Vendeur affiché sur la page (« Vendu par MASS DISTRIB ») quand le JSON-LD ne le dit pas."""
    texte = soup.get_text("  ", strip=True)
    m = _RE_VENDU_PAR.search(texte)
    return m.group(1).strip() if m else ""


def _repli_meta(soup, url, site, edition, confiance, prio, exiger_gta) -> list[M.Offre]:
    """Si pas de JSON-LD : balises meta / microdonnées (og:price, itemprop=price...)."""
    def meta(*noms):
        for n in noms:
            t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) \
                or soup.find(attrs={"itemprop": n})
            if t:
                v = t.get("content") or t.get("href") or t.get_text(strip=True)
                if v:
                    return v
        return None

    titre = meta("og:title") or (soup.title.get_text(strip=True) if soup.title else "")
    if exiger_gta and not F.est_la_manette(titre or ""):
        return []
    prix = F.lire_prix(meta("product:price:amount", "og:price:amount", "price"))
    if prix is None:
        return []
    dispo_brut = meta("product:availability", "og:availability", "availability") or ""
    dispo, libelle = F.dispo_schema(dispo_brut.replace(" ", "").replace("instock", "InStock"))
    if not dispo_brut:
        dispo, libelle = False, "disponibilité inconnue"
    return [M.Offre(site=site, edition=edition or F.detecter_edition(titre), titre=titre, url=url,
                    prix=prix, livraison=0.0, disponible=dispo, etat_stock=libelle, vendeur=site,
                    confiance=confiance, priorite_site=prio)]


def liens_produits(html: str, url_page: str, max_liens: int = 4) -> list[str]:
    """Dans une page de résultats de recherche, trouve les liens qui pointent vers la bonne manette."""
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, "lxml")
    dom = F.domaine(url_page)
    vus: list[str] = []
    for a in soup.find_all("a", href=True):
        texte = " ".join(filter(None, [a.get_text(" ", strip=True), a.get("title", ""), a.get("aria-label", "")]
                                + [img.get("alt", "") for img in a.find_all("img")]))
        if not F.est_la_manette(texte):
            continue
        lien = urljoin(url_page, a["href"])
        if F.domaine(lien) != dom:
            continue
        lien = re.sub(r"#.*$", "", lien)
        if lien not in vus:
            vus.append(lien)
        if len(vus) >= max_liens:
            break
    return vus
