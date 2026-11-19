"""Point d'entrée : python -m traqueur [verifier|diagnostic|test-notif]"""
from __future__ import annotations

import sys


def main() -> int:
    commande = sys.argv[1] if len(sys.argv) > 1 else "verifier"
    if commande == "diagnostic":
        from .diagnostic import lancer
        lancer(sys.argv[2] if len(sys.argv) > 2 else "")
        return 0
    if commande == "verifier":
        print("Vérification pas encore branchée (installation en cours).")
        return 0
    print(f"Commande inconnue : {commande}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
