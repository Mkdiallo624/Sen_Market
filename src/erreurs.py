"""Nos propres types d'erreurs.

Pourquoi ? Pour distinguer une erreur ATTENDUE (fichier abîmé, mauvaise
configuration) d'un vrai BUG du programme. Les premières, on les explique
à l'utilisateur en une phrase claire ; les secondes, on veut voir le détail.
"""


class ConfigurationError(Exception):
    """La configuration (.env) contient une valeur impossible."""


class DonneesInvalidesError(Exception):
    """Un fichier d'entrée est introuvable, vide, illisible ou incomplet."""