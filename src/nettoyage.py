"""Lecture sécurisée des fichiers + nettoyage avec Pandas.

Deux responsabilités :
1. charger_csv : lire un fichier en vérifiant qu'il est exploitable,
   et sinon échouer avec un message CLAIR (pas une erreur Python cryptique).
2. nettoyer_* : retirer ou corriger les défauts, en journalisant chaque
   correction (« combien de lignes retirées, et pourquoi »).

Défauts gérés : doublons, valeurs manquantes (nom, email, region), dates dans le
futur, montants écrits en texte (« 42.50 € »), montants aberrants (outliers),
noms avec accents / caractères spéciaux (conservés, jamais supprimés).

Les outliers sont détectés par COHÉRENCE (montant_total = prix x quantité ; montant du
paiement = montant de la commande) : une règle purement statistique échoue ici, car
certaines commandes légitimes (Électronique x 5) atteignent déjà ~1,2 M FCFA.
"""
import logging
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from src.erreurs import DonneesInvalidesError

logger = logging.getLogger(__name__)

# Valeur de remplacement quand on GARDE le client malgré une valeur manquante.
# L'email n'est volontairement pas dans la liste : « inconnu » n'est pas un email,
# on le laisse vide plutôt que d'inventer une fausse valeur.
VALEURS_PAR_DEFAUT_CLIENTS = {"telephone": "inconnu", "nom": "inconnu", "region": "inconnu"}

# Règle de SECOURS (quand on n'a pas de référence pour vérifier la cohérence) :
# outlier = montant > Q3 + FACTEUR_OUTLIER x (Q3 - Q1).
FACTEUR_OUTLIER = 10

# Colonnes de montant possibles dans la table paiements (selon votre schéma).
COLONNES_MONTANT_PAIEMENTS = ("montant", "montant_total")


