# Détourage local (BiRefNet)

Outil de bureau qui tourne sur ton PC (jamais sur le VM Oracle) pour détourer
les images de composants avec BiRefNet — le modèle IA qui donnait la
meilleure qualité en test, mais qui était trop lourd/lent pour le petit VM
ARM. Sur ton PC (surtout avec un GPU), il tourne normalement.

## Installation (une fois)

```bash
cd pc-configurator/local_bg_tool
pip install -r requirements.txt
```

## Utilisation

```bash
python app.py
```

1. **Charger les composants** — liste tous les composants ayant une image.
2. Sélectionne une ou plusieurs lignes (le champ *Filtre* permet de chercher
   par nom).
3. **Détourer la sélection** — lance BiRefNet sur chaque image sélectionnée.
   Le tout premier détourage télécharge le modèle (~1 Go, une seule fois,
   mis en cache dans `~/.u2net/`) — patience la première fois seulement.
4. Clique sur une ligne pour voir l'aperçu avant/après.
5. **Enregistrer sur le site** — écrit directement les images détourées
   dans la base de production (Turso). Demande confirmation avant d'écrire.

## GPU (accélération, optionnel)

Par défaut `onnxruntime` tourne sur CPU (fonctionne, juste plus lent — BiRefNet
prend quelques secondes par image sur CPU). Pour l'accélération GPU :

- **NVIDIA** : `pip uninstall onnxruntime` puis `pip install onnxruntime-gpu`
  (nécessite CUDA installé).
- **AMD / Intel / autre** (pas de CUDA) : `pip uninstall onnxruntime` puis
  `pip install onnxruntime-directml` — fonctionne sur toute carte compatible
  DirectX 12 sous Windows, sans CUDA. C'est l'équivalent pratique de
  "ncnn-vulkan" pour ce modèle (rembg utilise onnxruntime, pas ncnn — il
  n'existe pas de portage ncnn-vulkan public de BiRefNet à ce jour).

Aucun changement de code nécessaire : rembg détecte automatiquement le
meilleur provider onnxruntime disponible.

## Notes

- Ce dossier n'est PAS déployé sur le VM — c'est un outil pour ton poste
  uniquement. Le `.env` du projet (`pc-configurator/.env`) doit exister un
  niveau au-dessus (déjà le cas si tu lances depuis le repo).
- Le bouton "Détourer l'image" existant dans l'admin web reste disponible
  pour un détourage ponctuel sans passer par cet outil.
