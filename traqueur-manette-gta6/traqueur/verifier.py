"""Une vérification complète : interroge toutes les sources, trie, décide quoi signaler."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from . import filtres as F
from . import modeles as M
from .config import Config
from .http import Navigateur
from .sources import ErreurSource, amazon, dealabs, ebay, enseignes, playstation

PORT_SI_INCONNU = 8.0   # quand les frais de port ne sont pas affichés, on suppose ça pour comparer au seuil


@dataclass
class Bilan:
    sources: list[M.ResultatSource] = field(default_factory=list)
    offres: list[M.Offre] = field(default_factory=list)       # toutes les offres retenues (fiables)
    alertes: list[M.Offre] = field(default_factory=list)      # < seuil, commandables
    compromis: list[M.Offre] = field(default_factory=list)    # entre seuil et seuil_compromis, enseignes
    duree: float = 0.0

    @property
    def disponibles(self) -> list[M.Offre]:
        return sorted([o for o in self.offres if o.disponible and o.total is not None], key=cle_tri)

    def meilleure(self, edition: str) -> M.Offre | None:
        d = [o for o in self.disponibles if o.edition == edition]
        return d[0] if d else None

    @property
    def nb_sources_ok(self) -> int:
        return sum(1 for s in self.sources if s.statut == "ok")


def cle_tri(o: M.Offre):
    return (total_pour_seuil(o), o.confiance, o.priorite_site)


def total_pour_seuil(o: M.Offre) -> float:
    if o.prix is None:
        return 1e9
    return o.prix + (PORT_SI_INCONNU if o.livraison is None else o.livraison)


def _executer(nom: str, fn) -> M.ResultatSource:
    debut = time.time()
    res = M.ResultatSource(nom=nom)
    try:
        sortie = fn()
        if isinstance(sortie, tuple):
            res.offres, res.detail = sortie[0], str(sortie[1] or "")
        else:
            res.offres = sortie or []
    except ErreurSource as e:
        res.statut = "bloque" if e.bloque else "erreur"
        res.detail = str(e)
    except Exception as e:  # un site qui change sa page ne doit jamais faire planter le reste
        res.statut = "erreur"
        res.detail = f"{type(e).__name__}: {e}"[:160]
        traceback.print_exc()
    res.duree = round(time.time() - debut, 1)
    print(f"  · {nom:<32} {res.statut:<8} {len(res.offres):>2} offre(s)  {res.detail[:90]}", flush=True)
    return res


def verifier(cfg: Config) -> Bilan:
    debut = time.time()
    nav = Navigateur()
    print(f"Vérification (empreinte navigateur : {nav.empreinte})", flush=True)
    sources: list[M.ResultatSource] = []
    urls_connues = {f["url"] for f in cfg.fiches}

    # 1) Officiel Sony
    for f in cfg.fiches:
        if "playstation.com" in f["url"]:
            sources.append(_executer(f"{f['site']} ({f['edition']})",
                                     lambda f=f: playstation.verifier_fiche(nav, f["url"], f["edition"])))

    # 2) Amazon (.fr d'abord, puis Europe)
    pays = ["fr"] + (["de", "it", "es"] if cfg.amazon_europe else [])
    asins = {a["asin"]: a["edition"] for a in cfg.amazon_asins}
    for tld in pays:
        def _amazon(tld=tld):
            offres = []
            for asin, ed in list(asins.items()):
                offres.extend(amazon.verifier_asin(nav, asin, ed, tld, cfg.amazon_port_europe))
            return offres
        sources.append(_executer(amazon.PAYS[tld][0], _amazon))

    # Recherche Amazon.fr : repère d'autres fiches (ex. la noire si Amazon la référence un jour)
    def _amazon_recherche():
        trouves, _ = amazon.rechercher(nav, "fr", "manette dualsense gta vi edition limitee")
        nouveaux = [(a, t) for a, t, _ in trouves if a not in asins][:3]
        offres = []
        for asin, titre in nouveaux:
            offres.extend(amazon.verifier_asin(nav, asin, F.detecter_edition(titre), "fr", 0.0))
        return offres, f"{len(trouves)} résultat(s), {len(nouveaux)} nouvelle(s) fiche(s)"
    sources.append(_executer("Amazon.fr (recherche)", _amazon_recherche))

    # 3) Fiches connues des autres enseignes (Fnac, Alternate, TopAchat...)
    for f in cfg.fiches:
        if "playstation.com" not in f["url"]:
            sources.append(_executer(f"{f['site']} ({f['edition']})",
                                     lambda f=f: enseignes.verifier_fiche(nav, f["site"], f["url"], f["edition"])))

    # 4) eBay
    def _ebay():
        offres, ecartees = ebay.rechercher(nav, cfg)
        return offres, f"{ecartees} annonce(s) écartée(s) (vendeur pas assez noté, hors UE, prix louche...)"
    sources.append(_executer("eBay", _ebay))

    # 5) Moteurs de recherche des enseignes
    vues = set(urls_connues)
    for nom, url in enseignes.RECHERCHES:
        sources.append(_executer(f"{nom} (recherche)", lambda nom=nom, url=url: enseignes.chercher(nav, nom, url, vues)))

    # 6) Dealabs (signal communautaire)
    sources.append(_executer("Dealabs", lambda: dealabs.rechercher(nav)))

    bilan = trier(sources, cfg)
    bilan.duree = round(time.time() - debut, 1)
    return bilan


def trier(sources: list[M.ResultatSource], cfg: Config) -> Bilan:
    bilan = Bilan(sources=sources)
    retenues: dict[str, M.Offre] = {}
    for s in sources:
        for o in s.offres:
            if not F.domaine_autorise(o.url):
                continue
            if o.edition not in cfg.editions and o.edition != "?":
                continue
            if not o.neuf and not cfg.accepter_occasion:
                continue
            if o.confiance in (M.MARKETPLACE, M.EBAY_PRO) and o.prix is not None and o.prix < cfg.ebay_prix_min_credible:
                continue
            ancienne = retenues.get(o.cle)
            if ancienne is None or (o.total or 1e9) < (ancienne.total or 1e9):
                retenues[o.cle] = o
    bilan.offres = sorted(retenues.values(), key=cle_tri)

    # Une offre "édition à confirmer" ne déclenche une alerte que si les deux éditions t'intéressent.
    edition_ok = lambda o: o.edition in cfg.editions or (o.edition == "?" and len(cfg.editions) >= 2)
    for o in bilan.disponibles:
        if not edition_ok(o):
            continue
        t = total_pour_seuil(o)
        if t < cfg.seuil_alerte:
            bilan.alertes.append(o)
        elif t < cfg.seuil_compromis and o.confiance in (M.OFFICIEL, M.ENSEIGNE):
            bilan.compromis.append(o)
    return bilan
