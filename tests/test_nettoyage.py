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


def test_montants_en_texte_sont_convertis():
    df = pd.DataFrame({
        "commande_id": [1, 2, 3],
        "montant_total": ["1000", "2500.00 €", "1 750,00 €"],
        "date_commande": pd.to_datetime(["2026-01-10"] * 3),
    })
    propre = nettoyer_commandes(df, "2026-10-25")
    assert list(propre["montant_total"]) == [1000, 2500, 1750]
    assert propre["montant_total"].dtype == "int64"


def test_outlier_incoherent_avec_prix_fois_quantite_est_retire():
    # 1 200 000 est un montant LÉGITIME ici (Électronique x 5) ; 999999.99 ne l'est pas
    produits = pd.DataFrame({"produit_id": [1, 2], "prix": [250000, 5000]})
    df = pd.DataFrame({
        "commande_id": [1, 2, 3, 4],
        "produit_id": [1, 1, 2, 2],
        "quantite": [5, 2, 3, 1],
        "montant_total": [1250000, 999999.99, "15000.00 €", 5000],
        "date_commande": pd.to_datetime(["2026-01-10"] * 4),
    })
    propre = nettoyer_commandes(df, "2026-10-25", produits=produits)
    assert list(propre["commande_id"]) == [1, 3, 4]
    assert list(propre["montant_total"]) == [1250000, 15000, 5000]


def test_outlier_regle_de_secours_sans_table_produits():
    montants = list(range(1000, 1100)) + [999999.99]
    df = pd.DataFrame({
        "commande_id": range(len(montants)),
        "montant_total": montants,
        "date_commande": pd.to_datetime(["2026-01-10"] * len(montants)),
    })
    propre = nettoyer_commandes(df, "2026-10-25")
    assert len(propre) == 100 and propre["montant_total"].max() < 2000


def test_clients_manquants_remplaces_et_noms_speciaux_conserves():
    df = pd.DataFrame({
        "client_id": [1, 2, 3, 4],
        "nom": ["Éloïse Müller-Ødegård", None, "  Awa   Diop ", "Ã‰loÃ¯se"],
        "email": ["A@X.fr", None, "b@x.fr", "c@x.fr"],
        "region": ["Dakar", None, "Thiès", "Kaolack"],
    })
    propre = nettoyer_clients(df).set_index("client_id")
    assert propre.loc[1, "nom"] == "Éloïse Müller-Ødegård"   # conservé tel quel
    assert propre.loc[2, "nom"] == "inconnu"
    assert propre.loc[2, "region"] == "inconnu"
    assert pd.isna(propre.loc[2, "email"])                    # on n'invente pas d'email
    assert propre.loc[3, "nom"] == "Awa Diop"                 # espaces nettoyés
    assert propre.loc[1, "email"] == "a@x.fr"                 # email en minuscules
    assert propre.loc[4, "nom"] == "Éloïse"                   # texte mal décodé réparé


def test_paiement_futur_montant_texte_et_outlier():
    n = 30
    commandes = nettoyer_commandes(pd.DataFrame({
        "commande_id": range(1, n + 1),
        "montant_total": [1000 + 10 * i for i in range(n)],
        "date_commande": pd.to_datetime(["2026-01-10"] * n),
    }), "2026-10-25")
    montants = [1000 + 10 * i for i in range(n)]
    montants[1] = "1010.00 €"        # texte : converti
    montants[2] = 999999.99          # outlier : retiré
    dates = ["2026-01-10 10:00"] * n
    dates[3] = "2027-05-01 00:00"    # futur : retiré
    paiements = pd.DataFrame({
        "paiement_id": range(1, n + 1),
        "commande_id": range(1, n + 1),
        "montant": montants,
        "date_paiement": pd.to_datetime(dates),
    })
    propre = nettoyer_paiements(paiements, commandes, "2026-10-25")
    assert sorted(set(range(1, n + 1)) - set(propre["paiement_id"])) == [3, 4]
    assert propre.loc[propre["paiement_id"] == 2, "montant"].iloc[0] == 1010
    assert propre["montant"].dtype == "int64"


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