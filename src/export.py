"""Export : écrire une table dans les trois formats du projet."""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _compatible_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Parquet exige un seul type par colonne.

    Une colonne mixte (ex. montants 1000 et "1000.00 €", défaut voulu des données
    brutes) est donc enregistrée en texte dans le .parquet. CSV et JSON la gardent telle quelle.
    """
    df = df.copy()
    for col in df.columns[df.dtypes == object]:
        if len({type(v) for v in df[col].dropna()}) > 1:
            df[col] = df[col].map(lambda v: v if pd.isna(v) else str(v))
    return df


def exporter(df: pd.DataFrame, nom: str, dossier) -> None:
    """Écrit `nom`.csv, `nom`.json (une ligne = un enregistrement) et `nom`.parquet.

    Relancer écrase les fichiers : le résultat est le même à chaque fois
    (c'est de l'idempotence, notion centrale en data engineering).
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    df.to_csv(dossier / f"{nom}.csv", index=False, encoding="utf-8")
    df.to_json(dossier / f"{nom}.json", orient="records", lines=True,
               date_format="iso", force_ascii=False)
    _compatible_parquet(df).to_parquet(dossier / f"{nom}.parquet", index=False)
    logger.info("Exporté %-10s -> %s (%d lignes, 3 formats)", nom, dossier, len(df))