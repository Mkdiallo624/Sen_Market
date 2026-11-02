"""Le « contrat » des données : quelles colonnes doit avoir chaque table.

Ce contrat sert à vérifier un fichier AVANT de le traiter. Si quelqu'un
supprime une colonne, on le détecte immédiatement avec un message clair.
Les clés DOIVENT être identiques aux noms de fichiers (data/brut/<clé>.csv).
"""

COLONNES = {
    "clients": ["client_id", "nom", "telephone", "email", "region"],
    "vendeurs": ["vendeur_id", "nom_boutique", "telephone", "region"],
    "produits": ["produit_id", "vendeur_id", "nom", "categorie", "prix", "stock", "attributs"],
    "commandes": ["commande_id", "client_id", "statut", "region_livraison",
                  "date_commande", "montant_total"],
    "lignes_commande": ["ligne_id", "commande_id", "produit_id", "quantite",
                        "prix_unitaire", "montant_ligne"],
    "paiements": ["paiement_id", "commande_id", "operateur", "montant", "statut", "date_paiement"],
    "avis": ["avis_id", "produit_id", "client_id", "note", "commentaire", "date_avis"],
    "evenements": ["evenement_id", "client_id", "produit_id", "type", "appareil", "horodatage"],
}

# Colonnes à lire comme des dates (un CSV ne stocke que du texte)
COLONNES_DATES = {
    "clients": [],
    "vendeurs": [],
    "produits": [],
    "lignes_commande": [],
    "commandes": ["date_commande"],
    "paiements": ["date_paiement"],
    "avis": ["date_avis"],
    "evenements": ["horodatage"],
}

# Sécurité : les deux dictionnaires doivent décrire exactement les mêmes tables.
assert COLONNES.keys() == COLONNES_DATES.keys(), "schemas.py : clés incohérentes"