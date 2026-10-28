"""Point d'entrée : c'est le chef d'orchestre.

    python -m src.main                  # génère + nettoie
    python -m src.main --nettoyage      # nettoie seulement (fichiers bruts existants)
"""
import argparse
import logging
import sys

from src.config import Config
from src.defauts import injecter_defauts
from src.erreurs import ConfigurationError, DonneesInvalidesError
from src.export import exporter
from src.generateur import generer_tout
from src.logger import configurer_logging
from src.nettoyage import (charger_csv, nettoyer_clients, nettoyer_commandes,
                           nettoyer_paiements)
from src.schemas import COLONNES, COLONNES_DATES

logger = logging.getLogger(__name__)


def generer_brut(cfg: Config) -> None:
    """Génère les données, les abîme, et les écrit dans data/brut/."""
    tables = injecter_defauts(generer_tout(cfg), cfg)
    for nom, df in tables.items():
        exporter(df, nom, cfg.dossier_sortie / "brut")


def nettoyer_vers_propre(cfg: Config) -> None:
    """Relit data/brut/*.csv, nettoie, et écrit dans data/propre/."""
    brut = cfg.dossier_sortie / "brut"
    tables = {nom: charger_csv(brut / f"{nom}.csv", COLONNES[nom], COLONNES_DATES[nom])
              for nom in COLONNES}

    commandes = nettoyer_commandes(tables["commandes"], cfg.date_fin, produits=tables["produits"])
    propres = dict(tables)  # vendeurs, produits, avis, evenements : déjà corrects
    propres["clients"] = nettoyer_clients(tables["clients"])
    propres["commandes"] = commandes
    propres["paiements"] = nettoyer_paiements(tables["paiements"], commandes, cfg.date_fin)

    for nom, df in propres.items():
        exporter(df, nom, cfg.dossier_sortie / "propre")


def main(argv=None, cfg: Config | None = None) -> int:
    """Retourne 0 si tout va bien, 1 en cas d'erreur attendue (avec message clair)."""
    parser = argparse.ArgumentParser(description="Générateur de données SenMarket")
    parser.add_argument("--nettoyage", action="store_true",
                        help="ne pas régénérer : nettoyer les fichiers bruts existants")
    args = parser.parse_args(argv)

    configurer_logging()
    try:
        cfg = cfg or Config.depuis_env()
        if not args.nettoyage:
            generer_brut(cfg)
        nettoyer_vers_propre(cfg)
    except (ConfigurationError, DonneesInvalidesError) as erreur:
        logger.error("ARRÊT : %s", erreur)
        return 1
    logger.info("Terminé avec succès.")
    return 0


if __name__ == "__main__":
    sys.exit(main())