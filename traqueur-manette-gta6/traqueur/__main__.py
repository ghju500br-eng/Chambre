"""Point d'entrée : python -m traqueur [verifier|diagnostic|test-notif|essai]

  verifier    vérification complète + notifs + bilans (lancé toutes les heures par GitHub)
  diagnostic  teste chaque site et affiche ce qu'on reçoit (pour réparer un parseur)
  test-notif  envoie deux notifs de test sur ton téléphone
  essai       vérification complète SANS notif ni sauvegarde (affiche juste le résultat)
"""
from __future__ import annotations

import sys


def main() -> int:
    commande = sys.argv[1] if len(sys.argv) > 1 else "verifier"
    if commande == "verifier":
        from .tourner import lancer
        return lancer()
    if commande == "diagnostic":
        from .diagnostic import lancer as diag
        diag(sys.argv[2] if len(sys.argv) > 2 else "")
        return 0
    if commande == "test-notif":
        from .tourner import test_notif
        return test_notif()
    if commande == "essai":
        from . import config, rapport
        from .etat import maintenant
        from .verifier import verifier
        cfg = config.charger()
        bilan = verifier(cfg)
        print("\n" + rapport.statut_md(bilan, cfg, maintenant(), []))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
