"""Configuration : tous les réglages au même endroit.

Les valeurs viennent du fichier .env (ou de variables d'environnement).
Ainsi, changer le volume de données ne demande JAMAIS de modifier le code.
"""
import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.erreurs import ConfigurationError

_NOMBRES_POSITIFS = (
    "nb_clients", "nb_vendeurs", "nb_produits",
    "nb_commandes", "nb_avis", "nb_evenements",
)


@dataclass(frozen=True)
class Config:
    nb_clients: int = 1000
    nb_vendeurs: int = 50
    nb_produits: int = 200
    nb_commandes: int = 5000
    nb_avis: int = 2000
    nb_evenements: int = 20000
    taux_defauts: float = 0.05
    seed: int = 42
    date_fin: str = "2026-10-25"
    dossier_sortie: Path = Path("data")

    def __post_init__(self):
        # On refuse tout de suite les valeurs absurdes (échouer tôt = échouer clairement)
        for nom in _NOMBRES_POSITIFS:
            if getattr(self, nom) <= 0:
                raise ConfigurationError(f"{nom.upper()} doit être supérieur à 0.")
        if not 0 <= self.taux_defauts <= 0.5:
            raise ConfigurationError("TAUX_DEFAUTS doit être compris entre 0 et 0.5.")
        try:
            datetime.date.fromisoformat(self.date_fin)
        except ValueError:
            raise ConfigurationError(
                f"DATE_FIN '{self.date_fin}' invalide : format attendu AAAA-MM-JJ."
            ) from None

    @classmethod
    def depuis_env(cls) -> "Config":
        """Construit la configuration à partir du fichier .env."""
        load_dotenv()
        try:
            return cls(
                nb_clients=int(os.getenv("NB_CLIENTS", cls.nb_clients)),
                nb_vendeurs=int(os.getenv("NB_VENDEURS", cls.nb_vendeurs)),
                nb_produits=int(os.getenv("NB_PRODUITS", cls.nb_produits)),
                nb_commandes=int(os.getenv("NB_COMMANDES", cls.nb_commandes)),
                nb_avis=int(os.getenv("NB_AVIS", cls.nb_avis)),
                nb_evenements=int(os.getenv("NB_EVENEMENTS", cls.nb_evenements)),
                taux_defauts=float(os.getenv("TAUX_DEFAUTS", cls.taux_defauts)),
                seed=int(os.getenv("SEED", cls.seed)),
                date_fin=os.getenv("DATE_FIN", cls.date_fin),
                dossier_sortie=Path(os.getenv("DOSSIER_SORTIE", str(cls.dossier_sortie))),
            )
        except ValueError as e:
            raise ConfigurationError(f"Valeur non numérique dans .env : {e}") from None
