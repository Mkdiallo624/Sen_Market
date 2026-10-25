"""Export : écrire une table dans les trois formats du projet."""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def exporter(df: pd.DataFrame, nom: str, dossier) -> None:
    """Écrit `nom`.csv, `nom`.json (une ligne = un enregistrement) et `nom`.parquet.

    Relancer écrase les fichiers : le résultat est le même à chaque fois
    (c'est de l'idempotence, notion centrale en data engineering).
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    df.to_csv(dossier / f"{nom}.csv", index=False)
    df.to_json(dossier / f"{nom}.json", orient="records", lines=True,
               date_format="iso", force_ascii=False)
    df.to_parquet(dossier / f"{nom}.parquet", index=False)
    logger.info("Exporté %-10s -> %s (%d lignes, 3 formats)", nom, dossier, len(df))