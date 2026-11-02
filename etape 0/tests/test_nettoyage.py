"""Tests du nettoyage, y compris les CAS D'ERREUR (fichier abîmé)."""
import pandas as pd
import pytest

from src.erreurs import DonneesInvalidesError
from src.nettoyage import (_convertir_montants, charger_csv, nettoyer_clients,
                           nettoyer_commandes, nettoyer_lignes_commande,
                           nettoyer_paiements, recalculer_totaux)

DATE_FIN = "2026-10-25"


def _commandes():
    return pd.DataFrame({
        "commande_id": [1, 1, 2, 3, 4],
        "montant_total": [1000, 1000, None, 500, 700],   # ignoré : sera recalculé
        "date_commande": pd.to_datetime(["2026-01-10", "2026-01-10", "2026-01-11",
                                         "2030-01-01", "2026-02-01"]),
    })


def _produits():
    return pd.DataFrame({"produit_id": [1, 2], "prix": [500, 700]})


def _lignes_simples():
    """Une ligne saine pour la commande 1 et une pour la commande 4 (la 2 n'en a aucune)."""
    return pd.DataFrame({
        "ligne_id": [1, 2], "commande_id": [1, 4], "produit_id": [1, 2],
        "quantite": [2, 1], "prix_unitaire": [500, 700], "montant_ligne": [1000, 700],
    })


def _commandes_propres():
    """Commandes 1 (1000 FCFA, 10/01) et 4 (700 FCFA, 01/02), totaux recalculés."""
    commandes = nettoyer_commandes(_commandes(), DATE_FIN)
    return recalculer_totaux(commandes, _lignes_simples())


# --- commandes -----------------------------------------------------------

def test_commandes_doublons_et_futur_sont_retires():
    propre = nettoyer_commandes(_commandes(), date_fin=DATE_FIN)
    assert list(propre["commande_id"]) == [1, 2, 4]          # 1 doublon, 3 dans le futur
    assert "montant_total" not in propre.columns             # reconstruit plus tard


def test_commande_sans_ligne_est_retiree_au_recalcul():
    propre = _commandes_propres()
    assert list(propre["commande_id"]) == [1, 4]             # la 2 n'a aucune ligne
    assert list(propre["montant_total"]) == [1000, 700]
    assert propre["montant_total"].dtype == "int64"


def test_nettoyage_commandes_est_idempotent():
    une_fois = nettoyer_commandes(_commandes(), DATE_FIN)
    deux_fois = nettoyer_commandes(une_fois, DATE_FIN)
    pd.testing.assert_frame_equal(une_fois, deux_fois)


# --- montants ------------------------------------------------------------

def test_montants_en_texte_sont_convertis():
    df = pd.DataFrame({"m": ["1000", "2500.00 FCFA", "1 750,00 €", "3 000 xof", "abc"]})
    propre = _convertir_montants(df, "m", "test")
    assert list(propre["m"].iloc[:4]) == [1000, 2500, 1750, 3000]
    assert pd.isna(propre["m"].iloc[4])                      # illisible -> manquant


# --- lignes de commande --------------------------------------------------

def test_lignes_outlier_texte_et_prix_manquant_sont_corriges():
    # 1 250 000 est un montant LÉGITIME (Électronique x 5) ; 999999.99 ne l'est pas
    produits = pd.DataFrame({"produit_id": [1, 2], "prix": [250000, 5000]})
    lignes = pd.DataFrame({
        "ligne_id": [1, 2, 3, 4, 4, 5],                      # ligne 4 en double
        "commande_id": [1, 2, 3, 4, 4, 99],                  # 99 : commande retirée
        "produit_id": [1, 1, 2, 2, 2, 2],
        "quantite": [5, 2, 3, 1, 1, 1],
        "prix_unitaire": [250000, 250000, 5000, None, None, 5000],
        "montant_ligne": [1250000, 999999.99, "15000.00 FCFA", 5000, 5000, 5000],
    })
    commandes = pd.DataFrame({"commande_id": [1, 2, 3, 4]})
    propre = nettoyer_lignes_commande(lignes, produits, commandes)
    assert list(propre["ligne_id"]) == [1, 2, 3, 4]
    assert list(propre["prix_unitaire"]) == [250000, 250000, 5000, 5000]   # 4 : relu dans produits
    assert list(propre["montant_ligne"]) == [1250000, 500000, 15000, 5000]
    for col in ("quantite", "prix_unitaire", "montant_ligne"):
        assert propre[col].dtype == "int64"


