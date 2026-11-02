"""Lecture sécurisée des fichiers + nettoyage avec Pandas.

Deux responsabilités :
1. charger_csv : lire un fichier en vérifiant qu'il est exploitable,
   et sinon échouer avec un message CLAIR (pas une erreur Python cryptique).
2. nettoyer_* : retirer ou corriger les défauts, en journalisant chaque
   correction (« combien de lignes retirées / corrigées, et pourquoi »).

PRINCIPE : on ne JUGE pas une donnée dérivée, on la RECONSTRUIT.
  - montant_ligne  = prix_unitaire x quantite
  - montant_total  = somme des montant_ligne de la commande
  - paiements.montant = montant_total de la commande
Les outliers (999999.99), les montants en texte (« 42.50 FCFA ») et les montants
manquants de ces colonnes disparaissent donc d'eux-mêmes, sans règle statistique
(qui échoue ici : une commande légitime peut déjà dépasser 1 M FCFA).

On ne supprime que ce qui est irrécupérable (doublons, date de commande future,
commande dont une ligne ne peut pas être reconstruite, lignes/paiements orphelins).
Les noms avec accents / caractères spéciaux sont conservés, jamais supprimés.

Ordre d'appel (voir main.py) :
  nettoyer_clients -> nettoyer_commandes -> nettoyer_lignes_commande
  -> recalculer_totaux -> nettoyer_paiements
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

# Symboles de devise acceptés dans un montant écrit en texte.
DEVISES = r"fcfa|xof|cfa|€"

# Délai paiement - commande utilisé si on doit recréer une date de paiement
# et qu'aucun paiement valide ne permet d'estimer le délai habituel.
DELAI_PAIEMENT_PAR_DEFAUT = pd.Timedelta(minutes=30)


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
        # traitée ensuite au nettoyage au lieu de faire planter le programme.
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df[colonnes_attendues]


def _journaliser(table: str, raison: str, avant: int, apres: int) -> None:
    if avant != apres:
        logger.info("[%s] %s : %d ligne(s) retirée(s)", table, raison, avant - apres)


def _limite_futur(date_fin: str) -> pd.Timestamp:
    """Première date INTERDITE : le lendemain de date_fin à minuit.

    Une date est dans le futur si date >= limite. Cela laisse une marge d'un jour :
    un paiement fait 30 min après une commande de 23 h 50 le dernier jour reste valide.
    """
    return pd.Timestamp(date_fin) + pd.Timedelta(days=1)


# ---------------------------------------------------------------- montants

def _convertir_montants(df: pd.DataFrame, colonne: str, table: str) -> pd.DataFrame:
    """Transforme « 42.50 FCFA » (ou « 1 234,50 € ») en nombre. Illisible -> NaN.

    Limite connue : « 1,234.50 » (virgule des milliers) n'est pas géré.
    """
    serie = df[colonne]
    if pd.api.types.is_numeric_dtype(serie):
        return df
    texte = serie.astype(str)  # NaN devient "nan", re-converti en NaN juste après
    avec_devise = int(texte.str.contains(DEVISES, regex=True, flags=re.IGNORECASE).sum())
    propre = (texte.str.replace(DEVISES, "", regex=True, flags=re.IGNORECASE)
                   .str.replace(r"\s", "", regex=True)       # espaces, y compris insécables
                   .str.replace(",", ".", regex=False))
    nombres = pd.to_numeric(propre, errors="coerce")
    illisibles = int(nombres.isna().sum() - serie.isna().sum())
    if avec_devise:
        logger.info("[%s] %s : %d montant(s) en texte converti(s) en nombre",
                    table, colonne, avec_devise)
    if illisibles:
        logger.info("[%s] %s : %d montant(s) illisible(s) -> considérés manquants",
                    table, colonne, illisibles)
    return df.assign(**{colonne: nombres})


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


def nettoyer_commandes(df: pd.DataFrame, date_fin: str) -> pd.DataFrame:
    """Doublons + dates. Le montant_total (souvent faux) est écarté : recalculer_totaux le refait."""
    avant = len(df)
    df = df.drop_duplicates(subset="commande_id")
    _journaliser("commandes", "doublons", avant, len(df))

    # Une date de commande absente ou dans le futur est irrécupérable : on retire la commande.
    avant = len(df)
    df = df.dropna(subset=["date_commande"])
    _journaliser("commandes", "date manquante ou illisible", avant, len(df))

    avant = len(df)
    df = df[df["date_commande"] < _limite_futur(date_fin)]
    _journaliser("commandes", "date dans le futur", avant, len(df))

    if "montant_total" in df.columns:
        df = df.drop(columns="montant_total")   # sera reconstruit à partir des lignes
    return df.reset_index(drop=True)


def nettoyer_lignes_commande(df: pd.DataFrame, produits: pd.DataFrame,
                             commandes_propres: pd.DataFrame) -> pd.DataFrame:
    avant = len(df)
    df = df.drop_duplicates(subset="ligne_id")
    _journaliser("lignes_commande", "doublons", avant, len(df))

    # Une ligne ne doit pas pointer vers une commande retirée au nettoyage
    avant = len(df)
    df = df[df["commande_id"].isin(commandes_propres["commande_id"])].copy()
    _journaliser("lignes_commande", "commande absente ou invalide", avant, len(df))

    # Prix manquant : on le relit dans le catalogue (produits n'a pas de défauts)
    prix_ref = produits.set_index("produit_id")["prix"]
    df["prix_unitaire"] = pd.to_numeric(df["prix_unitaire"], errors="coerce")
    manquants = df["prix_unitaire"].isna()
    if manquants.any():
        df.loc[manquants, "prix_unitaire"] = df.loc[manquants, "produit_id"].map(prix_ref)
        relus = int(df.loc[manquants, "prix_unitaire"].notna().sum())
        logger.info("[lignes_commande] prix_unitaire manquant : %d valeur(s) relue(s) dans produits",
                    relus)

    # Montant en texte -> nombre (peut rester NaN ou valoir un outlier : il ne sert que
    # à retrouver une quantité, et sera recalculé plus bas).
    df = _convertir_montants(df, "montant_ligne", "lignes_commande")

    # Quantité impossible : on la RETROUVE par montant_ligne / prix_unitaire, mais seulement
    # si le résultat est un entier plausible (un outlier ne donne jamais un entier).
    quantite = pd.to_numeric(df["quantite"], errors="coerce")
    invalide = quantite.isna() | (quantite <= 0) | (quantite != quantite.round())
    if invalide.any():
        plafond = quantite[~invalide].max()          # plus grande quantité observée et valide
        estimee = df["montant_ligne"] / df["prix_unitaire"].replace(0, np.nan)
        arrondie = estimee.round()
        fiable = (invalide & ((estimee - arrondie).abs() < 1e-6)
                  & (arrondie >= 1) & (arrondie <= plafond))
        quantite = quantite.mask(fiable, arrondie)
        logger.info("[lignes_commande] quantité invalide : %d valeur(s) retrouvée(s) "
                    "(montant / prix)", int(fiable.sum()))
        invalide = invalide & ~fiable

    # Reste irrécupérable (quantité ET montant abîmés, ou produit inconnu) : on retire TOUTE
    # la commande, sinon son montant_total recalculé serait faux.
    perdue = invalide | df["prix_unitaire"].isna()
    if perdue.any():
        commandes_perdues = df.loc[perdue, "commande_id"].unique()
        garder = ~df["commande_id"].isin(commandes_perdues)
        logger.info("[lignes_commande] %d commande(s) irrécupérable(s) : %d ligne(s) retirée(s)",
                    len(commandes_perdues), int((~garder).sum()))
        df, quantite = df[garder].copy(), quantite[garder]

    df["quantite"] = quantite.astype("int64")
    df["prix_unitaire"] = df["prix_unitaire"].astype("int64")

    # Montant : toujours recalculé (corrige aussi l'outlier et le texte illisible)
    attendu = df["prix_unitaire"] * df["quantite"]
    corriges = int((df["montant_ligne"] != attendu).sum())
    if corriges:
        logger.info("[lignes_commande] montant_ligne : %d valeur(s) recalculée(s) (prix x quantité)",
                    corriges)
    df["montant_ligne"] = attendu
    return df.reset_index(drop=True)


def recalculer_totaux(commandes: pd.DataFrame, lignes: pd.DataFrame) -> pd.DataFrame:
    """montant_total = somme des montant_ligne. Une commande sans ligne valide est retirée."""
    totaux = lignes.groupby("commande_id")["montant_ligne"].sum()
    avant = len(commandes)
    commandes = commandes.assign(montant_total=commandes["commande_id"].map(totaux))
    commandes = commandes.dropna(subset=["montant_total"])
    _journaliser("commandes", "aucune ligne de commande valide", avant, len(commandes))
    return commandes.astype({"montant_total": "int64"}).reset_index(drop=True)


def nettoyer_paiements(df: pd.DataFrame, commandes_propres: pd.DataFrame,
                       date_fin: str) -> pd.DataFrame:
    """Doublons, orphelins, puis montant et date alignés sur la commande."""
    avant = len(df)
    df = df.drop_duplicates(subset="paiement_id")
    _journaliser("paiements", "doublons", avant, len(df))

    # On joint avec les commandes valides : un paiement sans commande valide est « orphelin »
    avant = len(df)
    ref = commandes_propres[["commande_id", "date_commande", "montant_total"]].rename(
        columns={"date_commande": "_date_commande", "montant_total": "_montant_commande"})
    df = df.merge(ref, on="commande_id", how="inner")
    _journaliser("paiements", "commande absente ou invalide", avant, len(df))

    # Montant : le paiement vaut le montant de la commande (texte et outliers disparaissent)
    df = _convertir_montants(df, "montant", "paiements")
    differents = int((df["montant"] != df["_montant_commande"]).sum())
    if differents:
        logger.info("[paiements] montant : %d valeur(s) alignée(s) sur la commande", differents)
    df["montant"] = df["_montant_commande"].astype("int64")

    # Date impossible (manquante, dans le futur, ou AVANT la commande) : on la recrée avec le
    # délai médian observé sur les paiements valides.
    d = df["date_paiement"]
    invalide = d.isna() | (d >= _limite_futur(date_fin)) | (d < df["_date_commande"])
    if invalide.any():
        delais = (d - df["_date_commande"])[~invalide]
        delai = delais.median() if len(delais) else DELAI_PAIEMENT_PAR_DEFAUT
        if pd.isna(delai):
            delai = DELAI_PAIEMENT_PAR_DEFAUT
        df.loc[invalide, "date_paiement"] = df.loc[invalide, "_date_commande"] + delai
        logger.info("[paiements] date_paiement impossible : %d valeur(s) recréée(s) "
                    "(commande + délai médian %s)", int(invalide.sum()), delai)

    return df.drop(columns=["_date_commande", "_montant_commande"]).reset_index(drop=True)