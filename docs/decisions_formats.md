# Fiche de décision — Quel format de fichier pour quel usage ?

| Critère | CSV | JSON (lignes) | Parquet |
|---|---|---|---|
| Lisible par un humain | Oui (Excel, éditeur) | Oui | Non (binaire) |
| Taille sur disque | Grande | La plus grande | La plus petite (compressé) |
| Vitesse d'analyse | Lente | Lente | Très rapide |
| Types conservés (dates, nombres) | Non (tout est texte) | Partiel | Oui |
| Structures imbriquées | Non | Oui | Oui |
| Support Spark / dbt / cloud | Oui | Oui | Natif, format de référence |

## Décision

- **CSV** : échange avec des personnes ou des outils simples (Excel), petits fichiers,
  et ce que nous *ingérons* depuis l'extérieur. C'est notre format d'entrée du nettoyage.
- **JSON (une ligne = un enregistrement)** : données d'API et d'événements, documents
  à structure variable (futur catalogue MongoDB, messages Kafka).
- **Parquet** : tout ce qui est stocké pour être *analysé* (lakehouse, Spark, Athena).
  C'est le format cible des étapes 2 à 4.

## Ce que j'ai observé (à compléter avec vos mesures)

Lancez avec `NB_COMMANDES=1000000` puis comparez `ls -lh data/propre/commandes.*` :
notez la taille de chaque format et le temps de lecture avec Pandas.