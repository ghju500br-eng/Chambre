"""Envoi des notifications : push sur le téléphone (ntfy) + issues GitHub (email / appli GitHub)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

NTFY_SERVEUR = os.environ.get("NTFY_SERVEUR", "https://ntfy.sh")

# Priorités ntfy : 1 = invisible, 2 = discrète (pas de son), 3 = normale, 4 = haute, 5 = urgente (sonne fort).
DISCRETE, NORMALE, HAUTE, URGENTE = 2, 3, 4, 5


def _requete(url: str, donnees: dict | None, entetes: dict, methode: str = "POST") -> dict | None:
    corps = json.dumps(donnees).encode("utf-8") if donnees is not None else None
    req = urllib.request.Request(url, data=corps, method=methode, headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            texte = r.read().decode("utf-8") or "{}"
            return json.loads(texte)
    except urllib.error.HTTPError as e:
        print(f"  ! {methode} {url} → HTTP {e.code} : {e.read()[:200]!r}")
    except Exception as e:
        print(f"  ! {methode} {url} → {type(e).__name__}: {e}")
    return None


# ── ntfy (push téléphone) ────────────────────────────────────────────────────
def ntfy_actif() -> bool:
    return bool(os.environ.get("NTFY_TOPIC"))


def push(titre: str, message: str, priorite: int = NORMALE, tags: list[str] | None = None,
         clic: str | None = None, boutons: list[tuple[str, str]] | None = None) -> bool:
    sujet = os.environ.get("NTFY_TOPIC", "").strip()
    if not sujet:
        print(f"  (ntfy non configuré) {titre}")
        return False
    donnees = {"topic": sujet, "title": titre[:250], "message": message[:3900], "priority": priorite,
               "tags": tags or []}
    if clic:
        donnees["click"] = clic
    if boutons:
        donnees["actions"] = [{"action": "view", "label": l[:40], "url": u, "clear": False} for l, u in boutons[:3]]
    ok = _requete(NTFY_SERVEUR, donnees, {"Content-Type": "application/json"}) is not None
    print(f"  → push {'envoyé' if ok else 'ÉCHEC'} (priorité {priorite}) : {titre}")
    return ok


# ── GitHub (issues = email + notif appli GitHub, sans rien configurer) ───────
def _gh(chemin: str, donnees: dict | None = None, methode: str = "POST") -> dict | None:
    jeton, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not jeton or not repo:
        return None
    return _requete(f"https://api.github.com/repos/{repo}{chemin}", donnees, {
        "Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
        "User-Agent": "traqueur-manette"}, methode)


def github_actif() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY"))


def creer_issue(titre: str, corps: str) -> int | None:
    r = _gh("/issues", {"title": titre[:250], "body": corps[:60000]})
    if r and r.get("number"):
        print(f"  → issue GitHub #{r['number']} : {titre}")
        return int(r["number"])
    return None


def commenter_issue(numero: int, corps: str) -> bool:
    return _gh(f"/issues/{numero}/comments", {"body": corps[:60000]}) is not None


def fermer_issue(numero: int, commentaire: str | None = None) -> None:
    if commentaire:
        commenter_issue(numero, commentaire)
    _gh(f"/issues/{numero}", {"state": "closed", "state_reason": "completed"}, "PATCH")


def issue_ouverte(numero: int) -> bool:
    r = _gh(f"/issues/{numero}", None, "GET")
    return bool(r and r.get("state") == "open")
