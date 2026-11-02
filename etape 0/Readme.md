# SenMarket — Étape 0 : le générateur de données

SenMarket est une marketplace sénégalaise fictive. Cette étape contient le générateur
qui fabrique ses données (clients, vendeurs, produits, commandes, lignes de commande,
paiements mobiles, avis, événements de navigation), les **abîme volontairement**,
puis les **nettoie**.

Pourquoi abîmer des données qu'on a soi-même générées ? Parce que les vraies données
sont toujours sales. Comme on contrôle les défauts, on peut vérifier que le nettoyage
les corrige tous, et même qu'il **retrouve les vraies valeurs**.

## Installation

À faire une seule fois, à la **racine du projet fil rouge** (l'environnement sert à toutes les étapes) :

```bash
python -m venv mon_env
source mon_env/bin/activate        # Windows : mon_env\Scripts\activate
pip install -r requirements.txt    # pandas, numpy, faker, python-dotenv, pyarrow, pytest
cp .env.example .env               # Windows : copy .env.example .env
```

## Utilisation

Toujours depuis le **dossier de l'étape** (`etape_0/`), avec `-m` (sinon : `ModuleNotFoundError: No module named 'src'`) :

```bash
cd etape_0
python -m src.main                 # génère les données brutes puis les nettoie
python -m src.main --nettoyage     # nettoie seulement les fichiers bruts existants
python -m pytest -q                # lance tous les tests (40 attendus)
```

Code de sortie : `0` si tout va bien, `1` en cas d'erreur attendue (message clair dans les logs).
Les volumes, la période et l'intensité des défauts se règlent dans `.env`
(de quelques milliers à plusieurs millions de lignes).

## Résultat

```
data/brut/     données avec défauts
data/propre/   données nettoyées
               chaque table en .csv, .json (une ligne par enregistrement) et .parquet
logs/          journal d'exécution (combien de lignes corrigées, et pourquoi)
```

8 tables dans chaque dossier : clients, vendeurs, produits, commandes, lignes_commande,
paiements, avis, evenements.

## Les défauts injectés (`src/defauts.py`)

Seules les tables **clients**, **commandes**, **paiements** et **lignes_commande** sont abîmées ;
vendeurs, produits, avis et événements restent intacts. Les taux se règlent dans le dictionnaire
`TAUX` en haut du fichier (valeurs pour `TAUX_DEFAUTS=0.05`), et sont calculés sur le nombre
de lignes de chaque table.

| Défaut | Taux | Table · colonne | Exemple |
|---|---|---|---|
| Doublons | 5 % | clients, commandes, paiements, lignes_commande | ligne recopiée à l'identique |
| Valeurs manquantes | 8 % **par colonne** | clients · `nom`, `email`, `region` ; lignes_commande · `prix_unitaire` | `NaN` |
| Dates dans le futur | 2 % | commandes · `date_commande`, paiements · `date_paiement` | 1 jour à 2 ans après `DATE_FIN` |
| Montants en texte | 3 % | commandes · `montant_total`, paiements · `montant`, lignes_commande · `montant_ligne` | `"17300.00 FCFA"` |
| Outliers | 1 % | mêmes colonnes que les montants en texte | `999999.99` |
| Noms avec caractères spéciaux | 2 % | clients · `nom` | `Éloïse Müller-Ødegård` |
| Quantités invalides | 2 % | lignes_commande · `quantite` | `0`, `-1` ou `-2` |

Détails de fabrication :
- Les montants en texte et les outliers sont tirés sur des lignes **différentes** (jamais `"999999.99 FCFA"`).
- Les noms spéciaux ne tombent jamais sur un nom déjà vidé.
- Les doublons sont injectés **en dernier** : ce sont des copies exactes de lignes déjà abîmées.
- Tout est reproductible : même `SEED`, mêmes défauts.
- `TAUX_DEFAUTS` du `.env` agit comme un **multiplicateur** : `0` n'abîme rien, `0.10` double tous les taux
  (plafond 0.5, refusé au-delà).

> Dans `data/brut/*.parquet`, une colonne mêlant nombres et texte (`montant_total`) est
> enregistrée **en texte**, car Parquet n'accepte qu'un type par colonne. Les `.csv` et
> `.json` bruts gardent le mélange.

## Le nettoyage (`src/nettoyage.py`)

Le nettoyage relit `data/brut/*.csv` (encodage `utf-8-sig`, qui accepte aussi les fichiers
Excel avec BOM) et corrige chaque défaut. Chaque correction est journalisée.

L'**ordre** compte, chaque étape s'appuie sur la précédente :
`clients` → `commandes` → `lignes_commande` → `recalculer_totaux` → `paiements`.

| Défaut | Traitement |
|---|---|
| Doublons | `drop_duplicates` sur l'identifiant de la table |
| Montants en texte | `"2 500,00 FCFA"` → `2500` (retire `FCFA`/`XOF`/`CFA`/`€`, espaces, virgule décimale) |
| Outliers `montant_ligne` | **recalculé** : `prix_unitaire × quantite` |
| Outliers `montant_total` | **recalculé** : somme des `montant_ligne` de la commande |
| Outliers `paiements.montant` | **aligné** sur le `montant_total` de la commande |
| `prix_unitaire` manquant | relu dans `produits` (le catalogue n'a pas de défauts) |
| Quantité invalide (≤ 0) | **retrouvée** par `montant_ligne / prix_unitaire` si le résultat est un entier plausible |
| Quantité ET montant abîmés | irrécupérable : **toute la commande** est retirée (sinon son total serait faux) |
| Commande sans date ou à date future | commande retirée (la vraie date est perdue) |
| Commande sans ligne valide | retirée au recalcul des totaux |
| Date de paiement manquante, future ou antérieure à la commande | **recréée** : date de la commande + délai médian observé |
| Paiement sans commande valide | retiré (orphelin) |
| Ligne de commande sans commande valide | retirée (orpheline) |
| `nom`, `region` manquants | client **gardé**, valeur remplacée par `"inconnu"` (sinon ses commandes deviennent orphelines) |
| `email` manquant | client gardé, email laissé **vide** (« inconnu » n'est pas un email) |
| Noms spéciaux | **conservés**. On normalise seulement l'Unicode (NFC), les espaces, et on répare le texte mal décodé (`Ã©` → `é`) |

Pourquoi **recalculer** plutôt que détecter les outliers ? Certaines commandes légitimes
atteignent déjà ~1,2 M FCFA (Électronique × 5) : `999999.99` n'est donc pas « hors plage »,
et une règle statistique (Q3 + 10 × IQR) le laisse passer. Or `montant_ligne`, `montant_total`
et `paiements.montant` sont des données **dérivées** : on les reconstruit, on ne les juge pas.
Résultat : l'outlier disparaît de lui-même, et le paiement sain d'une commande à outlier
n'est plus supprimé à tort.

Une marge d'un jour est accordée après `DATE_FIN` : un paiement fait quelques minutes après
une commande passée dans la dernière heure reste valide.

Les montants nettoyés sont des entiers (FCFA).

### Exemple de journal (extrait, `SEED=42`, réglages par défaut)

```
[paiements] commande absente ou invalide : 99 ligne(s) retirée(s)
[paiements] montant : 142 montant(s) en texte converti(s) en nombre
[paiements] montant : 47 valeur(s) alignée(s) sur la commande
[paiements] date_paiement impossible : 94 valeur(s) recréée(s) (commande + délai médian 0 days 00:30:29)
```

Le journal complet est dans `logs/senmarket.log`. Les chiffres varient avec la configuration.

### Exemple de résultat (réglages par défaut)

| Table | Brut | Propre |
|---|---|---|
| clients | 1050 | 1000 |
| commandes | 5250 | 4897 |
| lignes_commande | 15851 | 14790 |
| paiements | 4995 | 4659 |

Environ 98 % des commandes d'origine sont récupérées ; les pertes viennent surtout des dates
de commande dans le futur, qui sont irrécupérables.

## Structure du code

| Fichier | Rôle |
|---|---|
| `src/config.py` | Lit et valide les réglages du `.env` |
| `src/generateur.py` | Fabrique les 8 tables |
| `src/defauts.py` | Injecte doublons, manquants, dates futures, montants en texte, outliers, noms spéciaux, quantités invalides |
| `src/nettoyage.py` | Lecture sécurisée + corrections + recalcul des totaux |
| `src/export.py` | Écrit CSV, JSON, Parquet |
| `src/schemas.py` | Colonnes attendues de chaque table (le « contrat ») |
| `src/erreurs.py` | Erreurs « attendues » avec messages clairs |
| `src/logger.py` | Journalisation (écran + `logs/senmarket.log`) |
| `src/main.py` | Chef d'orchestre |
| `tests/` | Tests du générateur, des défauts, du nettoyage et du pipeline complet |

## Tests

```bash
python -m pytest -q
```

| Fichier | Ce qu'il vérifie |
|---|---|
| `test_generateur.py` | colonnes conformes au contrat, volumes, identifiants uniques, nombre **exact** de chaque défaut, `TAUX_DEFAUTS` appliqué, configuration invalide refusée |
| `test_nettoyage.py` | chaque règle sur de petits cas (outliers recalculés, quantités retrouvées, dates recréées), idempotence, fichiers abîmés |
| `test_main.py` | les 3 formats pour les 8 tables, relancer ne change pas le résultat, fichier corrompu = arrêt propre |
| `test_pipeline.py` | sur 3 000 commandes : aucun doublon, orphelin ou date future ; totaux cohérents ; et surtout les montants et quantités retrouvés sont **identiques aux données d'origine** |

Les noms spéciaux survivent au nettoyage, et les montants légitimes de plus de 1 M FCFA sont conservés.

## Mettre à l'épreuve

Corrompre un fichier et vérifier l'échec propre :

```bash
python -m src.main
echo "colonne_bizarre" > data/brut/commandes.csv
python -m src.main --nettoyage     # ARRÊT : Colonne(s) ['commande_id', ...] introuvable(s)
echo $?                            # 1
```

Relancer `python -m src.main` régénère tout (idempotent).

## Limites connues

- Une commande à date future est supprimée : sa vraie date est perdue.
- Les dates de paiement recréées sont une estimation (délai médian), pas la valeur d'origine.
- Le format `1,234.50` (virgule des milliers) n'est pas géré.
- Les CSV sont écrits en `utf-8` sans BOM : passe l'export en `utf-8-sig` pour les ouvrir dans Excel.
- Les défauts sont indépendants : une même ligne peut en cumuler plusieurs.

## Décisions

- Choix des formats : voir [`docs/decisions_formats.md`](docs/decisions_formats.md).
- Recalculer les données dérivées plutôt que les supprimer : voir « Le nettoyage » ci-dessus.