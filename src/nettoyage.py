"""Lecture sécurisée des fichiers + nettoyage avec Pandas.

Deux responsabilités :
1. charger_csv : lire un fichier en vérifiant qu'il est exploitable,
   et sinon échouer avec un message CLAIR (pas une erreur Python cryptique).
2. nettoyer_* : retirer ou corriger les défauts, en journalisant chaque
   correction (« combien de lignes retirées, et pourquoi »).
"""
import logging
from pathlib import Path

import pandas as pd

from src.erreurs import DonneesInvalidesError

logger = logging.getLogger(__name__)


def charger_csv(chemin, colonnes_attendues: list[str], colonnes_dates=()) -> pd.DataFrame:
    """Lit un CSV et vérifie qu'il est valide. Lève DonneesInvalidesError sinon."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise DonneesInvalidesError(
            f"Fichier introuvable : {chemin}. Lancez d'abord la génération des données."
        )
    try:
        df = pd.read_csv(chemin)
    except pd.errors.EmptyDataError:
        raise DonneesInvalidesError(f"Le fichier {chemin} est vide.") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        raise DonneesInvalidesError(f"Le fichier {chemin} est corrompu : {e}") from None

    manquantes = [c for c in colonnes_attendues if c not in df.columns]
    if manquantes:
        raise DonneesInvalidesError(
            f"Colonne(s) {manquantes} introuvable(s) dans {chemin.name}. "
            f"Colonnes présentes : {list(df.columns)}."
        )
    for col in colonnes_dates:
        # errors="coerce" : une date illisible devient NaT (« date manquante »),
        # qui sera retirée au nettoyage au lieu de faire planter le programme.
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df[colonnes_attendues]


def _journaliser(table: str, raison: str, avant: int, apres: int) -> None:
    if avant != apres:
        logger.info("[%s] %s : %d ligne(s) retirée(s)", table, raison, avant - apres)


def nettoyer_clients(df: pd.DataFrame) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="client_id")
    _journaliser("clients", "doublons", avant, len(df))
    # Ici on GARDE le client : supprimer des clients rendrait ses commandes orphelines.
    manquants = int(df["telephone"].isna().sum())
    if manquants:
        logger.info("[clients] téléphone manquant : %d valeur(s) remplacée(s) par 'inconnu'", manquants)
    return df.assign(telephone=df["telephone"].fillna("inconnu")).reset_index(drop=True)


def nettoyer_commandes(df: pd.DataFrame, date_fin: str) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="commande_id")
    _journaliser("commandes", "doublons", avant, len(df))

    avant = len(df)
    df = df.dropna(subset=["montant_total", "date_commande"])
    _journaliser("commandes", "montant ou date manquant", avant, len(df))

    avant = len(df)
    df = df[df["montant_total"] > 0]
    _journaliser("commandes", "montant nul ou négatif", avant, len(df))

    avant = len(df)
    df = df[df["date_commande"] <= pd.Timestamp(date_fin)]
    _journaliser("commandes", "date dans le futur", avant, len(df))

    return df.astype({"montant_total": "int64"}).reset_index(drop=True)


def nettoyer_paiements(df: pd.DataFrame, commandes_propres: pd.DataFrame) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="paiement_id")
    _journaliser("paiements", "doublons", avant, len(df))

    # On joint avec les commandes valides : un paiement sans commande valide est « orphelin »
    avant = len(df)
    dates_commandes = commandes_propres[["commande_id", "date_commande"]]
    df = df.merge(dates_commandes, on="commande_id", how="inner")
    _journaliser("paiements", "commande absente ou invalide", avant, len(df))

    # On ne peut pas payer AVANT d'avoir commandé
    avant = len(df)
    df = df[df["date_paiement"] >= df["date_commande"]]
    _journaliser("paiements", "paiement antérieur à la commande", avant, len(df))

    return df.drop(columns="date_commande").reset_index(drop=True)