"""Tests hors ligne : parseurs (HTML d'exemple), filtres, et logique d'alerte anti-spam.

Lancement : python -m unittest discover -s tests -v   (depuis traqueur-manette-gta6/)
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traqueur import filtres as F  # noqa: E402
from traqueur import modeles as M  # noqa: E402
from traqueur import tourner  # noqa: E402
from traqueur.config import Config, charger  # noqa: E402
from traqueur.etat import PARIS  # noqa: E402
from traqueur.sources import amazon, dealabs, ebay, idealo, playstation  # noqa: E402
from traqueur.sources.fiche import analyser_fiche, liens_produits  # noqa: E402
from traqueur.verifier import fiches_a_verifier, trier  # noqa: E402


def cfg_test(**kw) -> Config:
    c = Config(ebay_pays=["France", "Allemagne", "Belgique"])
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestFiltres(unittest.TestCase):
    def test_bonne_manette(self):
        self.assertTrue(F.est_la_manette("Manette sans fil DualSense® - Édition limitée Grand Theft Auto VI Black"))
        self.assertTrue(F.est_la_manette("Mando Inalámbrico DualSense Grand Theft Auto VI Limited Edition"))
        self.assertFalse(F.est_la_manette("Manette Sans Fil Dualsense + Grand Theft Auto VI (code De Téléchargement)"))
        self.assertFalse(F.est_la_manette("Coque skin manette PS5 GTA VI", strict=True))
        self.assertFalse(F.est_la_manette("Manette DualSense blanche", strict=True))  # pas GTA
        self.assertFalse(F.est_la_manette("Manette compatible PS5 style GTA 6", strict=True))
        self.assertTrue(F.est_la_manette("Manette PS5 GTA 6 édition limitée blanche neuve", strict=True))

    def test_editions(self):
        self.assertEqual(F.detecter_edition("DualSense GTA VI White Limited Edition"), "blanche")
        self.assertEqual(F.detecter_edition("DualSense GTA VI édition limitée noire"), "noire")
        self.assertEqual(F.detecter_edition("Controller GTA VI Weiß"), "blanche")
        self.assertEqual(F.detecter_edition("Manette GTA VI"), "?")

    def test_prix(self):
        self.assertEqual(F.lire_prix("84,99 €"), 84.99)
        self.assertEqual(F.lire_prix("1 234,56 €"), 1234.56)
        self.assertEqual(F.lire_prix("84€99"), 84.99)
        self.assertEqual(F.lire_prix("84.99"), 84.99)
        self.assertIsNone(F.lire_prix(""))

    def test_domaines(self):
        self.assertTrue(F.domaine_autorise("https://www.fnac.com/a23608238/w-4"))
        self.assertFalse(F.domaine_autorise("https://www.fnac.com.arnaque.ru/a1"))
        self.assertFalse(F.domaine_autorise("https://www.wish.com/x"))

    def test_config_reelle(self):
        c = charger()
        self.assertEqual(c.seuil_alerte, 100.0)
        self.assertIn("blanche", c.editions)
        self.assertTrue(all(F.domaine_autorise(f["url"]) for f in c.fiches))


FICHE_FNAC = """<html><head><title>Manette</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
"name":"Manette gaming sans fil Sony DualSense® Édition limitée Grand Theft Auto VI Blanc pour PS5 et PC",
"offers":[{"@type":"Offer","price":"84.99","priceCurrency":"EUR","availability":"https://schema.org/OutOfStock",
"seller":{"@type":"Organization","name":"Fnac.com"}},
{"@type":"Offer","price":"209.09","priceCurrency":"EUR","availability":"https://schema.org/InStock",
"seller":{"@type":"Organization","name":"COLLECTORGAMES"}}]}</script>
<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"ListItem","item":
{"@type":"Product","name":"Câble USB-C","offers":{"@type":"Offer","price":"9.99","availability":"InStock"}}}]}</script>
</head><body></body></html>"""


class TestFiche(unittest.TestCase):
    def test_jsonld_fnac(self):
        offres, nom = analyser_fiche(FICHE_FNAC, "https://www.fnac.com/a23608238/w-4", site="Fnac", edition="blanche")
        self.assertEqual(len(offres), 2)  # le câble USB recommandé est ignoré
        fnac = next(o for o in offres if o.vendeur == "Fnac.com")
        tiers = next(o for o in offres if o.vendeur == "COLLECTORGAMES")
        self.assertFalse(fnac.disponible)
        self.assertEqual(fnac.confiance, M.ENSEIGNE)
        self.assertTrue(tiers.disponible)
        self.assertEqual(tiers.confiance, M.MARKETPLACE)
        self.assertEqual(tiers.total, 209.09)

    def test_meta_repli(self):
        html = """<html><head><meta property="og:title" content="DualSense Grand Theft Auto VI White Limited Edition">
        <meta property="product:price:amount" content="84.99"><meta property="product:availability" content="instock">
        </head></html>"""
        offres, _ = analyser_fiche(html, "https://www.micromania.fr/p/x.html", site="Micromania")
        self.assertEqual(len(offres), 1)
        self.assertTrue(offres[0].disponible)
        self.assertEqual(offres[0].edition, "blanche")

    def test_liens_recherche(self):
        html = """<a href="/p/manette-gta-vi-blanche-123.html">Manette DualSense Édition Limitée GTA VI Blanche</a>
        <a href="/p/coque.html">Coque manette GTA VI</a><a href="https://autre-site.com/x">Manette DualSense GTA VI</a>"""
        liens = liens_produits(html, "https://www.micromania.fr/search?q=gta")
        self.assertEqual(liens, ["https://www.micromania.fr/p/manette-gta-vi-blanche-123.html"])


AMAZON = """<html><body><span id="productTitle"> Manette sans fil DualSense - Edition Limitée Grand Theft Auto VI - Blanche </span>
<div id="corePrice_feature_div"><span class="a-price"><span class="a-offscreen">84,99 €</span></span></div>
<div id="availability"><span>En stock</span></div>
<input id="add-to-cart-button" type="submit">
<div id="merchantInfoFeature_feature_div"><span class="offer-display-feature-text-message">Amazon</span></div>
</body></html>"""
AMAZON_RUPTURE = """<html><body><span id="productTitle">Manette sans fil DualSense - Edition Limitée Grand Theft Auto VI - Blanche</span>
<div id="availability"><span>Actuellement indisponible.</span></div><div id="outOfStock"></div></body></html>"""


class TestAmazon(unittest.TestCase):
    def _nav(self, *pages):
        nav = mock.Mock()
        nav.get.side_effect = [mock.Mock(ok=True, texte=p, url="u", statut=200, bloque=False, raison="") for p in pages]
        return nav

    def test_en_stock_vendu_par_amazon(self):
        offres = amazon.verifier_asin(self._nav(AMAZON, "<html></html>"), "B0HHS4DKRM", "blanche", "fr", 7.0)
        self.assertEqual(len(offres), 1)
        o = offres[0]
        self.assertTrue(o.disponible)
        self.assertEqual((o.prix, o.livraison, o.confiance), (84.99, 0.0, M.ENSEIGNE))

    def test_rupture(self):
        offres = amazon.verifier_asin(self._nav(AMAZON_RUPTURE, "<html></html>"), "B0HHS4DKRM", "blanche", "fr", 7.0)
        self.assertEqual(len(offres), 1)
        self.assertFalse(offres[0].disponible)

    def test_europe_port_estime(self):
        offres = amazon.verifier_asin(self._nav(AMAZON, "<html></html>"), "B0HHS4DKRM", "blanche", "de", 7.0)
        self.assertEqual(offres[0].total, 91.99)


def carte_ebay(titre, prix, vendeur, port="Livraison gratuite", prov="Provenance : France", item="123456789012"):
    return f"""<li class="s-card"><a class="s-card__link" href="https://www.ebay.fr/itm/{item}?hash=x">
    <div class="s-card__title"><span>{titre}</span></div></a><span class="s-card__price">{prix}</span>
    <span>{port}</span><span>{prov}</span><span>{vendeur}</span></li>"""


class TestEbay(unittest.TestCase):
    def test_filtrage_vendeurs(self):
        html = "<ul>" + "".join([
            carte_ebay("Manette DualSense GTA VI édition limitée blanche neuve", "95,00 €", "top_jeux (2 345) 99,6 %", item="111111111111"),
            carte_ebay("Manette DualSense GTA VI édition limitée blanche neuve", "70,00 €", "nouveau (3) 100 %", item="222222222222"),
            carte_ebay("Manette DualSense GTA VI édition limitée noire", "89,00 €", "pro (5 000) 99,9 %", prov="Provenance : Chine", item="333333333333"),
            carte_ebay("Manette DualSense GTA VI édition limitée noire", "25,00 €", "pro (5 000) 99,9 %", item="444444444444"),
            carte_ebay("Skin manette GTA VI", "9,99 €", "pro (5 000) 99,9 %", item="555555555555"),
            carte_ebay("Manette PS5 GTA 6 blanche", "120,00 €", "boutique (812) 98,9 %", "+6,50 € de frais de livraison", "Provenance : Allemagne", item="666666666666"),
        ]) + "</ul>"
        offres, ecartees = ebay.analyser_resultats(html, cfg_test())
        urls = {o.url: o for o in offres}
        self.assertEqual(set(urls), {"https://www.ebay.fr/itm/111111111111", "https://www.ebay.fr/itm/666666666666"})
        self.assertEqual(urls["https://www.ebay.fr/itm/666666666666"].total, 126.5)
        self.assertEqual(ecartees, 3)  # vendeur trop récent, Chine, prix louche (la skin est ignorée d'office)


class TestEbayVendeur(unittest.TestCase):
    def test_formats_vendeur(self):
        self.assertEqual(ebay._lire_vendeur("top_jeux (2 345) 99,6 %"), (2345, 99.6))
        self.assertEqual(ebay._lire_vendeur("boutique 99,5 % d'évaluations positives (1,2 k)"), (1200, 99.5))
        self.assertEqual(ebay._lire_vendeur("rien"), (None, None))


class TestDealabs(unittest.TestCase):
    def test_deal_enseigne_seulement(self):
        import html as h
        import time
        threads = [
            {"threadId": 1, "title": "Manette DualSense Édition limitée GTA VI Blanche", "price": 84.99,
             "merchant": {"merchantName": "Fnac"}, "isExpired": False, "publishedAt": time.time() - 600,
             "shareableLink": "https://www.dealabs.com/bons-plans/manette-gta-1"},
            {"threadId": 2, "title": "Manette DualSense GTA VI Blanche", "price": 60,
             "merchant": {"merchantName": "Vinted"}, "isExpired": False, "publishedAt": time.time() - 600},
            {"threadId": 3, "title": "Manette DualSense GTA VI Noire", "price": 84.99,
             "merchant": {"merchantName": "Amazon"}, "isExpired": True, "publishedAt": time.time() - 600},
        ]
        page = "".join(f"<article data-vue3='{h.escape(json.dumps({'props': {'thread': t}}))}'></article>" for t in threads)
        offres = dealabs.analyser(page)
        self.assertEqual(len(offres), 1)
        self.assertEqual(offres[0].vendeur, "Fnac")


def page_ps(dispo: str, autres: str = "") -> str:
    ld = {"@context": "https://schema.org", "@type": "Product", "productID": "PSD001-PSDE02019_19-DUALSENSEGEYIO4E",
          "name": "Manette sans fil DualSense® - Édition limitée Grand Theft Auto VI Black - pour PS5, PC, Mac et mobile\t\t",
          "offers": {"@type": "Offer", "availability": f"https://schema.org/{dispo}", "url": "https://x"}}
    return (f'<html><script type="application/ld+json">{json.dumps(ld)}</script><body>'
            f'<p>Manette GTA VI Black</p>{autres}</body></html>')


class TestPlayStation(unittest.TestCase):
    URL = "https://www.playstation.com/fr-fr/accessories/x/grand-theft-auto-vi-black-limited-edition/"

    def test_rupture(self):
        # Page réelle : d'autres manettes en promo avec bouton d'achat → ne doit PAS compter.
        autres = 'Non disponible à l\'achat {"type":"ADD_TO_CART"} {"discountedPrice":"54,99 €"}'
        offres, _ = playstation.analyser(page_ps("OutOfStock", autres), self.URL, "PlayStation (officiel)", "noire")
        self.assertEqual(len(offres), 1)
        self.assertFalse(offres[0].disponible)
        self.assertEqual(offres[0].etat_stock, "Non disponible à l'achat")
        self.assertEqual(offres[0].prix, 84.99)

    def test_en_stock(self):
        offres, _ = playstation.analyser(page_ps("InStock"), self.URL, "PlayStation (officiel)", "noire")
        self.assertTrue(offres[0].disponible)
        self.assertEqual((offres[0].confiance, offres[0].total), (M.OFFICIEL, 84.99))


IDEALO = """<html><div class="leadoutbox"><a class="leadoutbox-priceAmount"
href="/relocator/relocate?offerKey=aaaa&price=189.99&sid=1&type=offer">189,99 €</a>
<div class="leadoutbox-shop">Marchand: <a href="/relocator/relocate?offerKey=aaaa&price=189.99">cstech.store/fr</a></div></div>
<ul>
<li class="productOffers-listItem" data-mtrx-click='{"shop_name":"cstech.store/fr","products":[{"id":1,"price":189.99}]}'>
 <span class="productOffers-listItemTitleInner" title="Manette Sony DualSense PS5 Édition Limitée GTA VI Blanc"></span></li>
