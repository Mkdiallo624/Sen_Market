"""Le générateur : fabrique de fausses données réalistes pour SenMarket.

On utilise NumPy (rapide, adapté aux millions de lignes) et Faker
(pour les détails « réalistes », ici les domaines d'e-mail).
Une même SEED donne toujours exactement les mêmes données.
"""
import json
import logging
import unicodedata

import numpy as np
import pandas as pd
from faker import Faker

from src.config import Config

logger = logging.getLogger(__name__)

PRENOMS = ["Awa", "Moussa", "Fatou", "Mamadou", "Aminata", "Ibrahima", "Khadija",
           "Cheikh", "Ndèye", "Ousmane", "Mariama", "Abdoulaye", "Sokhna", "Modou",
           "Aïssatou", "Pape", "Rokhaya", "Samba", "Binta", "Alioune"]
NOMS = ["Diop", "Ndiaye", "Fall", "Sow", "Ba", "Gueye", "Diallo", "Sarr", "Faye",
        "Mbaye", "Cissé", "Thiam", "Sy", "Diouf", "Kane", "Seck", "Niang", "Lô",
        "Badji", "Ndao"]
REGIONS = ["Dakar", "Thiès", "Diourbel", "Fatick", "Kaolack", "Kaffrine", "Kédougou",
           "Kolda", "Louga", "Matam", "Saint-Louis", "Sédhiou", "Tambacounda", "Ziguinchor"]
# Dakar concentre l'essentiel de l'activité : on le reflète dans les probabilités
POIDS_REGIONS = np.array([0.40] + [0.60 / 13] * 13)

# catégorie -> (noms de produits, fourchette de prix en FCFA)
CATALOGUE = {
    "Alimentation": (["Riz brisé 5kg", "Huile d'arachide 1L", "Thé Touba 500g",
                      "Bissap séché 250g", "Mil local 2kg"], (500, 15000)),
    "Mode": (["Boubou brodé", "Sandales en cuir", "Robe wax", "Sac en pagne",
              "Chemise bazin"], (3000, 60000)),
    "Électronique": (["Smartphone", "Écouteurs sans fil", "Chargeur rapide",
                      "Enceinte Bluetooth", "Batterie externe"], (5000, 250000)),
    "Maison": (["Seau en plastique", "Natte tressée", "Théière émaillée",
                "Ventilateur", "Set de verres"], (1000, 40000)),
    "Beauté": (["Beurre de karité", "Savon noir", "Huile de baobab",
                "Parfum Thiouraye", "Henné naturel"], (500, 20000)),
}
OPERATEURS = ["Wave", "Orange Money", "Free Money", "Carte bancaire"]
PHRASES_AVIS = {
    1: ["Très déçu, produit non conforme.", "Je ne recommande pas du tout."],
    2: ["Qualité moyenne, livraison trop longue.", "Peut mieux faire."],
    3: ["Correct, sans plus.", "Conforme à la description."],
    4: ["Bon produit, livraison rapide.", "Satisfait de mon achat."],
    5: ["Excellent, je recommande !", "Parfait, merci au vendeur."],
}


def _sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()


def _dates_aleatoires(rng, n: int, date_fin: str, jours: int = 365) -> pd.DatetimeIndex:
    """n dates/heures tirées au hasard dans les `jours` précédant date_fin."""
    debut = pd.Timestamp(date_fin) - pd.Timedelta(days=jours)
    secondes = rng.integers(0, jours * 24 * 3600, size=n)
    return debut + pd.to_timedelta(secondes, unit="s")


def _telephones(rng, n: int) -> list[str]:
    prefixes = rng.choice(["70", "75", "76", "77", "78"], n)
    a, b, c = (rng.integers(lo, hi, n) for lo, hi in [(100, 1000), (10, 100), (10, 100)])
    return [f"+221 {p} {x} {y} {z}" for p, x, y, z in zip(prefixes, a, b, c)]


def generer_clients(rng, fake: Faker, cfg: Config) -> pd.DataFrame:
    n = cfg.nb_clients
    ids = np.arange(1, n + 1)
    prenoms = rng.choice(PRENOMS, n)
    noms = rng.choice(NOMS, n)
    domaines = np.array(sorted({fake.free_email_domain() for _ in range(30)}))
    choix_domaines = rng.choice(domaines, n)
    emails = [f"{_sans_accents(p).lower()}.{_sans_accents(nm).lower()}{i}@{d}"
              for p, nm, i, d in zip(prenoms, noms, ids, choix_domaines)]
    return pd.DataFrame({
        "client_id": ids,
        "nom": [f"{p} {nm}" for p, nm in zip(prenoms, noms)],
        "telephone": _telephones(rng, n),
        "email": emails,
        "region": rng.choice(REGIONS, n, p=POIDS_REGIONS),
        "date_inscription": _dates_aleatoires(rng, n, cfg.date_fin),
    })


def generer_vendeurs(rng, cfg: Config) -> pd.DataFrame:
    n = cfg.nb_vendeurs
    return pd.DataFrame({
        "vendeur_id": np.arange(1, n + 1),
        "nom_boutique": [f"Boutique {nom} {i}" for i, nom in enumerate(rng.choice(NOMS, n), 1)],
        "telephone": _telephones(rng, n),
        "region": rng.choice(REGIONS, n, p=POIDS_REGIONS),
    })


