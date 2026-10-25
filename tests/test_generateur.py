"""Tests du générateur et de l'injection de défauts."""
import numpy as np
import pandas as pd
import pytest

from src.config import Config
from src.defauts import injecter_defauts
from src.erreurs import ConfigurationError
from src.generateur import generer_tout
from src.schemas import COLONNES


@pytest.fixture
def cfg(tmp_path):
    return Config(nb_clients=100, nb_vendeurs=5, nb_produits=20, nb_commandes=300,
                  nb_avis=50, nb_evenements=200, dossier_sortie=tmp_path)


def test_toutes_les_tables_ont_les_bonnes_colonnes(cfg):
    tables = generer_tout(cfg)
    for nom, colonnes in COLONNES.items():
        assert list(tables[nom].columns) == colonnes


def test_les_volumes_respectent_la_configuration(cfg):
    tables = generer_tout(cfg)
    assert len(tables["clients"]) == 100
    assert len(tables["commandes"]) == 300
    assert len(tables["paiements"]) == 300  # un paiement par commande


def test_les_identifiants_sont_uniques(cfg):
    tables = generer_tout(cfg)
    assert tables["clients"]["client_id"].is_unique
    assert tables["commandes"]["commande_id"].is_unique


def test_les_montants_sont_positifs_et_coherents(cfg):
    commandes = generer_tout(cfg)["commandes"]
    assert (commandes["montant_total"] > 0).all()


def test_meme_graine_memes_donnees(cfg):
    a, b = generer_tout(cfg), generer_tout(cfg)
    for nom in a:
        pd.testing.assert_frame_equal(a[nom], b[nom])


def test_les_defauts_sont_bien_injectes(cfg):
    propres = generer_tout(cfg)
    abimees = injecter_defauts(propres, cfg)
    assert len(abimees["commandes"]) > len(propres["commandes"])        # doublons
    assert abimees["commandes"]["montant_total"].isna().any()           # manquants
    assert abimees["clients"]["telephone"].isna().any()
    assert len(abimees["vendeurs"]) == len(propres["vendeurs"])         # intacte


def test_configuration_invalide_est_refusee():
    with pytest.raises(ConfigurationError):
        Config(nb_clients=0)
    with pytest.raises(ConfigurationError):
        Config(taux_defauts=0.9)
    with pytest.raises(ConfigurationError):
        Config(date_fin="25/10/2026")
