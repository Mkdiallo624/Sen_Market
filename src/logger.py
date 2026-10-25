"""Journalisation (logging).

Un programme de données tourne souvent sans personne devant l'écran.
Le journal est sa « boîte noire » : on y lit ce qui s'est passé, et surtout
pourquoi ça a échoué. On écrit à la fois à l'écran et dans logs/senmarket.log.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def configurer_logging() -> None:
    load_dotenv()
    niveau = os.getenv("NIVEAU_LOG", "INFO").upper()
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/senmarket.log", encoding="utf-8"),
        ],
    )