def charger_csv(chemin, colonnes_attendues: list[str], colonnes_dates=()) -> pd.DataFrame:
    """Lit un CSV et vérifie qu'il est valide. Lève DonneesInvalidesError sinon."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise DonneesInvalidesError(
            f"Fichier introuvable : {chemin}. Lancez d'abord la génération des données."
        )
    try:
        # utf-8-sig lit l'UTF-8 normal ET celui avec BOM (fichiers enregistrés par Excel) :
        # indispensable pour ne pas abîmer « Éloïse Müller-Ødegård ».
        df = pd.read_csv(chemin, encoding="utf-8-sig")
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


# ---------------------------------------------------------------- montants

def _convertir_montants(df: pd.DataFrame, colonne: str, table: str) -> pd.DataFrame:
    """Transforme « 42.50 € » (ou « 1 234,50 € ») en nombre. Illisible -> NaN."""
    serie = df[colonne]
    if pd.api.types.is_numeric_dtype(serie):
        return df
    texte = serie.astype(str)  # NaN devient "nan", re-converti en NaN juste après
    avec_euro = int(texte.str.contains("€", regex=False).sum())
    propre = (texte.str.replace("€", "", regex=False)
                   .str.replace(r"\s", "", regex=True)       # espaces, y compris insécables
                   .str.replace(",", ".", regex=False))
    nombres = pd.to_numeric(propre, errors="coerce")
    illisibles = int(nombres.isna().sum() - serie.isna().sum())
    if avec_euro:
        logger.info("[%s] %s : %d montant(s) en texte converti(s) en nombre",
                    table, colonne, avec_euro)
    if illisibles:
        logger.info("[%s] %s : %d montant(s) illisible(s) -> considérés manquants",
                    table, colonne, illisibles)
    return df.assign(**{colonne: nombres})


def _retirer_outliers(df: pd.DataFrame, colonne: str, table: str, montant_max=None) -> pd.DataFrame:
    """Retire les montants aberrants. Seuil automatique (Q3 + 10 x IQR) si non fourni."""
    if montant_max is None:
        q1, q3 = df[colonne].quantile([0.25, 0.75])
        iqr = q3 - q1
        if not iqr > 0:      # montants quasi constants : pas de seuil fiable, on ne touche à rien
            return df
        montant_max = q3 + FACTEUR_OUTLIER * iqr
    avant = len(df)
    df = df[df[colonne] <= montant_max]
    _journaliser(table, f"montant aberrant (> {montant_max:,.2f})", avant, len(df))
    return df


# ------------------------------------------------------------------- textes

def _reparer_encodage(texte: str) -> str:
    """Répare un texte « mojibake » (ex. « Ã©loÃ¯se » -> « Éloïse »). Sinon, ne change rien."""
    if not any(m in texte for m in ("Ã", "Â", "Å")):
        return texte
    for encodage in ("cp1252", "latin-1"):
        try:
            return texte.encode(encodage).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texte


def _normaliser_texte(valeur, minuscules: bool = False):
    """Normalise un texte SANS supprimer les caractères spéciaux : Unicode NFC, espaces nettoyés."""
    if not isinstance(valeur, str):
        return valeur
    valeur = unicodedata.normalize("NFC", _reparer_encodage(valeur))
    valeur = re.sub(r"\s+", " ", valeur).strip()
    if minuscules:
        valeur = valeur.lower()
    return valeur if valeur else np.nan   # une chaîne vide = valeur manquante


# ------------------------------------------------------------------ tables

def nettoyer_clients(df: pd.DataFrame) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="client_id").copy()
    _journaliser("clients", "doublons", avant, len(df))

    # Noms/villes/emails : on normalise l'Unicode mais on GARDE les caractères spéciaux.
    for col in ("nom", "region"):
        if col in df.columns:
            df[col] = df[col].map(_normaliser_texte)
    if "email" in df.columns:
        df["email"] = df["email"].map(lambda v: _normaliser_texte(v, minuscules=True))

    # Ici on GARDE le client : supprimer des clients rendrait ses commandes orphelines.
    for col, defaut in VALEURS_PAR_DEFAUT_CLIENTS.items():
        if col not in df.columns:
            continue
        manquants = int(df[col].isna().sum())
        if manquants:
            logger.info("[clients] %s manquant : %d valeur(s) remplacée(s) par '%s'",
                        col, manquants, defaut)
        df[col] = df[col].fillna(defaut)
    if "email" in df.columns:
        manquants = int(df["email"].isna().sum())
        if manquants:
            logger.info("[clients] email manquant : %d valeur(s) laissée(s) vide(s)", manquants)
    return df.reset_index(drop=True)


def _retirer_montants_incoherents(df: pd.DataFrame, produits: pd.DataFrame) -> pd.DataFrame:
    """Retire les commandes dont montant_total != prix du produit x quantité."""
    prix = df["produit_id"].map(produits.set_index("produit_id")["prix"])
    attendu = prix * df["quantite"]
    avant = len(df)
    df = df[attendu.isna() | (df["montant_total"] == attendu)]   # produit inconnu : on ne juge pas
    _journaliser("commandes", "montant incohérent avec prix x quantité", avant, len(df))
    return df


def nettoyer_commandes(df: pd.DataFrame, date_fin: str, montant_max=None,
                       produits: pd.DataFrame | None = None) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="commande_id")
    _journaliser("commandes", "doublons", avant, len(df))

    # Le montant peut être du texte (« 42.50 € ») : on le convertit AVANT toute comparaison.
    df = _convertir_montants(df, "montant_total", "commandes")

    avant = len(df)
    df = df.dropna(subset=["montant_total", "date_commande"])
    _journaliser("commandes", "montant ou date manquant", avant, len(df))

    avant = len(df)
    df = df[df["montant_total"] > 0]
    _journaliser("commandes", "montant nul ou négatif", avant, len(df))

    if produits is not None and {"produit_id", "quantite"} <= set(df.columns):
        df = _retirer_montants_incoherents(df, produits)
    else:
        df = _retirer_outliers(df, "montant_total", "commandes", montant_max)

    avant = len(df)
    df = df[df["date_commande"] <= pd.Timestamp(date_fin)]
    _journaliser("commandes", "date dans le futur", avant, len(df))

    return df.astype({"montant_total": "int64"}).reset_index(drop=True)


def nettoyer_paiements(df: pd.DataFrame, commandes_propres: pd.DataFrame,
                       date_fin: str | None = None, montant_max=None) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="paiement_id")
    _journaliser("paiements", "doublons", avant, len(df))

    # Montant du paiement (si la table en a un) : texte -> nombre
    colonne_montant = next((c for c in COLONNES_MONTANT_PAIEMENTS if c in df.columns), None)
    verifier_avec_commande = colonne_montant and "montant_total" in commandes_propres.columns
    if colonne_montant:
        df = _convertir_montants(df, colonne_montant, "paiements")
        avant = len(df)
        df = df.dropna(subset=[colonne_montant])
        _journaliser("paiements", "montant manquant ou illisible", avant, len(df))
        if not verifier_avec_commande:   # règle de secours (statistique)
            df = _retirer_outliers(df, colonne_montant, "paiements", montant_max)

    # Une date de paiement dans le futur est impossible (passer date_fin pour l'activer)
    if date_fin is not None:
        avant = len(df)
        df = df[df["date_paiement"] <= pd.Timestamp(date_fin)]
        _journaliser("paiements", "date dans le futur", avant, len(df))

    # On joint avec les commandes valides : un paiement sans commande valide est « orphelin »
    avant = len(df)
    colonnes_commandes = ["commande_id", "date_commande"]
    if verifier_avec_commande:
        colonnes_commandes.append("montant_total")
    df = df.merge(commandes_propres[colonnes_commandes].rename(columns={"montant_total": "_montant_commande"}),
                  on="commande_id", how="inner")
    _journaliser("paiements", "commande absente ou invalide", avant, len(df))

    # Le paiement doit correspondre au montant de la commande (sinon : montant aberrant)
    if verifier_avec_commande:
        avant = len(df)
        df = df[df[colonne_montant] == df["_montant_commande"]]
        _journaliser("paiements", "montant différent de la commande (aberrant)", avant, len(df))
        df = df.drop(columns="_montant_commande").astype({colonne_montant: "int64"})
    elif colonne_montant:
        df = df.astype({colonne_montant: "int64"})

    # On ne peut pas payer AVANT d'avoir commandé
    avant = len(df)
    df = df[df["date_paiement"] >= df["date_commande"]]
    _journaliser("paiements", "paiement antérieur à la commande", avant, len(df))

    return df.drop(columns="date_commande").reset_index(drop=True)