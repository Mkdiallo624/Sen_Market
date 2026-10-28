"""Injection de défauts : on abîme volontairement les données.

Pourquoi ? Parce que les vraies données sont toujours sales. Un data engineer
qui n'a jamais vu de doublons ou de dates absurdes n'est pas prêt pour la
réalité. Ici on contrôle les défauts, donc on peut vérifier qu'ils sont bien
corrigés ensuite.
"""
import logging

import numpy as np
import pandas as pd

from src.config import Config

logger = logging.getLogger(__name__)

# Taux de défauts (proportion des lignes de chaque table concernée)
TAUX = {
    "doublons": 0.05,        # lignes recopiées
    "manquantes": 0.08,      # par colonne : nom, email, region
    "dates_futur": 0.02,     # dates postérieures à DATE_FIN
    "montants_texte": 0.03,  # montant stocké en texte, ex. "42.50 €"
    "outliers": 0.01,        # montant = VALEUR_OUTLIER
    "noms_speciaux": 0.02,   # noms avec accents / caractères spéciaux
}

VALEUR_OUTLIER = 999999.99

NOMS_SPECIAUX = [
    "Éloïse Müller-Ødegård", "Zoë Çelik", "Bjørn Åkesson", "Renée Dvořák",
    "Łukasz Wiśniewski", "Núria Peña-Ibáñez", "Søren Kierkegård",
    "Chloé Lefèvre-Bœuf", "Şebnem Yıldız", "Anaïs Fröhlich",
]


def _lignes_au_hasard(rng, df: pd.DataFrame, taux: float) -> np.ndarray:
    nb = int(len(df) * taux)
    return rng.choice(len(df), size=nb, replace=False)


def _tirage_disjoint(rng, df: pd.DataFrame, *taux: float) -> list[np.ndarray]:
    """Tire des groupes de lignes sans aucun chevauchement entre eux."""
    tailles = [int(len(df) * t) for t in taux]
    lignes = rng.choice(len(df), size=sum(tailles), replace=False)
    bornes = np.cumsum([0] + tailles)
    return [lignes[bornes[i]:bornes[i + 1]] for i in range(len(tailles))]


def _colonne(df: pd.DataFrame, table: str, *candidats: str) -> str:
    """Retourne la première colonne existante parmi `candidats`."""
    for c in candidats:
        if c in df.columns:
            return c
    raise KeyError(f"Table '{table}' : aucune colonne parmi {candidats} "
                   f"(colonnes présentes : {list(df.columns)})")


def ajouter_doublons(df: pd.DataFrame, taux: float, rng) -> pd.DataFrame:
    """Recopie `taux` % des lignes (un même clic de souris envoyé deux fois)."""
    copies = df.iloc[_lignes_au_hasard(rng, df, taux)]
    return pd.concat([df, copies], ignore_index=True)


def vider_colonne(df: pd.DataFrame, colonne: str, taux: float, rng) -> pd.DataFrame:
    """Efface la valeur de `colonne` sur `taux` % des lignes (valeurs manquantes)."""
    df = df.copy()
    df.iloc[_lignes_au_hasard(rng, df, taux), df.columns.get_loc(colonne)] = None
    return df


def decaler_dates(df: pd.DataFrame, colonne: str, taux: float, rng, jours: int) -> pd.DataFrame:
    """Décale la date de `jours` jours sur `taux` % des lignes (date incohérente)."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    lignes = _lignes_au_hasard(rng, df, taux)
    df.iloc[lignes, pos] = df.iloc[lignes, pos] + pd.Timedelta(days=jours)
    return df


def dates_dans_le_futur(df: pd.DataFrame, colonne: str, taux: float, rng, apres: str) -> pd.DataFrame:
    """Met `taux` % des dates entre 1 jour et 2 ans APRÈS `apres` (= DATE_FIN) : incohérence."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    lignes = _lignes_au_hasard(rng, df, taux)
    reference = pd.Timestamp(apres).normalize()
    jours = rng.integers(1, 731, size=len(lignes))
    df.iloc[lignes, pos] = [reference + pd.Timedelta(days=int(j)) for j in jours]
    return df


def abimer_montants(df: pd.DataFrame, colonne: str, taux_texte: float,
                    taux_outliers: float, rng) -> pd.DataFrame:
    """Montants en texte avec " €" et outliers, sur des lignes forcément différentes."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    lignes_texte, lignes_outliers = _tirage_disjoint(rng, df, taux_texte, taux_outliers)
    df[colonne] = df[colonne].astype(object)  # la colonne devient mixte (nombres + texte)
    df.iloc[lignes_texte, pos] = [f"{float(v):.2f} €" for v in df.iloc[lignes_texte, pos]]
    df.iloc[lignes_outliers, pos] = VALEUR_OUTLIER
    return df


def noms_avec_caracteres_speciaux(df: pd.DataFrame, colonne: str, taux: float, rng) -> pd.DataFrame:
    """Remplace `taux` % des noms (non vides) par des noms à accents / caractères spéciaux."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    candidates = np.flatnonzero(df[colonne].notna().to_numpy())
    nb = int(len(df) * taux)
    lignes = rng.choice(candidates, size=min(nb, len(candidates)), replace=False)
    df.iloc[lignes, pos] = rng.choice(NOMS_SPECIAUX, size=len(lignes))
    return df


def injecter_defauts(tables: dict[str, pd.DataFrame], cfg: Config) -> dict[str, pd.DataFrame]:
    """Abîme clients, commandes et paiements. Les autres tables restent intactes."""
    # Graine différente de celle du générateur, mais toujours reproductible
    rng = np.random.default_rng(cfg.seed + 1)
    abimees = dict(tables)

    # Clients : valeurs manquantes (nom, email, region) + noms spéciaux + doublons
    clients = tables["clients"]
    for col in ("nom", "email", "region"):
        clients = vider_colonne(clients, _colonne(clients, "clients", col),
                                TAUX["manquantes"], rng)
    clients = noms_avec_caracteres_speciaux(
        clients, _colonne(clients, "clients", "nom"), TAUX["noms_speciaux"], rng)
    abimees["clients"] = ajouter_doublons(clients, TAUX["doublons"], rng)

    # Commandes : dates futures + montants texte / outliers + doublons
    commandes = dates_dans_le_futur(
        tables["commandes"], _colonne(tables["commandes"], "commandes", "date_commande"),
        TAUX["dates_futur"], rng, cfg.date_fin)
    commandes = abimer_montants(
        commandes, _colonne(commandes, "commandes", "montant_total", "montant"),
        TAUX["montants_texte"], TAUX["outliers"], rng)
    abimees["commandes"] = ajouter_doublons(commandes, TAUX["doublons"], rng)

    # Paiements : dates futures + montants texte / outliers + doublons
    paiements = dates_dans_le_futur(
        tables["paiements"], _colonne(tables["paiements"], "paiements", "date_paiement"),
        TAUX["dates_futur"], rng, cfg.date_fin)
    paiements = abimer_montants(
        paiements, _colonne(paiements, "paiements", "montant", "montant_total"),
        TAUX["montants_texte"], TAUX["outliers"], rng)
    abimees["paiements"] = ajouter_doublons(paiements, TAUX["doublons"], rng)

    for nom in ("clients", "commandes", "paiements"):
        logger.info("Défauts injectés dans %-10s : %d -> %d lignes",
                    nom, len(tables[nom]), len(abimees[nom]))
    return abimees
