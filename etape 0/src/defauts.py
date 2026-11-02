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

# Taux de défauts (proportion des lignes de chaque table concernée) pour
# cfg.taux_defauts == TAUX_REFERENCE. Pour une autre valeur de TAUX_DEFAUTS (.env),
# tous les taux sont multipliés par cfg.taux_defauts / TAUX_REFERENCE.
TAUX_REFERENCE = 0.05
TAUX = {
    "doublons": 0.05,        # lignes recopiées
    "manquantes": 0.08,      # par colonne : nom, email, region (et prix_unitaire)
    "dates_futur": 0.02,     # dates postérieures à DATE_FIN
    "montants_texte": 0.03,  # montant stocké en texte, ex. "42.50 FCFA"
    "outliers": 0.01,        # montant = VALEUR_OUTLIER
    "noms_speciaux": 0.02,   # noms avec accents / caractères spéciaux
    "quantites_invalides": 0.02,  # quantite <= 0 (lignes_commande)
}

VALEUR_OUTLIER = 999999.99

NOMS_SPECIAUX = [
    "Éloïse Müller-Ødegård", "Zoë Çelik", "Bjørn Åkesson", "Renée Dvořák",
    "Łukasz Wiśniewski", "Núria Peña-Ibáñez", "Søren Kierkegård",
    "Chloé Lefèvre-Bœuf", "Şebnem Yıldız", "Anaïs Fröhlich",
]


def _taux_effectifs(cfg: Config) -> dict[str, float]:
    """Applique cfg.taux_defauts aux taux de référence (plafonnés à 100 %)."""
    facteur = cfg.taux_defauts / TAUX_REFERENCE
    return {nom: min(valeur * facteur, 1.0) for nom, valeur in TAUX.items()}


def _lignes_au_hasard(rng, df: pd.DataFrame, taux: float) -> np.ndarray:
    nb = int(len(df) * taux)
    return rng.choice(len(df), size=nb, replace=False)


def _tirage_disjoint(rng, df: pd.DataFrame, *taux: float) -> list[np.ndarray]:
    """Tire des groupes de lignes sans aucun chevauchement entre eux.

    Si la table est trop petite pour tous les groupes, les derniers sont tronqués
    au lieu de lever une ValueError.
    """
    tailles = [int(len(df) * t) for t in taux]
    total = min(sum(tailles), len(df))
    lignes = rng.choice(len(df), size=total, replace=False)
    bornes = np.minimum(np.cumsum([0] + tailles), total)
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
    """Montants en texte (« 42.50 FCFA ») et outliers, sur des lignes forcément différentes."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    lignes_texte, lignes_outliers = _tirage_disjoint(rng, df, taux_texte, taux_outliers)
    df[colonne] = df[colonne].astype(object)  # la colonne devient mixte (nombres + texte)
    df.iloc[lignes_texte, pos] = [v if pd.isna(v) else f"{float(v):.2f} FCFA"
                                  for v in df.iloc[lignes_texte, pos]]
    df.iloc[lignes_outliers, pos] = VALEUR_OUTLIER
    return df


def noms_avec_caracteres_speciaux(df: pd.DataFrame, colonne: str, taux: float, rng) -> pd.DataFrame:
    """Remplace `taux` % des noms (non vides) par des noms à accents / caractères spéciaux."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    non_vides = df[colonne].notna() & (df[colonne].astype(str).str.strip() != "")
    candidates = np.flatnonzero(non_vides.to_numpy())
    nb = int(len(df) * taux)
    lignes = rng.choice(candidates, size=min(nb, len(candidates)), replace=False)
    df.iloc[lignes, pos] = rng.choice(NOMS_SPECIAUX, size=len(lignes))
    return df


def quantites_invalides(df: pd.DataFrame, colonne: str, taux: float, rng) -> pd.DataFrame:
    """Remplace `taux` % des quantités par 0, -1 ou -2 (valeur impossible)."""
    df = df.copy()
    pos = df.columns.get_loc(colonne)
    lignes = _lignes_au_hasard(rng, df, taux)
    df.iloc[lignes, pos] = rng.choice([0, -1, -2], size=len(lignes))
    return df


def injecter_defauts(tables: dict[str, pd.DataFrame], cfg: Config) -> dict[str, pd.DataFrame]:
    """Abîme clients, commandes, paiements et lignes_commande. Les autres tables restent intactes."""
    # Graine différente de celle du générateur, mais toujours reproductible
    rng = np.random.default_rng(cfg.seed + 1)
    t = _taux_effectifs(cfg)
    abimees = dict(tables)

    # Clients : valeurs manquantes (nom, email, region) + noms spéciaux + doublons
    clients = tables["clients"]
    for col in ("nom", "email", "region"):
        clients = vider_colonne(clients, _colonne(clients, "clients", col), t["manquantes"], rng)
    clients = noms_avec_caracteres_speciaux(
        clients, _colonne(clients, "clients", "nom"), t["noms_speciaux"], rng)
    abimees["clients"] = ajouter_doublons(clients, t["doublons"], rng)

    # Commandes : dates futures + montants texte / outliers + doublons
    commandes = dates_dans_le_futur(
        tables["commandes"], _colonne(tables["commandes"], "commandes", "date_commande"),
        t["dates_futur"], rng, cfg.date_fin)
    commandes = abimer_montants(
        commandes, _colonne(commandes, "commandes", "montant_total", "montant"),
        t["montants_texte"], t["outliers"], rng)
    abimees["commandes"] = ajouter_doublons(commandes, t["doublons"], rng)

    # Paiements : dates futures + montants texte / outliers + doublons
    paiements = dates_dans_le_futur(
        tables["paiements"], _colonne(tables["paiements"], "paiements", "date_paiement"),
        t["dates_futur"], rng, cfg.date_fin)
    paiements = abimer_montants(
        paiements, _colonne(paiements, "paiements", "montant", "montant_total"),
        t["montants_texte"], t["outliers"], rng)
    abimees["paiements"] = ajouter_doublons(paiements, t["doublons"], rng)

    # Lignes de commande : quantités invalides + prix manquants
    # + montants texte / outliers + doublons
    lignes = tables["lignes_commande"]
    lignes = quantites_invalides(
        lignes, _colonne(lignes, "lignes_commande", "quantite"), t["quantites_invalides"], rng)
    col_prix = _colonne(lignes, "lignes_commande", "prix_unitaire")
    lignes = lignes.astype({col_prix: "float64"})  # pour accepter les NaN
    lignes = vider_colonne(lignes, col_prix, t["manquantes"], rng)
    lignes = abimer_montants(
        lignes, _colonne(lignes, "lignes_commande", "montant_ligne"),
        t["montants_texte"], t["outliers"], rng)
    abimees["lignes_commande"] = ajouter_doublons(lignes, t["doublons"], rng)

    for nom in ("clients", "commandes", "paiements", "lignes_commande"):
        logger.info("Défauts injectés dans %-16s : %d -> %d lignes",
                    nom, len(tables[nom]), len(abimees[nom]))
    return abimees