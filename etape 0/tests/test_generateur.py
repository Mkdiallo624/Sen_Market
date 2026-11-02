"""Tests du générateur et de l'injection de défauts."""
import pandas as pd
import pytest

from src.config import Config
from src.defauts import NOMS_SPECIAUX, TAUX, VALEUR_OUTLIER, injecter_defauts
from src.erreurs import ConfigurationError
from src.generateur import generer_tout
from src.schemas import COLONNES


@pytest.fixture
def cfg(tmp_path):
    return Config(nb_clients=100, nb_vendeurs=5, nb_produits=20, nb_commandes=300,
                  nb_avis=50, nb_evenements=200, dossier_sortie=tmp_path)


def _nb(n, nom):
    """Nombre de lignes touchées pour un défaut : même formule que defauts.py."""
    return int(n * TAUX[nom])


def test_toutes_les_tables_ont_les_bonnes_colonnes(cfg):
    tables = generer_tout(cfg)
    assert tables.keys() == COLONNES.keys()
    for nom, colonnes in COLONNES.items():
        assert list(tables[nom].columns) == colonnes


def test_les_volumes_respectent_la_configuration(cfg):
    tables = generer_tout(cfg)
    assert len(tables["clients"]) == 100
    assert len(tables["commandes"]) == 300
    # une commande annulée n'a pas de paiement
    non_annulees = (tables["commandes"]["statut"] != "annulee").sum()
    assert len(tables["paiements"]) == non_annulees


def test_les_identifiants_sont_uniques(cfg):
    tables = generer_tout(cfg)
    assert tables["clients"]["client_id"].is_unique
    assert tables["commandes"]["commande_id"].is_unique
    assert tables["lignes_commande"]["ligne_id"].is_unique


def test_les_montants_sont_positifs_et_coherents(cfg):
    tables = generer_tout(cfg)
    commandes, lignes = tables["commandes"], tables["lignes_commande"]
    assert (commandes["montant_total"] > 0).all()
    assert (lignes["montant_ligne"] == lignes["prix_unitaire"] * lignes["quantite"]).all()
    somme = lignes.groupby("commande_id")["montant_ligne"].sum()
    assert (commandes["montant_total"].to_numpy()
            == somme.reindex(commandes["commande_id"]).to_numpy()).all()


def test_meme_graine_memes_donnees(cfg):
    a, b = generer_tout(cfg), generer_tout(cfg)
    for nom in a:
        pd.testing.assert_frame_equal(a[nom], b[nom])


def test_les_defauts_sont_bien_injectes(cfg):
    propres = generer_tout(cfg)
    abimees = injecter_defauts(propres, cfg)
    clients, commandes, paiements, lignes = (
        abimees[t] for t in ("clients", "commandes", "paiements", "lignes_commande"))
    n_cli, n_cmd = len(propres["clients"]), len(propres["commandes"])
    n_pay, n_lig = len(propres["paiements"]), len(propres["lignes_commande"])
    limite = pd.Timestamp(cfg.date_fin) + pd.Timedelta(days=1)

    # doublons : +5 % de lignes dans les 4 tables abîmées
    assert len(clients) == n_cli + _nb(n_cli, "doublons")
    assert len(commandes) == n_cmd + _nb(n_cmd, "doublons")
    assert len(paiements) == n_pay + _nb(n_pay, "doublons")
    assert len(lignes) == n_lig + _nb(n_lig, "doublons")
    assert len(abimees["vendeurs"]) == len(propres["vendeurs"])         # intacte

    # valeurs manquantes : 8 % sur nom, email, region (lignes d'origine seulement)
    for col in ("nom", "email", "region"):
        assert clients[col].iloc[:n_cli].isna().sum() == _nb(n_cli, "manquantes")

    # noms avec caractères spéciaux : 2 % (ex. « Éloïse Müller-Ødegård »)
    assert clients["nom"].iloc[:n_cli].isin(NOMS_SPECIAUX).sum() == _nb(n_cli, "noms_speciaux")

    # montants : 3 % en texte avec " FCFA" et 1 % d'outliers
    for table, col in ((commandes, "montant_total"), (paiements, "montant"),
                       (lignes, "montant_ligne")):
        n = {"montant_total": n_cmd, "montant": n_pay, "montant_ligne": n_lig}[col]
        montants = table[col].iloc[:n]
        est_texte = montants.map(lambda v: isinstance(v, str))
        assert montants.map(lambda v: isinstance(v, str) and v.endswith(" FCFA")).sum() == \
            _nb(n, "montants_texte")
        assert (~est_texte & (montants == VALEUR_OUTLIER)).sum() == _nb(n, "outliers")

    # dates dans le futur : 2 % après DATE_FIN
    assert (commandes["date_commande"].iloc[:n_cmd] >= limite).sum() == _nb(n_cmd, "dates_futur")
    assert (paiements["date_paiement"].iloc[:n_pay] >= limite).sum() == _nb(n_pay, "dates_futur")

    # lignes de commande : quantités impossibles et prix manquants
    assert (lignes["quantite"].iloc[:n_lig] <= 0).sum() == _nb(n_lig, "quantites_invalides")
    assert lignes["prix_unitaire"].iloc[:n_lig].isna().sum() == _nb(n_lig, "manquantes")


def test_taux_defauts_zero_n_abime_rien(tmp_path):
    cfg = Config(nb_clients=100, nb_vendeurs=5, nb_produits=20, nb_commandes=300,
                 nb_avis=50, nb_evenements=200, taux_defauts=0.0, dossier_sortie=tmp_path)
    propres = generer_tout(cfg)
    abimees = injecter_defauts(propres, cfg)
    for nom in propres:
        assert len(abimees[nom]) == len(propres[nom])
    assert not abimees["clients"][["nom", "email", "region"]].isna().any().any()


def test_taux_defauts_est_applique(tmp_path):
    """TAUX_DEFAUTS=0.10 doit doubler les doublons par rapport à la référence (0.05)."""
    cfg = Config(nb_clients=100, nb_vendeurs=5, nb_produits=20, nb_commandes=300,
                 nb_avis=50, nb_evenements=200, taux_defauts=0.10, dossier_sortie=tmp_path)
    abimees = injecter_defauts(generer_tout(cfg), cfg)
    assert len(abimees["clients"]) == 110


def test_configuration_invalide_est_refusee():
    with pytest.raises(ConfigurationError):
        Config(nb_clients=0)
    with pytest.raises(ConfigurationError):
        Config(taux_defauts=0.9)
    with pytest.raises(ConfigurationError):
        Config(date_fin="25/10/2026")