<li class="productOffers-listItem" data-mtrx-click='{"shop_name":"Amazon.fr","products":[{"id":1,"price":84.99}]}'>
 <span class="productOffers-listItemTitleInner" title="Manette sans fil DualSense Édition limitée Grand Theft Auto VI Blanc"></span>
 Livraison gratuite</li>
<li class="productOffers-listItem" data-mtrx-click='{"shop_name":"Cdiscount.com (Marketplace)","products":[{"id":1,"price":289.0}]}'>
 <span class="productOffers-listItemTitleInner" title="Manette sans fil DualSense - Édition limitée Grand Theft Auto VI - Blanche"></span>
 + 4,99 € frais de livraison</li>
</ul></html>"""


class TestIdealo(unittest.TestCase):
    def test_marchands(self):
        offres, ecartees = idealo.analyser(IDEALO, "https://www.idealo.fr/prix/1/x.html", "blanche")
        par_vendeur = {o.vendeur: o for o in offres}
        self.assertEqual(set(par_vendeur), {"Amazon.fr", "Cdiscount.com (Marketplace)"})
        self.assertEqual((par_vendeur["Amazon.fr"].total, par_vendeur["Amazon.fr"].confiance), (84.99, M.ENSEIGNE))
        cd = par_vendeur["Cdiscount.com (Marketplace)"]
        self.assertEqual((cd.total, cd.confiance), (293.99, M.MARKETPLACE))
        self.assertEqual(ecartees, ["cstech.store/fr"])

    def test_prix_pas_pris_pour_le_port(self):
        html = """<li class="productOffers-listItem" data-mtrx-click='{"shop_name":"Fnac.com","products":[{"price":289.0}]}'>
        <span class="productOffers-listItemTitleInner" title="Manette DualSense Grand Theft Auto VI Blanche"></span>
        289,00 € Livraison : ven. 27/11</li>"""
        offres, _ = idealo.analyser(html, "https://www.idealo.fr/prix/1/x.html", "blanche")
        self.assertIsNone(offres[0].livraison)
        self.assertEqual(offres[0].total, 289.0)

    def test_fiche_auchan_meta_vendeur_tiers(self):
        html = """<html><head><meta property="og:title" content="SONY Manette sans fil DualSense Édition limitée Grand Theft Auto VI">
        <meta property="og:description" content="Manette blanche édition limitée"><meta property="product:price:amount" content="299.99">
        <meta property="product:availability" content="instock"></head><body><p>Vendu par MASS DISTRIB</p></body></html>"""
        offres, _ = analyser_fiche(html, "https://www.auchan.fr/x/pr-C1", site="Auchan")
        o = offres[0]
        self.assertEqual((o.vendeur, o.confiance, o.edition, o.livraison), ("MASS DISTRIB", M.MARKETPLACE, "blanche", None))

    def test_fiche_auchan_vendeur_tiers(self):
        html = """<html><script type="application/ld+json">{"@type":"Product",
        "name":"SONY Manette sans fil DualSense Édition limitée Grand Theft Auto VI",
        "description":"Manette blanche en édition limitée","offers":{"@type":"Offer","price":"299.99",
        "availability":"https://schema.org/InStock"}}</script><body><p>299,99€ / pce</p>
        <p>Vendu par MASS DISTRIB</p><p>Expédié sous 48h</p></body></html>"""
        offres, _ = analyser_fiche(html, "https://www.auchan.fr/x/pr-C1", site="Auchan")
        self.assertEqual(len(offres), 1)
        o = offres[0]
        self.assertEqual((o.vendeur, o.confiance, o.edition), ("MASS DISTRIB", M.MARKETPLACE, "blanche"))
        self.assertIsNone(o.livraison)


def offre(prix, site="Fnac", url="https://www.fnac.com/a1", dispo=True, confiance=M.ENSEIGNE, ed="blanche", port=0.0):
    return M.Offre(site=site, edition=ed, titre="Manette GTA VI", url=url, prix=prix, livraison=port,
                   disponible=dispo, etat_stock="En stock" if dispo else "Rupture", vendeur=site, confiance=confiance)


def bilan_avec(*offres, statut="ok"):
    s = M.ResultatSource(nom="Fnac (blanche)", statut=statut, offres=list(offres))
    return trier([s], cfg_test())


class TestCadences(unittest.TestCase):
    def test_passage_rapide_sony_seulement(self):
        c = charger()
        rapides = fiches_a_verifier(c, seulement_sony=True)
        self.assertTrue(rapides and all("playstation.com" in f["url"] for f in rapides))
        self.assertEqual({f["edition"] for f in rapides}, {"blanche", "noire"})
        tout = fiches_a_verifier(c)
        self.assertEqual(tout[:len(rapides)], rapides)          # Sony en premier
        self.assertGreater(len(tout), len(rapides))

    def test_workflow_cadences(self):
        wf = (Path(__file__).resolve().parents[2] / ".github/workflows/traqueur-manette-gta6.yml").read_text()
        self.assertIn('cron: "*/8 * * * *"', wf)
        self.assertIn("github.event.schedule == '*/8 * * * *' && 'sony'", wf)
        self.assertIn('cron: "4,34 * * * *"', wf)


class TestAlertes(unittest.TestCase):
    def setUp(self):
        self.push = mock.patch.object(tourner.N, "push", return_value=True).start()
        mock.patch.object(tourner.N, "creer_issue", return_value=7).start()
        mock.patch.object(tourner.N, "issue_ouverte", return_value=True).start()
        mock.patch.object(tourner.N, "commenter_issue", return_value=True).start()
        self.fermer = mock.patch.object(tourner.N, "fermer_issue").start()
        self.t0 = datetime(2026, 11, 19, 21, 7, tzinfo=PARIS)

    def tearDown(self):
        mock.patch.stopall()

    def test_tri_seuils(self):
        b = bilan_avec(offre(84.99), offre(104.0, url="https://www.fnac.com/a2"),
                       offre(95.0, site="eBay", url="https://www.ebay.fr/itm/1", confiance=M.EBAY_PRO, port=None),
                       offre(80.0, url="https://www.fnac.com/a3", dispo=False),
                       offre(50.0, site="Pirate", url="https://pirate.example/x"))
        self.assertEqual([o.prix for o in b.alertes], [84.99])     # 95 € + port inconnu (≈8 €) > 100 €
        self.assertEqual([o.prix for o in b.compromis], [104.0])

    def test_pas_de_double_alerte(self):
        etat = {}
        b = bilan_avec(offre(84.99))
        self.assertEqual(tourner.signaler(b, cfg_test(), etat, self.t0), 1)
        self.assertEqual(tourner.signaler(b, cfg_test(), etat, self.t0 + timedelta(hours=1)), 0)
        # Baisse de prix → nouvelle alerte
        self.assertEqual(tourner.signaler(bilan_avec(offre(79.99)), cfg_test(), etat, self.t0 + timedelta(hours=2)), 1)

    def test_passage_sony_ne_ferme_pas_les_autres(self):
        # Une offre idealo signalée ne doit pas être déclarée disparue par un passage Sony seul.
        etat = {}
        tourner.signaler(bilan_avec(offre(84.99)), cfg_test(), etat, self.t0)
        sony = trier([M.ResultatSource(nom="PlayStation (officiel) (blanche)", offres=[
            offre(84.99, site="PlayStation (officiel)", url="https://www.playstation.com/x", dispo=False,
                  confiance=M.OFFICIEL)])], cfg_test())
        tourner.signaler(sony, cfg_test(), etat, self.t0 + timedelta(minutes=8))
        self.fermer.assert_not_called()
        self.assertFalse(any(v.get("absent_depuis") for v in etat["signalees"].values()))

    def test_disparition_puis_retour(self):
        etat = {}
        tourner.signaler(bilan_avec(offre(84.99)), cfg_test(), etat, self.t0)
        # Site bloqué : on ne conclut pas que l'offre a disparu
        tourner.signaler(bilan_avec(statut="bloque"), cfg_test(), etat, self.t0 + timedelta(hours=1))
        self.fermer.assert_not_called()
        # Site OK et offre absente : issue fermée
        tourner.signaler(bilan_avec(), cfg_test(), etat, self.t0 + timedelta(hours=2))
        self.fermer.assert_called_once()
        # Elle revient : nouvelle alerte "retour en stock"
        self.push.reset_mock()
        self.assertEqual(tourner.signaler(bilan_avec(offre(84.99)), cfg_test(), etat, self.t0 + timedelta(hours=3)), 1)
        self.assertIn("RETOUR", self.push.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
