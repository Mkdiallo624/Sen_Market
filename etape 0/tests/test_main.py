"""Test de bout en bout : génération -> nettoyage -> fichiers produits."""
import pandas as pd
import pytest

from src.config import Config
from src.main import main
from src.schemas import COLONNES


@pytest.fixture
def cfg(tmp_path):
    return Config(nb_clients=100, nb_vendeurs=5, nb_produits=20, nb_commandes=300,
                  nb_avis=50, nb_evenements=200, dossier_sortie=tmp_path)


@pytest.fixture
def propres(cfg):
    """Lance le pipeline et relit les tables propres (CSV)."""
    assert main([], cfg=cfg) == 0
    lire = lambda nom: pd.read_csv(cfg.dossier_sortie / "propre" / f"{nom}.csv",
                                   encoding="utf-8-sig")
    return {nom: lire(nom) for nom in ("clients", "commandes", "lignes_commande", "paiements")}


def test_pipeline_complet_produit_les_trois_formats(cfg):
    assert main([], cfg=cfg) == 0
    for nom in COLONNES:
        for ext in ("csv", "json", "parquet"):
            assert (cfg.dossier_sortie / "propre" / f"{nom}.{ext}").exists()


def test_relancer_ne_change_pas_le_resultat(cfg):
    main([], cfg=cfg)
    premier = pd.read_parquet(cfg.dossier_sortie / "propre" / "commandes.parquet")
    main([], cfg=cfg)
    second = pd.read_parquet(cfg.dossier_sortie / "propre" / "commandes.parquet")
    pd.testing.assert_frame_equal(premier, second)  # aucun doublon ajouté


def test_lignes_nettoyees(propres):
    lignes, commandes = propres["lignes_commande"], propres["commandes"]
    assert lignes["ligne_id"].is_unique
    assert (lignes["quantite"] > 0).all()
    assert lignes["prix_unitaire"].notna().all()
    assert (lignes["montant_ligne"] == lignes["prix_unitaire"] * lignes["quantite"]).all()
    assert lignes["commande_id"].isin(commandes["commande_id"]).all()


def test_totaux_et_paiements_coherents(propres):
    lignes, commandes, paiements = (propres[t] for t in ("lignes_commande", "commandes", "paiements"))
    somme = lignes.groupby("commande_id")["montant_ligne"].sum()
    assert (commandes.set_index("commande_id")["montant_total"]
            == somme.reindex(commandes["commande_id"]).to_numpy()).all()
    m = paiements.merge(commandes[["commande_id", "montant_total"]], on="commande_id")
    assert len(m) == len(paiements)                          # aucun paiement orphelin
    assert (m["montant"] == m["montant_total"]).all()


def test_fichier_corrompu_arrete_le_script_proprement(cfg, caplog):
    main([], cfg=cfg)
    (cfg.dossier_sortie / "brut" / "commandes.csv").write_text("colonne_bizarre\n42\n")
    code = main(["--nettoyage"], cfg=cfg)
    assert code == 1                       # échec propre, pas de plantage
    assert "montant_total" in caplog.text  # le message dit QUOI est cassé
