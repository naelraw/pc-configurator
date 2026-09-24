# Recherche AliExpress (feed Awin)

Outil de bureau local pour chercher un produit dans le feed AliExpress
(export Awin, ~427 000 produits) sans repasser par Claude à chaque fois.

## Installation (une fois)

```bash
cd pc-configurator/aliexpress_tool
pip install -r requirements.txt
```

## Utilisation

```bash
python app.py
```

1. **Charger le feed** — lit `feed.csv` (~320 Mo, prend quelques secondes).
2. Tape un ou plusieurs mots-clés (ex: `ventilateur rgb`, `boitier pc`,
   `carte graphique`) — tous les mots doivent apparaître dans le nom, la
   catégorie ou la marque du produit.
3. Clique un résultat pour voir l'aperçu (image, prix, marque, stock).
4. **Copier le lien d'affiliation** ou **Copier tout (nom + prix + lien)**,
   puis colle dans l'admin du site : édite le composant concerné → ajoute
   une ligne de prix → vendeur = `AliExpress` (casse exacte) → colle le
   prix et le lien.

## Limites à connaître

- Le feed AliExpress n'a pas d'équivalent à un ASIN Amazon propre : noms de
  marque et descriptions sont en vrac, donc pas de récupération automatique
  fiable façon "coller un lien → tout se remplit" comme pour Amazon. Cet
  outil sert à *chercher*, pas à importer automatiquement.
- Le feed est une photo à un instant donné (téléchargée manuellement depuis
  Awin) — pas de mise à jour en temps réel des prix/stock.

## Rafraîchir le feed

Sur [ui.awin.com](https://ui.awin.com) : Toolbox → Create-a-Feed →
"Configure an advertiser-based feed" → sélectionne AliExpress → génère à
nouveau le feed "Bestsellers CSS" (mêmes colonnes que la première fois) →
remplace `feed.csv` dans ce dossier par le nouveau fichier téléchargé.
