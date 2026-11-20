"""Mise en forme des bilans (notifs, commentaires GitHub, page STATUT.md)."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime

from . import modeles as M
from .config import Config
from .verifier import Bilan

PASTILLE = {"blanche": "⚪", "noire": "⚫", "?": "❔"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def euros(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def heure(dt: datetime) -> str:
    return dt.strftime("%Hh%M")


def date_longue(dt: datetime) -> str:
    return f"{JOURS[dt.weekday()]} {dt.strftime('%d/%m')} à {heure(dt)}"


def url_statut() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branche = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://github.com/{repo}/blob/{branche}/traqueur-manette-gta6/STATUT.md" if repo else ""


def port(o: M.Offre) -> str:
    if o.livraison is None:
        return "port inconnu"
    if o.livraison == 0:
        return "port offert"
    return f"port {'≈' if o.site.startswith('Amazon.') and o.site != 'Amazon.fr' else ''}{euros(o.livraison)}"


def ligne(o: M.Offre, avec_edition: bool = True) -> str:
    ed = f"{PASTILLE.get(o.edition, '')} {M.EDITIONS.get(o.edition, o.edition)} · " if avec_edition else ""
    return f"{ed}{euros(o.total)} — {o.site} · {o.vendeur} · {o.etat_stock} · {port(o)}"


# ── Notifications ────────────────────────────────────────────────────────────
def titre_alerte(o: M.Offre, raison: str) -> str:
    prefixe = {"retour": "🔁 RETOUR EN STOCK", "baisse": "📉 BAISSE DE PRIX"}.get(raison, "🚨 TROUVÉE")
    return f"{prefixe} : GTA VI {M.EDITIONS.get(o.edition, '')} à {euros(o.total)} — {o.site}"


def message_alerte(o: M.Offre) -> str:
    lignes = [
        f"{o.titre}",
        f"Vendeur : {o.vendeur} ({M.LIBELLE_CONFIANCE.get(o.confiance, '')})",
        f"Stock : {o.etat_stock}",
        f"Prix : {euros(o.prix)} + {port(o)} = {euros(o.total)}",
    ]
    if o.remarque:
        lignes.append(f"⚠️ {o.remarque}")
    lignes.append("👉 Fonce, ces manettes partent en quelques minutes.")
    return "\n".join(lignes)


def corps_issue_alerte(o: M.Offre, raison: str, maintenant: datetime) -> str:
    return (f"### {titre_alerte(o, raison)}\n\n"
            f"| | |\n|---|---|\n"
            f"| **Produit** | {o.titre} |\n| **Édition** | {M.EDITIONS.get(o.edition, o.edition)} |\n"
            f"| **Site** | {o.site} |\n| **Vendeur** | {o.vendeur} — {M.LIBELLE_CONFIANCE.get(o.confiance, '')} |\n"
            f"| **Stock** | {o.etat_stock} |\n| **Prix** | {euros(o.prix)} + {port(o)} = **{euros(o.total)}** |\n"
            f"| **Repérée** | {date_longue(maintenant)} |\n\n"
            f"## 👉 [Ouvrir l'offre]({o.url})\n\n"
            + (f"> ⚠️ {o.remarque}\n\n" if o.remarque else "")
            # Mention du propriétaire du repo = notif garantie (appli GitHub + email), même sans ntfy.
            + (f"@{os.environ['GITHUB_REPOSITORY_OWNER']} fonce ! 🏃\n\n" if os.environ.get("GITHUB_REPOSITORY_OWNER") else "")
            + "_Cette issue se ferme toute seule quand l'offre disparaît._")


def resume_court(bilan: Bilan, cfg: Config) -> str:
    """Quelques lignes pour le petit bilan discret (toutes les 30 min)."""
    lignes = []
    for ed in cfg.editions:
        m = bilan.meilleure(ed)
        nom = M.EDITIONS[ed]
        if m:
            lignes.append(f"{PASTILLE[ed]} {nom} : mieux dispo {euros(m.total)} ({m.site})")
        else:
            lignes.append(f"{PASTILLE[ed]} {nom} : rien de dispo chez les vendeurs fiables")
    officiels = [o for o in bilan.offres if o.confiance == M.OFFICIEL]
    if officiels:
        etats = {f"{M.EDITIONS[o.edition]} {'✅ ' + o.etat_stock if o.disponible else '❌ rupture'}"
                 for o in officiels if o.edition in cfg.editions}
        lignes.append("🎮 Sony : " + " · ".join(sorted(etats)))
    lignes.append(_ligne_sources(bilan))
    return "\n".join(lignes)


def _ligne_sources(bilan: Bilan) -> str:
    ko = [s.nom.split(" (")[0] for s in bilan.sources if s.statut != "ok"]
    ko = sorted(set(ko))
    txt = f"📡 Sources OK : {bilan.nb_sources_ok}/{len(bilan.sources)}"
    if ko:
        txt += " (KO : " + ", ".join(ko[:6]) + ("…" if len(ko) > 6 else "") + ")"
    return txt


def bilan_quotidien(bilan: Bilan, cfg: Config, histo_jour: list[dict], alertes_jour: int,
                    maintenant: datetime) -> tuple[str, str]:
    titre = f"📊 Bilan du {maintenant.strftime('%d/%m')} — manette GTA VI"
    lignes = [f"Vérifications aujourd'hui : {len({h['date'] for h in histo_jour})} (dernière à {heure(maintenant)})"]
    for ed in cfg.editions:
        prix_jour = [(float(h["meilleur_dispo"]), h["site"]) for h in histo_jour
                     if h["edition"] == ed and h.get("meilleur_dispo")]
        nom = f"{PASTILLE[ed]} {M.EDITIONS[ed]}"
        actuel = bilan.meilleure(ed)
        if prix_jour:
            p, s = min(prix_jour)
            lignes.append(f"{nom} : meilleur prix vu aujourd'hui {euros(p)} ({s}) · maintenant : "
                          f"{euros(actuel.total) + ' (' + actuel.site + ')' if actuel else 'rien de dispo'}")
        else:
            lignes.append(f"{nom} : rien de dispo chez les vendeurs fiables de la journée")
    lignes.append(f"🚨 Alertes sous {euros(cfg.seuil_alerte)} aujourd'hui : {alertes_jour}")
    officiels = [o for o in bilan.offres if o.confiance in (M.OFFICIEL, M.ENSEIGNE) and o.edition in cfg.editions]
    if officiels:
        lignes.append("🏬 Officiel et enseignes en ce moment :")
        for o in sorted(officiels, key=lambda o: (o.priorite_site, o.site))[:10]:
            lignes.append(f"   • {o.site} {M.EDITIONS[o.edition]} : {euros(o.prix)} — "
                          f"{o.etat_stock if o.disponible else '❌ ' + o.etat_stock}")
    lignes.append(_ligne_sources(bilan))
    return titre, "\n".join(lignes)


# ── Page STATUT.md ───────────────────────────────────────────────────────────
def _tableau(offres: list[M.Offre]) -> list[str]:
    l = ["| Total | Édition | Site | Vendeur | Stock | Lien |", "|---:|---|---|---|---|---|"]
    for o in offres:
        l.append(f"| **{euros(o.total)}** | {PASTILLE.get(o.edition, '')} {M.EDITIONS.get(o.edition, o.edition)} "
                 f"| {o.site} | {o.vendeur} | {o.etat_stock} · {port(o)} | [voir]({o.url}) |")
    return l


def statut_md(bilan: Bilan, cfg: Config, maintenant: datetime, histo: list[dict]) -> str:
    md = ["# 🎮 Traqueur — manette DualSense édition limitée GTA VI", "",
          f"> Dernière vérification : **{date_longue(maintenant)}** (heure de Paris) · prochaine dans ~30 min — Sony est vérifié toutes les 8 min  ",
          f"> Objectif : **moins de {euros(cfg.seuil_alerte)} port compris**, uniquement chez des vendeurs fiables.  ",
          f"> Prix officiel Sony : 84,99 €.", ""]

    md += [f"## 🚨 Offres sous {euros(cfg.seuil_alerte)} disponibles maintenant", ""]
    md += (_tableau(bilan.alertes) if bilan.alertes else ["_Aucune pour l'instant. Tu seras prévenu dès qu'il y en a une._"])
    md += ["", "## 🏆 Meilleurs compromis disponibles (tous prix, vendeurs vérifiés)", ""]
    dispo = bilan.disponibles[:12]
    md += (_tableau(dispo) if dispo else ["_Rien de commandable chez les vendeurs fiables en ce moment._"])

    md += ["", "## 🏬 Sony et enseignes (même en rupture)", "",
           "| Site | Édition | Prix | Stock | Lien |", "|---|---|---:|---|---|"]
    vus = set()
    for o in sorted([o for o in bilan.offres if o.confiance in (M.OFFICIEL, M.ENSEIGNE)],
                    key=lambda o: (o.priorite_site, o.site, o.edition)):
        k = (o.site, o.edition, o.prix)
        if k in vus:
            continue
        vus.add(k)
        md.append(f"| {o.site} | {PASTILLE.get(o.edition, '')} {M.EDITIONS.get(o.edition, o.edition)} | {euros(o.prix)} "
                  f"| {'✅ ' if o.disponible else '❌ '}{o.etat_stock} | [voir]({o.url}) |")

    md += ["", "## 📡 État des sources", "", "| Source | Statut | Offres | Détail |", "|---|---|---:|---|"]
    icone = {"ok": "✅", "bloque": "🧱 bloqué", "erreur": "⚠️ erreur", "introuvable": "❓"}
    for s in bilan.sources:
        md.append(f"| {s.nom} | {icone.get(s.statut, s.statut)} | {len(s.offres)} | {s.detail[:110]} |")

    md += ["", "## 📈 Historique — meilleur prix dispo (vendeurs fiables)", "",
           "| Jour | ⚪ Blanche | ⚫ Noire |", "|---|---:|---:|"]
    par_jour: dict[str, dict[str, float]] = defaultdict(dict)
    for h in histo:
        if not h.get("meilleur_dispo"):
            continue
        j, ed, p = h["date"][:10], h["edition"], float(h["meilleur_dispo"])
        par_jour[j][ed] = min(p, par_jour[j].get(ed, 1e9))
    jours = sorted({h["date"][:10] for h in histo}, reverse=True)[:14]
    for j in jours:
        md.append(f"| {j[8:10]}/{j[5:7]} | {euros(par_jour[j].get('blanche'))} | {euros(par_jour[j].get('noire'))} |")
    md += ["", f"_Vérification faite en {bilan.duree:.0f} s. Réglages : `config.toml`._", ""]
    return "\n".join(md)
