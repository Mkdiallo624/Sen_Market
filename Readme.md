# SenMarket — Étape 0 : le générateur de données

SenMarket est une marketplace sénégalaise fictive. Ce dépôt contient le générateur
qui fabrique ses données (clients, vendeurs, produits, commandes, paiements mobiles,
avis, événements de navigation), les **abîme volontairement**, puis les **nettoie**.

Pourquoi abîmer des données qu'on a soi-même générées ? Parce que les vraies données
sont toujours sales. Comme on contrôle les défauts, on peut vérifier que le nettoyage
les corrige tous.

## Installation

```bash
python -m venv mon_env
source mon_env/bin/activate        # Windows : mon_env\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows : copy .env.example .env
```

## Utilisation

Toujours depuis la **racine du projet**, avec `-m` (sinon : `ModuleNotFoundError: No module named 'src'`) :

```bash
python -m src.main                 # génère les données brutes puis les nettoie
python -m src.main --nettoyage     # nettoie seulement les fichiers bruts existants
pytest                             # lance tous les tests
```

Les volumes et la période se règlent dans `.env` (de quelques milliers à plusieurs millions de lignes).

## Résultat

```
data/brut/     données avec défauts
data/propre/   données nettoyées
               chaque table en .csv, .json (une ligne par enregistrement) et .parquet
logs/          journal d'exécution (combien de lignes corrigées, et pourquoi)
```

## Les défauts injectés (`src/defauts.py`)

Seules les tables **clients**, **commandes** et **paiements** sont abîmées ; vendeurs,
produits, avis et événements restent intacts. Les taux se règlent dans le dictionnaire
`TAUX` en haut du fichier, et sont calculés sur le nombre de lignes de chaque table.

| Défaut | Taux | Table · colonne | Exemple |
|---|---|---|---|
| Doublons | 5 % | clients, commandes, paiements | ligne recopiée à l'identique |
| Valeurs manquantes | 8 % **par colonne** | clients · `nom`, `email`, `region` | `NaN` |
| Dates dans le futur | 2 % | commandes · `date_commande`, paiements · `date_paiement` | 1 jour à 2 ans après `DATE_FIN` |
| Montants en texte | 3 % | commandes · `montant_total`, paiements · `montant` | `"17300.00 €"` |
| Outliers | 1 % | commandes · `montant_total`, paiements · `montant` | `999999.99` |
| Noms avec caractères spéciaux | 2 % | clients · `nom` | `Éloïse Müller-Ødegård` |

Détails de fabrication :
- Les montants en texte et les outliers sont tirés sur des lignes **différentes** (jamais `"999999.99 €"`).
- Les noms spéciaux ne tombent jamais sur un nom déjà vidé.
- Les doublons sont injectés **en dernier** : ce sont des copies exactes de lignes déjà abîmées.
- Tout est reproductible : même `SEED`, mêmes défauts.
- `TAUX_DEFAUTS` du `.env` n'est plus utilisé par `defauts.py` (les taux sont dans `TAUX`).

> Dans `data/brut/*.parquet`, une colonne mêlant nombres et texte (`montant_total`) est
> enregistrée **en texte**, car Parquet n'accepte qu'un type par colonne. Les `.csv` et
> `.json` bruts gardent le mélange.

## Le nettoyage (`src/nettoyage.py`)

Le nettoyage relit `data/brut/*.csv` (encodage `utf-8-sig`, qui accepte aussi les fichiers
Excel avec BOM) et corrige chaque défaut. Chaque correction est journalisée.

| Défaut | Traitement |
|---|---|
| Doublons | `drop_duplicates` sur l'identifiant de la table |
| Montants en texte | `"2 500,00 €"` → `2500` (retire `€`, espaces, virgule décimale), **avant** toute comparaison |
| Outliers (commandes) | retirés si `montant_total` ≠ `prix × quantité` (prix lu dans `produits`) |
| Outliers (paiements) | retirés si `montant` ≠ montant de la commande correspondante |
| Dates dans le futur | commandes et paiements après `DATE_FIN` retirés |
| `nom`, `region` manquants | client **gardé**, valeur remplacée par `"inconnu"` (sinon ses commandes deviennent orphelines) |
| `email` manquant | client gardé, email laissé **vide** (« inconnu » n'est pas un email) |
| Noms spéciaux | **conservés**. On normalise seulement l'Unicode (NFC), les espaces, et on répare le texte mal décodé (`Ã©` → `é`) |
| Paiement sans commande valide | retiré (orphelin) |
| Paiement antérieur à la commande | retiré |

Pourquoi « cohérence » et pas un simple seuil pour les outliers ? Certaines commandes
légitimes atteignent déjà ~1,2 M FCFA (Électronique × 5) : `999999.99` n'est donc pas
« hors plage ». Seule la comparaison avec `prix × quantité` le détecte à coup sûr. Si on
ne fournit pas `produits`, une règle statistique de secours (Q3 + 10 × IQR) s'applique.

Les montants nettoyés sont des entiers (FCFA). Un outlier retiré dans `commandes`
fait aussi disparaître ses paiements (devenus orphelins) : le journal le montre.

### Exemple de journal (réglages par défaut, `SEED=42`)

```
[commandes] doublons : 250 ligne(s) retirée(s)
[commandes] montant_total : 150 montant(s) en texte converti(s) en nombre
[commandes] montant incohérent avec prix x quantité : 50 ligne(s) retirée(s)
[commandes] date dans le futur : 99 ligne(s) retirée(s)
[clients] doublons : 50 ligne(s) retirée(s)
[clients] nom manquant : 80 valeur(s) remplacée(s) par 'inconnu'
[clients] region manquant : 80 valeur(s) remplacée(s) par 'inconnu'
[clients] email manquant : 80 valeur(s) laissée(s) vide(s)
[paiements] doublons : 250 ligne(s) retirée(s)
[paiements] date dans le futur : 101 ligne(s) retirée(s)
[paiements] commande absente ou invalide : 148 ligne(s) retirée(s)
[paiements] montant différent de la commande (aberrant) : 48 ligne(s) retirée(s)
```

## Structure du code

| Fichier | Rôle |
|---|---|
| `src/config.py` | Lit et valide les réglages du `.env` |
| `src/generateur.py` | Fabrique les 7 tables |
| `src/defauts.py` | Injecte doublons, manquants, dates futures, montants en texte, outliers, noms spéciaux |
| `src/nettoyage.py` | Lecture sécurisée + corrections |
| `src/export.py` | Écrit CSV, JSON, Parquet |
| `src/schemas.py` | Colonnes attendues de chaque table |
| `src/erreurs.py` | Erreurs « attendues » avec messages clairs |
| `src/logger.py` | Journalisation |
| `src/main.py` | Chef d'orchestre |
| `tests/` | Tests du générateur, des défauts, du nettoyage et du pipeline complet |

## Tests

```bash
pytest
```

Ils vérifient les taux exacts de chaque défaut, que le nettoyage les corrige (y compris les
montants légitimes de plus de 1 M FCFA, conservés), que les noms spéciaux survivent, que
relancer ne change pas le résultat (idempotence), et qu'un fichier corrompu arrête le
script proprement.

## Mettre à l'épreuve

Corrompre un fichier et vérifier l'échec propre :

```bash
python -m src.main
echo "colonne_bizarre" > data/brut/commandes.csv
python -m src.main --nettoyage     # ARRÊT : Colonne(s) ['commande_id', ...] introuvable(s)
```

## Décisions

- Choix des formats : voir [`docs/decisions_formats.md`](docs/decisions_formats.md).