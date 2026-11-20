"""Une vérification complète : interroge toutes les sources, trie, décide quoi signaler."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from . import filtres as F
from . import modeles as M
from .config import Config
from .http import Navigateur
from .sources import ErreurSource, amazon, dealabs, ebay, enseignes, idealo, playstation

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


def _type(f: dict) -> int:
    u = f["url"]
    return 1 if "playstation.com" in u else 2 if "idealo.fr" in u else 3


def fiches_a_verifier(cfg: Config, seulement_sony: bool = False) -> list[dict]:
    """Sony d'abord, puis idealo, puis les enseignes. Passage rapide = Sony seulement."""
    fiches = sorted(cfg.fiches, key=_type)
    return [f for f in fiches if _type(f) == 1] if seulement_sony else fiches


def verifier(cfg: Config, seulement_sony: bool = False) -> Bilan:
    debut = time.time()
    nav = Navigateur()
    print(f"Vérification {'Sony seulement' if seulement_sony else 'complète'} "
          f"(empreinte navigateur : {nav.empreinte})", flush=True)
    sources: list[M.ResultatSource] = []
    urls_connues = {f["url"] for f in cfg.fiches}

    # 1) Officiel Sony (playstation.com + PlayStation Store), 2) idealo (prix Amazon, Fnac & co),
    # 3) fiches connues des enseignes — dans cet ordre de priorité.
    for f in fiches_a_verifier(cfg, seulement_sony):
        nom = f"{f['site']} ({f['edition']})"
        if _type(f) == 1:
            sources.append(_executer(nom, lambda f=f: playstation.verifier_fiche(nav, f["url"], f["edition"])))
        elif _type(f) == 2:
            sources.append(_executer(nom, lambda f=f: idealo.verifier(nav, f["url"], f["edition"])))
        else:
            sources.append(_executer(nom, lambda f=f: enseignes.verifier_fiche(nav, f["site"], f["url"], f["edition"])))

    if seulement_sony:
        bilan = trier(sources, cfg)
        bilan.duree = round(time.time() - debut, 1)
        return bilan

    # 4) Moteurs de recherche des enseignes (repère les nouvelles fiches)
    vues = set(urls_connues)
    for nom, url in enseignes.RECHERCHES:
        sources.append(_executer(f"{nom} (recherche)", lambda nom=nom, url=url: enseignes.chercher(nav, nom, url, vues)))

    # 5) Dealabs (signal communautaire)
    sources.append(_executer("Dealabs", lambda: dealabs.rechercher(nav)))

    # 6) Accès directs à Amazon / eBay : désactivés par défaut (ils refusent les robots, on respecte).
    if cfg.amazon_direct:
        asins = {a["asin"]: a["edition"] for a in cfg.amazon_asins}
        for tld in ["fr"] + (["de", "it", "es"] if cfg.amazon_europe else []):
            sources.append(_executer(amazon.PAYS[tld][0], lambda tld=tld: [
                o for asin, ed in asins.items() for o in amazon.verifier_asin(nav, asin, ed, tld, cfg.amazon_port_europe)]))
    if cfg.ebay_direct:
        def _ebay():
            offres, ecartees = ebay.rechercher(nav, cfg)
            return offres, f"{ecartees} annonce(s) écartée(s) (vendeur pas assez noté, hors UE, prix louche...)"
        sources.append(_executer("eBay", _ebay))

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