def _attributs(rng, categorie: str) -> dict:
    """Chaque catégorie a ses propres attributs : c'est ce qui rendra
    MongoDB (schéma souple) pertinent à l'étape 1."""
    if categorie == "Alimentation":
        return {"poids_kg": float(rng.choice([0.25, 0.5, 1, 2, 5])),
                "origine": str(rng.choice(["Sénégal", "Importé"]))}
    if categorie == "Mode":
        return {"taille": str(rng.choice(["S", "M", "L", "XL"])),
                "couleur": str(rng.choice(["bleu", "rouge", "blanc", "jaune"]))}
    if categorie == "Électronique":
        return {"marque": str(rng.choice(["Tecno", "Samsung", "Infinix", "Itel"])),
                "garantie_mois": int(rng.choice([6, 12, 24]))}
    if categorie == "Maison":
        return {"matiere": str(rng.choice(["plastique", "métal", "fibre", "verre"])),
                "couleur": str(rng.choice(["vert", "rouge", "blanc"]))}
    return {"contenance_ml": int(rng.choice([50, 100, 250])),
            "naturel": bool(rng.integers(0, 2))}


def generer_produits(rng, cfg: Config) -> pd.DataFrame:
    lignes = []
    categories = list(CATALOGUE)
    for pid in range(1, cfg.nb_produits + 1):
        cat = categories[rng.integers(len(categories))]
        noms, (pmin, pmax) = CATALOGUE[cat]
        prix = int(rng.integers(pmin, pmax) // 50 * 50) or 50  # arrondi aux 50 FCFA
        lignes.append({
            "produit_id": pid,
            "vendeur_id": int(rng.integers(1, cfg.nb_vendeurs + 1)),
            "nom": str(rng.choice(noms)),
            "categorie": cat,
            "prix": prix,
            "stock": int(rng.integers(0, 500)),
            # Stocké en texte JSON : un seul format qui marche en CSV, JSON et Parquet
            "attributs": json.dumps(_attributs(rng, cat), ensure_ascii=False),
        })
    return pd.DataFrame(lignes)


def generer_commandes(rng, cfg: Config, produits: pd.DataFrame) -> pd.DataFrame:
    n = cfg.nb_commandes
    produit_ids = rng.integers(1, cfg.nb_produits + 1, n)
    quantites = rng.integers(1, 6, n)
    prix = produits["prix"].to_numpy()[produit_ids - 1]  # produit_id = position + 1
    return pd.DataFrame({
        "commande_id": np.arange(1, n + 1),
        "client_id": rng.integers(1, cfg.nb_clients + 1, n),
        "produit_id": produit_ids,
        "quantite": quantites,
        "montant_total": prix * quantites,
        "statut": rng.choice(["livree", "en_cours", "annulee"], n, p=[0.80, 0.15, 0.05]),
        "region_livraison": rng.choice(REGIONS, n, p=POIDS_REGIONS),
        "date_commande": _dates_aleatoires(rng, n, cfg.date_fin),
    })


def generer_paiements(rng, commandes: pd.DataFrame) -> pd.DataFrame:
    """Un paiement par commande, quelques minutes après la commande."""
    n = len(commandes)
    delai = pd.to_timedelta(rng.integers(10, 3600, n), unit="s")
    return pd.DataFrame({
        "paiement_id": np.arange(1, n + 1),
        "commande_id": commandes["commande_id"].to_numpy(),
        "operateur": rng.choice(OPERATEURS, n, p=[0.45, 0.35, 0.10, 0.10]),
        "montant": commandes["montant_total"].to_numpy(),
        "statut": rng.choice(["reussi", "echoue"], n, p=[0.93, 0.07]),
        "date_paiement": commandes["date_commande"].to_numpy() + delai.to_numpy(),
    })


def generer_avis(rng, cfg: Config) -> pd.DataFrame:
    n = cfg.nb_avis
    notes = rng.choice([1, 2, 3, 4, 5], n, p=[0.05, 0.05, 0.15, 0.35, 0.40])
    commentaires = np.empty(n, dtype=object)
    for note, phrases in PHRASES_AVIS.items():
        masque = notes == note
        commentaires[masque] = rng.choice(phrases, masque.sum())
    return pd.DataFrame({
        "avis_id": np.arange(1, n + 1),
        "produit_id": rng.integers(1, cfg.nb_produits + 1, n),
        "client_id": rng.integers(1, cfg.nb_clients + 1, n),
        "note": notes,
        "commentaire": commentaires,
        "date_avis": _dates_aleatoires(rng, n, cfg.date_fin),
    })


def generer_evenements(rng, cfg: Config) -> pd.DataFrame:
    """Le « parcours de navigation » : vues, clics, ajouts au panier."""
    n = cfg.nb_evenements
    return pd.DataFrame({
        "evenement_id": np.arange(1, n + 1),
        "client_id": rng.integers(1, cfg.nb_clients + 1, n),
        "produit_id": rng.integers(1, cfg.nb_produits + 1, n),
        "type": rng.choice(["vue", "clic", "ajout_panier"], n, p=[0.70, 0.20, 0.10]),
        "appareil": rng.choice(["mobile", "ordinateur"], n, p=[0.85, 0.15]),
        "horodatage": _dates_aleatoires(rng, n, cfg.date_fin),
    })


def generer_tout(cfg: Config) -> dict[str, pd.DataFrame]:
    """Génère les 7 tables de SenMarket (propres, sans défauts)."""
    rng = np.random.default_rng(cfg.seed)
    Faker.seed(cfg.seed)
    fake = Faker("fr_FR")

    produits = generer_produits(rng, cfg)
    commandes = generer_commandes(rng, cfg, produits)
    tables = {
        "clients": generer_clients(rng, fake, cfg),
        "vendeurs": generer_vendeurs(rng, cfg),
        "produits": produits,
        "commandes": commandes,
        "paiements": generer_paiements(rng, commandes),
        "avis": generer_avis(rng, cfg),
        "evenements": generer_evenements(rng, cfg),
    }
    for nom, df in tables.items():
        logger.info("Table %-10s générée : %d lignes", nom, len(df))
    return tables