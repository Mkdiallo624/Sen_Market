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


def _lignes_au_hasard(rng, df: pd.DataFrame, taux: float) -> np.ndarray:
    nb = int(len(df) * taux)
    return rng.choice(len(df), size=nb, replace=False)


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


def injecter_defauts(tables: dict[str, pd.DataFrame], cfg: Config) -> dict[str, pd.DataFrame]:
    """Abîme clients, commandes et paiements. Les autres tables restent intactes."""
    # Graine différente de celle du générateur, mais toujours reproductible
    rng = np.random.default_rng(cfg.seed + 1)
    t = cfg.taux_defauts
    abimees = dict(tables)

    # Clients : téléphones manquants + doublons
    clients = vider_colonne(tables["clients"], "telephone", t, rng)
    abimees["clients"] = ajouter_doublons(clients, t, rng)

    # Commandes : montants manquants + dates dans le FUTUR + doublons
    commandes = vider_colonne(tables["commandes"], "montant_total", t, rng)
    commandes = decaler_dates(commandes, "date_commande", t / 2, rng, jours=730)
    abimees["commandes"] = ajouter_doublons(commandes, t, rng)

    # Paiements : date AVANT la commande (impossible) + doublons
    paiements = decaler_dates(tables["paiements"], "date_paiement", t / 2, rng, jours=-30)
    abimees["paiements"] = ajouter_doublons(paiements, t, rng)

    for nom in ("clients", "commandes", "paiements"):
        logger.info("Défauts injectés dans %-10s : %d -> %d lignes",
                    nom, len(tables[nom]), len(abimees[nom]))
    return abimees