def test_quantite_invalide_retrouvee_ou_commande_retiree():
    produits = pd.DataFrame({"produit_id": [1], "prix": [1000]})
    lignes = pd.DataFrame({
        "ligne_id": [1, 2, 3, 4],
        "commande_id": [1, 2, 3, 3],
        "produit_id": [1, 1, 1, 1],
        "quantite": [3, 0, -1, 1],                 # 2 : retrouvable ; 3 : montant aussi abîmé
        "prix_unitaire": [1000, 1000, 1000, 1000],
        "montant_ligne": [3000, 2000, 999999.99, 1000],
    })
    commandes = pd.DataFrame({"commande_id": [1, 2, 3]})
    propre = nettoyer_lignes_commande(lignes, produits, commandes)
    assert list(propre["ligne_id"]) == [1, 2]                # commande 3 entière retirée
    assert list(propre["quantite"]) == [3, 2]                # le 0 est devenu 2 (2000 / 1000)
    totaux = recalculer_totaux(commandes, propre)
    assert list(totaux["commande_id"]) == [1, 2]
    assert list(totaux["montant_total"]) == [3000, 2000]


def test_nettoyage_lignes_est_idempotent():
    produits = pd.DataFrame({"produit_id": [1], "prix": [1000]})
    lignes = pd.DataFrame({"ligne_id": [1, 2], "commande_id": [1, 2], "produit_id": [1, 1],
                           "quantite": [3, 0], "prix_unitaire": [1000, None],
                           "montant_ligne": ["3000.00 FCFA", 2000]})
    commandes = pd.DataFrame({"commande_id": [1, 2]})
    une_fois = nettoyer_lignes_commande(lignes, produits, commandes)
    deux_fois = nettoyer_lignes_commande(une_fois, produits, commandes)
    pd.testing.assert_frame_equal(une_fois, deux_fois)


# --- clients -------------------------------------------------------------

def test_clients_doublons_retires_et_telephone_remplace():
    df = pd.DataFrame({"client_id": [1, 1, 2], "telephone": ["+221 77", "+221 77", None]})
    propre = nettoyer_clients(df)
    assert len(propre) == 2
    assert propre.loc[propre["client_id"] == 2, "telephone"].iloc[0] == "inconnu"


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


# --- paiements -----------------------------------------------------------

def test_paiement_avant_la_commande_est_corrige_et_orphelin_retire():
    commandes = _commandes_propres()                          # commandes 1 et 4
    paiements = pd.DataFrame({
        "paiement_id": [1, 2, 3],
        "commande_id": [1, 4, 99],                            # 99 : commande inexistante
        "montant": [1000, 700, 5],
        "date_paiement": pd.to_datetime(["2026-01-10 10:00", "2026-01-01 00:00", "2026-01-01 00:00"]),
    })
    propre = nettoyer_paiements(paiements, commandes, DATE_FIN)
    assert list(propre["paiement_id"]) == [1, 2]              # l'orphelin est retiré
    # le paiement 2 précédait sa commande : date recréée = commande + délai médian (10 h)
    assert propre.loc[propre["paiement_id"] == 2, "date_paiement"].iloc[0] == \
        pd.Timestamp("2026-02-01 10:00")


def test_paiement_futur_montant_texte_et_outlier_sont_corriges():
    n = 30
    totaux = [1000 + 10 * i for i in range(n)]
    commandes = pd.DataFrame({
        "commande_id": range(1, n + 1),
        "date_commande": pd.to_datetime(["2026-01-10"] * n),
        "montant_total": totaux,
    })
    montants = list(totaux)
    montants[1] = "1010.00 FCFA"     # texte : converti
    montants[2] = 999999.99          # outlier : aligné sur la commande
    dates = ["2026-01-10 10:00"] * n
    dates[3] = "2027-05-01 00:00"    # futur : date recréée
    paiements = pd.DataFrame({
        "paiement_id": range(1, n + 1), "commande_id": range(1, n + 1),
        "montant": montants, "date_paiement": pd.to_datetime(dates),
    })
    propre = nettoyer_paiements(paiements, commandes, DATE_FIN)
    assert len(propre) == n                                   # aucun paiement perdu
    assert list(propre["montant"]) == totaux
    assert propre["montant"].dtype == "int64"
    assert propre.loc[propre["paiement_id"] == 4, "date_paiement"].iloc[0] == \
        pd.Timestamp("2026-01-10 10:00")
    assert (propre["date_paiement"] < pd.Timestamp("2026-10-26")).all()


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


def test_date_illisible_devient_manquante(tmp_path):
    chemin = tmp_path / "dates.csv"
    chemin.write_text("d\n2026-01-01\npas une date\n")
    df = charger_csv(chemin, ["d"], ["d"])
    assert pd.isna(df["d"].iloc[1]) and not pd.isna(df["d"].iloc[0])