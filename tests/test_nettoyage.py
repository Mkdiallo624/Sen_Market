"""Tests du nettoyage, y compris les CAS D'ERREUR (fichier abîmé)."""
import pandas as pd
import pytest

from src.erreurs import DonneesInvalidesError
from src.nettoyage import (charger_csv, nettoyer_clients, nettoyer_commandes,
                           nettoyer_paiements)


def _commandes():
    return pd.DataFrame({
        "commande_id": [1, 1, 2, 3, 4],
        "montant_total": [1000, 1000, None, 500, 700],
        "date_commande": pd.to_datetime(["2026-01-10", "2026-01-10", "2026-01-11",
                                         "2030-01-01", "2026-02-01"]),
    })


# --- cas normaux ---------------------------------------------------------

def test_commandes_doublons_manquants_et_futur_sont_retires():
    propre = nettoyer_commandes(_commandes(), date_fin="2026-10-25")
    assert list(propre["commande_id"]) == [1, 4]


def test_clients_doublons_retires_et_telephone_remplace():
    df = pd.DataFrame({"client_id": [1, 1, 2], "telephone": ["+221 77", "+221 77", None]})
    propre = nettoyer_clients(df)
    assert len(propre) == 2
    assert propre.loc[propre["client_id"] == 2, "telephone"].iloc[0] == "inconnu"


def test_paiement_avant_la_commande_est_retire():
    commandes = nettoyer_commandes(_commandes(), "2026-10-25")  # commandes 1 et 4
    paiements = pd.DataFrame({
        "paiement_id": [1, 2, 3],
        "commande_id": [1, 4, 99],  # 99 : commande inexistante
        "date_paiement": pd.to_datetime(["2026-01-10 10:00", "2026-01-01 00:00", "2026-01-01 00:00"]),
    })
    propre = nettoyer_paiements(paiements, commandes)
    assert list(propre["paiement_id"]) == [1]


def test_nettoyage_est_idempotent():
    une_fois = nettoyer_commandes(_commandes(), "2026-10-25")
    deux_fois = nettoyer_commandes(une_fois, "2026-10-25")
    pd.testing.assert_frame_equal(une_fois, deux_fois)


# --- cas d'erreur : le script doit échouer PROPREMENT --------------------

def test_fichier_introuvable(tmp_path):
    with pytest.raises(DonneesInvalidesError, match="introuvable"):
        charger_csv(tmp_path / "absent.csv", ["a"])


def test_fichier_vide(tmp_path):
    chemin = tmp_path / "vide.csv"
    chemin.write_text("")
    with pytest.raises(DonneesInvalidesError, match="vide"):
        charger_csv(chemin, ["a"])


def test_colonne_manquante(tmp_path):
    chemin = tmp_path / "incomplet.csv"
    chemin.write_text("commande_id,client_id\n1,2\n")
    with pytest.raises(DonneesInvalidesError, match="montant_total"):
        charger_csv(chemin, ["commande_id", "montant_total"])


def test_contenu_binaire_illisible(tmp_path):
    chemin = tmp_path / "corrompu.csv"
    chemin.write_bytes(b"\x00\xff\xfe\x80garbage\x00\x01")
    with pytest.raises(DonneesInvalidesError):
        charger_csv(chemin, ["commande_id"])