"""Exécutions planifiées : vérifier, prévenir (sans spammer), faire les bilans, mémoriser.

- lancer()       : vérification complète (toutes les 30 min) + bilans + page de statut
- lancer_sony()  : passage rapide sur Sony seulement (toutes les 8 min), alertes uniquement
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config as C
from . import etat as E
from . import modeles as M
from . import notifications as N
from . import rapport as R
from .verifier import Bilan, verifier

MAX_PUSH_PAR_VERIF = 3


def lancer() -> int:
    cfg = C.charger()
    etat = E.charger()
    maintenant = E.maintenant()
    if not N.ntfy_actif():
        print("⚠️  NTFY_TOPIC non configuré : pas de push téléphone (les issues GitHub fonctionnent quand même).")

    bilan = verifier(cfg)
    print(f"\n{len(bilan.offres)} offre(s) fiable(s), {len(bilan.disponibles)} commandable(s), "
          f"{len(bilan.alertes)} sous le seuil, {len(bilan.compromis)} compromis. ({bilan.duree:.0f} s)")

    premier = "premier_lancement" not in etat
    if premier:
        etat["premier_lancement"] = maintenant.isoformat()
        accueil(bilan, cfg, etat)

    envoyes = signaler(bilan, cfg, etat, maintenant)

    # Historique
    lignes = []
    for ed in cfg.editions:
        m = bilan.meilleure(ed)
        lignes.append({"date": maintenant.strftime("%Y-%m-%d %H:%M"), "edition": ed,
                       "meilleur_dispo": f"{m.total:.2f}" if m else "", "site": m.site if m else "",
                       "vendeur": m.vendeur if m else "",
                       "nb_offres_dispo": sum(1 for o in bilan.disponibles if o.edition == ed),
                       "sources_ok": bilan.nb_sources_ok, "sources_total": len(bilan.sources)})
    E.ajouter_historique(lignes)
    histo = E.lire_historique()

    # Petit bilan discret (toutes les 30 min) — inutile si on vient d'envoyer une alerte ou l'accueil
    if cfg.bilan_horaire and not envoyes and not premier:
        if bilan.nb_sources_ok == 0:
            titre = f"⚠️ {R.heure(maintenant)} · aucun site n'a répondu (souci réseau ?)"
        elif not bilan.disponibles:
            titre = f"🔎 {R.heure(maintenant)} · rien de dispo chez les vendeurs fiables"
        else:
            titre = (f"🔎 {R.heure(maintenant)} · mieux dispo {R.euros(bilan.disponibles[0].total)} "
                     f"(objectif < {R.euros(cfg.seuil_alerte)})")
        N.push(titre, R.resume_court(bilan, cfg), N.DISCRETE, ["mag"], clic=R.url_statut() or None)

    # Bilan quotidien
    aujourd_hui = maintenant.strftime("%Y-%m-%d")
    if maintenant.hour >= cfg.heure_bilan_quotidien and etat.get("dernier_bilan_quotidien") != aujourd_hui:
        histo_jour = [h for h in histo if h["date"].startswith(aujourd_hui)]
        alertes_jour = etat.get("alertes_par_jour", {}).get(aujourd_hui, 0)
        titre, texte = R.bilan_quotidien(bilan, cfg, histo_jour, alertes_jour, maintenant)
        N.push(titre, texte, N.NORMALE, ["bar_chart"], clic=R.url_statut() or None)
        numero = _issue_bilans(etat)
        if numero:
            N.commenter_issue(numero, f"### {titre}\n\n" + texte.replace("\n", "  \n")
                              + (f"\n\n[📄 Page de statut complète]({R.url_statut()})" if R.url_statut() else ""))
        etat["dernier_bilan_quotidien"] = aujourd_hui

    # Mémoire
    etat["derniere_verif"] = maintenant.isoformat()
    etat["nb_verifs"] = int(etat.get("nb_verifs", 0)) + 1
    sources = etat.setdefault("sources", {})
    for s in bilan.sources:
        info = sources.setdefault(s.nom, {})
        info["statut"] = s.statut
        if s.statut == "ok":
            info["dernier_ok"] = maintenant.isoformat()
    jours = sorted(etat.get("alertes_par_jour", {}))
    for j in jours[:-30]:
        etat["alertes_par_jour"].pop(j, None)
    E.sauver(etat)
    (C.RACINE / "STATUT.md").write_text(R.statut_md(bilan, cfg, maintenant, histo), encoding="utf-8")
    return 0


def lancer_sony() -> int:
    """Passage rapide : seulement les fiches Sony. Pas de bilan ni de page de statut (ça, c'est toutes
    les 30 min). L'état n'est réécrit que s'il s'est passé quelque chose, pour ne pas faire un commit
    toutes les 8 minutes pour rien."""
    etat = E.charger()
    if "premier_lancement" not in etat:
        return lancer()
    cfg = C.charger()
    maintenant = E.maintenant()
    bilan = verifier(cfg, seulement_sony=True)
    avant = json.dumps(etat.get("signalees", {}), sort_keys=True)
    envoyes = signaler(bilan, cfg, etat, maintenant)
    if envoyes or json.dumps(etat.get("signalees", {}), sort_keys=True) != avant:
        E.sauver(etat)
    dispo = [o for o in bilan.offres if o.disponible]
    print(f"\nSony : {len(dispo)} édition(s) commandable(s), {envoyes} alerte(s) envoyée(s). ({bilan.duree:.0f} s)")
    return 0


def signaler(bilan: Bilan, cfg: C.Config, etat: dict, maintenant: datetime) -> int:
    """Alerte pour chaque offre nouvelle / revenue / moins chère. Jamais deux fois la même chose."""
    signalees: dict = etat.setdefault("signalees", {})
    sources_ok = {s.nom for s in bilan.sources if s.statut == "ok"}
    source_de = {o.cle: s.nom for s in bilan.sources for o in s.offres}
    a_envoyer: list[tuple[M.Offre, str, str]] = []
    presentes = set()

    for o in bilan.alertes + bilan.compromis:
        type_ = "alerte" if o in bilan.alertes else "compromis"
        presentes.add(o.cle)
        prev = signalees.get(o.cle)
        raison = None
        if prev is None:
            raison = "nouveau"
        elif prev.get("absent_depuis"):
            raison = "retour"
        elif o.total is not None and prev.get("total") and o.total <= float(prev["total"]) - 1:
            raison = "baisse"
        elif type_ == "alerte" and prev.get("type") == "compromis":
            raison = "nouveau"
        if raison:
            a_envoyer.append((o, type_, raison))
        entree = signalees.setdefault(o.cle, {})
        entree.update({"vu_le": maintenant.isoformat(), "site": o.site, "url": o.url, "titre": o.titre[:100],
                       "source": source_de.get(o.cle, o.site)})
        entree.pop("absent_depuis", None)
        if raison:
            entree.update({"total": o.total, "type": type_, "notifie_le": maintenant.isoformat()})

    # Les alertes d'abord, puis les compromis ; les moins chères d'abord.
    a_envoyer.sort(key=lambda x: (x[1] != "alerte", x[0].total or 1e9))
    envoyes = 0
    for i, (o, type_, raison) in enumerate(a_envoyer):
        if i < MAX_PUSH_PAR_VERIF:
            if type_ == "alerte":
                N.push(R.titre_alerte(o, raison), R.message_alerte(o), N.URGENTE, ["rotating_light"], clic=o.url,
                       boutons=[("🛒 Ouvrir l'offre", o.url)] + ([("📄 Bilan", R.url_statut())] if R.url_statut() else []))
            else:
                N.push(f"👌 Bon compromis : GTA VI {M.EDITIONS.get(o.edition, '')} à {R.euros(o.total)} — {o.site}",
                       R.message_alerte(o), N.HAUTE, ["ok_hand"], clic=o.url, boutons=[("🛒 Ouvrir l'offre", o.url)])
            envoyes += 1
        if type_ == "alerte":
            jour = maintenant.strftime("%Y-%m-%d")
            etat.setdefault("alertes_par_jour", {})[jour] = etat.get("alertes_par_jour", {}).get(jour, 0) + 1
            entree = signalees[o.cle]
            if entree.get("issue") and N.issue_ouverte(entree["issue"]):
                N.commenter_issue(entree["issue"], R.corps_issue_alerte(o, raison, maintenant))
            else:
                entree["issue"] = N.creer_issue(R.titre_alerte(o, raison), R.corps_issue_alerte(o, raison, maintenant))
    reste = len(a_envoyer) - MAX_PUSH_PAR_VERIF
    if reste > 0:
        N.push(f"➕ {reste} autre(s) offre(s) intéressante(s)", "Toutes les offres sont sur la page de statut.",
               N.HAUTE, ["heavy_plus_sign"], clic=R.url_statut() or None)

    # Offres disparues : on ne conclut que si le site a bien répondu (sinon c'est peut-être juste un blocage).
    for cle, entree in list(signalees.items()):
        if cle in presentes:
            continue
        if entree.get("source") not in sources_ok:
            continue
        if not entree.get("absent_depuis"):
            entree["absent_depuis"] = maintenant.isoformat()
            if entree.get("issue"):
                N.fermer_issue(entree["issue"], f"❌ Offre plus disponible (ou prix remonté) — constaté le "
                                                f"{R.date_longue(maintenant)}.")
                entree["issue"] = None
        elif (maintenant - datetime.fromisoformat(entree["absent_depuis"])).total_seconds() > 3 * 86400:
            del signalees[cle]
    return envoyes


def accueil(bilan: Bilan, cfg: C.Config, etat: dict) -> None:
    texte = ("Je vérifie Sony (PlayStation) toutes les 8 minutes, et idealo (Amazon, Fnac…), les grandes "
             "enseignes et Dealabs toutes les 30 minutes.\n"
             f"🚨 Notif urgente si une manette est dispo à moins de {R.euros(cfg.seuil_alerte)} chez un vendeur fiable.\n"
             "🔎 Petit bilan discret à chaque vérif, 📊 récap complet chaque soir.\n\n" + R.resume_court(bilan, cfg))
    N.push("✅ Traqueur manette GTA VI activé", texte, N.NORMALE, ["video_game"], clic=R.url_statut() or None)
    _issue_bilans(etat)


def _issue_bilans(etat: dict) -> int | None:
    numero = etat.get("issue_bilans")
    if numero:
        return int(numero)
    numero = N.creer_issue("📊 Bilans quotidiens du traqueur de manette GTA VI",
                           "Le traqueur poste ici un récap chaque soir (tu le reçois par email / appli GitHub).\n\n"
                           "Les alertes de prix ont chacune leur propre issue (🚨) qui se ferme toute seule "
                           "quand l'offre disparaît.")
    if numero:
        etat["issue_bilans"] = numero
    return numero


def test_notif() -> int:
    ok1 = N.push("🧪 Test : notif urgente (alerte)", "Si tu lis ça avec du son, les alertes marchent. 🎮",
                 N.URGENTE, ["rotating_light"])
    ok2 = N.push("🧪 Test : notif discrète (petit bilan)", "Celle-ci arrive sans son ni vibration.",
                 N.DISCRETE, ["mag"])
    print("Notifs envoyées." if ok1 and ok2 else "Échec : vérifie le secret NTFY_TOPIC.")
    return 0 if ok1 and ok2 else 1
