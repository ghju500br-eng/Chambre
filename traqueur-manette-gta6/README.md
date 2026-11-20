# 🎮 Traqueur de manette DualSense édition limitée GTA VI

Ce robot cherche **toutes les heures** la manette PS5 DualSense édition limitée *Grand Theft Auto VI*
(**blanche** et **noire**) chez des vendeurs fiables uniquement, et te prévient sur ton téléphone.
Il tourne sur les serveurs de GitHub : ton téléphone peut être éteint, ça continue (les notifs arrivent
quand tu le rallumes).

👉 **Résultats en direct : [STATUT.md](STATUT.md)** (mis à jour à chaque vérification)

## Ce qu'il fait

| Quand | Quoi | Comment |
|---|---|---|
| Une manette est commandable à **moins de 100 €** port compris chez un vendeur fiable | 🚨 **Alerte urgente** (sonnerie) avec un bouton pour ouvrir l'offre | push ntfy + issue GitHub (email) |
| Retour en stock ou baisse de prix d'une offre déjà vue | 🔁 / 📉 nouvelle alerte | push + issue |
| PS Direct ou une enseigne la vend entre 100 et 110 € | 👌 notif « bon compromis » | push |
| Chaque heure | 🔎 petit bilan **discret** (sans son ni vibration) | push |
| Chaque soir à 20 h | 📊 récap de la journée | push + commentaire GitHub (email) |

Jamais deux fois la même alerte. Si l'offre disparaît, son issue se ferme toute seule.

## Sites surveillés (et seulement eux)

| Priorité | Source | Ce qu'on y lit |
|---|---|---|
| ⭐ 1 | **Sony** : playstation.com + PlayStation Store (PlayStation Direct y est intégré en France) | stock officiel des deux éditions — seul vendeur de la **noire** en France |
| ⭐ 1 | **idealo** (comparateur) | les offres d'**Amazon**, de la **Fnac** et des autres enseignes qui y sont référencées ; les petites boutiques inconnues sont écartées |
| 2 | E.Leclerc, TopAchat (fiches de la blanche), Micromania, Boulanger, Auchan, LDLC (recherche auto) | grandes enseignes ; un vendeur tiers de leur marketplace est signalé comme tel |
| signal | Dealabs | un deal n'est retenu que si le marchand est une enseigne fiable |

Toute offre dont le lien ne pointe pas vers un de ces sites est jetée. Les coques, skins, boîtes vides,
packs console, codes de jeu et annonces louches sont filtrés.

**Sites qui refusent les robots** (testé le 20/11/2026 depuis les serveurs GitHub) : Amazon (captcha),
Fnac, Darty (DataDome), eBay (403), Cultura, Carrefour, Cdiscount. Le traqueur **respecte ce refus** et ne
cherche pas à le contourner : leurs prix arrivent via idealo et Dealabs quand ils y sont. Pour eBay, la
voie propre serait son API officielle (compte développeur gratuit) — le code est prêt (`[ebay] acces_direct`).

## Installation (5 minutes, une seule fois)

1. **Installe l'appli ntfy** sur ton téléphone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) ·
   [iPhone](https://apps.apple.com/app/ntfy/id1625396347)). Gratuite, sans compte.
2. Dans ntfy, appuie sur **+** et abonne-toi à ton sujet secret (un nom long et imprévisible, par ex.
   `manette-gta6-xxxxxxxxxxxx`). Garde-le pour toi : quiconque le connaît peut lire tes notifs.
3. Sur GitHub, ouvre <https://github.com/ghju500br-eng/Chambre/settings/secrets/actions/new>
   (ou **Settings → Secrets and variables → Actions → New repository secret**) :
   - Name : `NTFY_TOPIC`
   - Secret : ton sujet (exactement le même que dans l'appli) → **Add secret**
4. Onglet **Actions → Traqueur manette GTA VI → Run workflow**, mode `test-notif` : tu dois recevoir 2 notifs
   (une qui sonne, une discrète).
5. Relance avec le mode `verifier` pour la première vraie recherche. Ensuite c'est automatique toutes les heures.

Sans l'étape ntfy, le traqueur marche quand même : les alertes et les bilans quotidiens arrivent
par **email / appli GitHub** via les issues du repo (vérifie que tu « Watch » le repo).

## Réglages

Tout est dans [`config.toml`](config.toml), modifiable directement sur GitHub (icône ✏️) :
seuil d'alerte, éditions voulues, occasion oui/non, exigences eBay, bilan horaire on/off, heure du récap…
Pour surveiller une nouvelle fiche produit, ajoute un bloc `[[fiches]]` avec son URL.

Pour vérifier plus souvent (ex. toutes les 15 min), change la ligne `cron` dans
`.github/workflows/traqueur-manette-gta6.yml` en `"*/15 * * * *"`.

## À savoir (honnêtement)

- **Une vérif par heure peut rater un réassort éclair** : sur ces manettes, un retour en stock chez Fnac/Amazon
  peut partir en 10-20 minutes. Passer à 15 min augmente les chances.
- **idealo a un léger décalage** : ses prix sont mis à jour par les marchands, pas en temps réel.
  Quand idealo ne donne pas les frais de port, le traqueur compte ≈ 8 € par prudence pour le seuil.
- Si un site se met à bloquer, la page de statut l'indique (🧱 bloqué) au lieu de prétendre qu'il n'y a rien.
- GitHub peut décaler les vérifs de quelques minutes quand ses serveurs sont chargés.
- Le robot ne commande rien à ta place : il te prévient, c'est toi qui achètes.

## Pour les curieux

```
python -m traqueur verifier     # vérification complète (ce que lance GitHub chaque heure)
python -m traqueur essai        # vérification sans notif ni sauvegarde
python -m traqueur diagnostic   # montre ce que chaque site renvoie (pour réparer un parseur)
python -m traqueur test-notif   # envoie 2 notifs de test (NTFY_TOPIC requis)
python -m unittest discover -s tests -v
```
