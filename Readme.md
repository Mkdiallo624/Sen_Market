# SenMarket — Étape 0 : le générateur de données

SenMarket est une marketplace sénégalaise fictive. Ce dépôt contient le générateur
qui fabrique ses données (clients, vendeurs, produits, commandes, paiements mobiles,
avis, événements de navigation), les abîme volontairement, puis les nettoie.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows : copy .env.example .env
```

## Utilisation

```bash
python -m src.main                 # génère les données brutes puis les nettoie
python -m src.main --nettoyage     # nettoie seulement les fichiers bruts existants
pytest                             # lance tous les tests
```

Les volumes se règlent dans `.env` (de quelques milliers à plusieurs millions de lignes).

## Résultat

```
data/brut/     données avec défauts (doublons, valeurs manquantes, dates absurdes)
data/propre/   données nettoyées
               chaque table en .csv, .json (une ligne par enregistrement) et .parquet
logs/          journal d'exécution
```

## Structure du code

| Fichier | Rôle |
|---|---|
| `src/config.py` | Lit et valide les réglages du `.env` |
| `src/generateur.py` | Fabrique les 7 tables |
| `src/defauts.py` | Injecte doublons, manquants, dates incohérentes |
| `src/nettoyage.py` | Lecture sécurisée + corrections |
| `src/export.py` | Écrit CSV, JSON, Parquet |
| `src/schemas.py` | Colonnes attendues de chaque table |
| `src/erreurs.py` | Erreurs « attendues » avec messages clairs |
| `src/logger.py` | Journalisation |
| `src/main.py` | Chef d'orchestre |

## Mettre à l'épreuve

Corrompre un fichier et vérifier l'échec propre :

```bash
python -m src.main
echo "colonne_bizarre" > data/brut/commandes.csv
python -m src.main --nettoyage     # ARRÊT : Colonne(s) ['commande_id', ...] introuvable(s)
```

## Décisions

- Choix des formats : voir `docs/decision_formats.md`.