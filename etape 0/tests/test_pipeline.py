"""Test de bout en bout : génération -> défauts -> nettoyage -> invariants.

On compare aussi au jeu de données PROPRE d'origine (la « vérité ») : c'est la preuve
que le nettoyage retrouve les vraies valeurs et ne se contente pas de supprimer.
"""
import pandas as pd
import pytest

from src.config import Config
from src.defauts import NOMS_SPECIAUX, VALEUR_OUTLIER
from src.generateur import generer_tout
from src.main import generer_brut, main, nettoyer_vers_propre

CFG_ARGS = dict(nb_clients=400, nb_vendeurs=20, nb_produits=80, nb_commandes=3000,
                nb_avis=100, nb_evenements=200)


@pytest.fixture(scope="module")
def resultat(tmp_path_factory):
    cfg = Config(dossier_sortie=tmp_path_factory.mktemp("data"), **CFG_ARGS)
    generer_brut(cfg)
    nettoyer_vers_propre(cfg)
    propre = cfg.dossier_sortie / "propre"
    lire = lambda n, d=(): pd.read_csv(propre / f"{n}.csv", encoding="utf-8-sig", parse_dates=list(d))
    brut = pd.read_csv(cfg.dossier_sortie / "brut" / "commandes.csv")
    return dict(cfg=cfg, verite=generer_tout(cfg), brut_commandes=brut,
                clients=lire("clients"), commandes=lire("commandes", ["date_commande"]),
                lignes=lire("lignes_commande"), paiements=lire("paiements", ["date_paiement"]),
                produits=lire("produits"))


def test_aucun_doublon_d_id(resultat):
    for table, cle in [("clients", "client_id"), ("commandes", "commande_id"),
                       ("lignes", "ligne_id"), ("paiements", "paiement_id")]:
        assert resultat[table][cle].is_unique, table


def test_dates_pas_dans_le_futur(resultat):
    limite = pd.Timestamp(resultat["cfg"].date_fin) + pd.Timedelta(days=1)
    assert (resultat["commandes"]["date_commande"] < limite).all()
    assert (resultat["paiements"]["date_paiement"] < limite).all()


def test_montants_numeriques_et_sans_outlier(resultat):
    for table, col in [("commandes", "montant_total"), ("lignes", "montant_ligne"),
                       ("paiements", "montant"), ("lignes", "prix_unitaire")]:
        s = resultat[table][col]
        assert pd.api.types.is_integer_dtype(s), (table, col)
        assert (s != VALEUR_OUTLIER).all() and (s > 0).all()


def test_coherence_montants(resultat):
    l, c, p = resultat["lignes"], resultat["commandes"], resultat["paiements"]
    assert (l["quantite"] > 0).all()
    assert (l["montant_ligne"] == l["prix_unitaire"] * l["quantite"]).all()
    prix = resultat["produits"].set_index("produit_id")["prix"]
    assert (l["prix_unitaire"] == l["produit_id"].map(prix)).all()
    somme = l.groupby("commande_id")["montant_ligne"].sum()
    assert (c.set_index("commande_id")["montant_total"] == somme.reindex(c["commande_id"]).to_numpy()).all()
    m = p.merge(c[["commande_id", "montant_total", "date_commande"]], on="commande_id")
    assert len(m) == len(p)
    assert (m["montant"] == m["montant_total"]).all()
    assert (m["date_paiement"] >= m["date_commande"]).all()


def test_pas_d_orphelins(resultat):
    c = set(resultat["commandes"]["commande_id"])
    assert set(resultat["lignes"]["commande_id"]) <= c
    assert set(resultat["paiements"]["commande_id"]) <= c
    assert set(resultat["commandes"]["client_id"]) <= set(resultat["clients"]["client_id"])
    assert c <= set(resultat["lignes"]["commande_id"])      # toute commande a >= 1 ligne


def test_valeurs_retrouvees_identiques_a_la_verite(resultat):
    v = resultat["verite"]
    for table, cle, cols in [("commandes", "commande_id", ["montant_total"]),
                             ("lignes_commande", "ligne_id", ["quantite", "prix_unitaire", "montant_ligne"]),
                             ("paiements", "paiement_id", ["montant"])]:
        propre = resultat["lignes" if table == "lignes_commande" else table]
        vrai = v[table].set_index(cle).loc[propre[cle]]
        for col in cols:
            assert (vrai[col].to_numpy() == propre[col].to_numpy()).all(), (table, col)


def test_peu_de_pertes(resultat):
    v = resultat["verite"]
    assert len(resultat["commandes"]) >= 0.95 * len(v["commandes"])
    assert len(resultat["lignes"]) >= 0.93 * len(v["lignes_commande"])
    assert len(resultat["clients"]) == len(v["clients"])      # aucun client perdu


def test_clients_noms_speciaux_conserves_et_sans_manquants(resultat):
    c = resultat["clients"]
    assert c["nom"].isin(NOMS_SPECIAUX).sum() > 0
    assert c["nom"].notna().all() and c["region"].notna().all()


def test_le_brut_contenait_bien_des_defauts(resultat):
    """Garde-fou : si le brut est propre, les tests ci-dessus ne prouveraient rien."""
    b = resultat["brut_commandes"]
    assert b["commande_id"].duplicated().any()
    assert b["montant_total"].astype(str).str.contains("FCFA").any()


def test_main_fichiers_absents(tmp_path):
    cfg = Config(dossier_sortie=tmp_path / "vide", **CFG_ARGS)
    assert main(["--nettoyage"], cfg=cfg) == 1