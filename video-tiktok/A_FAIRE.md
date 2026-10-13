# Vidéo promo PC Radar v2 — où on en est (13/10/2026)

Demande : vidéo plus longue (~47 s), 3D réaliste, fonctionnalités du site, voix off.

## Fait
- `src/three/Realiste.tsx` : modèles 3D réalistes (ventilateurs à pales courbes, carte graphique,
  ventirad cuivre/alu, RAM, carte mère texturée, boîtier verre trempé, alim, sol studio),
  studio (RoomEnvironment), post-traitement (Bloom, ACES, Vignette, DepthOfField optionnel),
  téléphone 3D dont l'écran affiche une capture du site qui défile (`Telephone ecran=... defilement=0..1`).
  Vérifiés en image fixe : composition `Essai3D` (src/Essai.tsx), images 0 (GPU), 1 (PC), 2 (téléphone).
- `voix.py` -> `public/voix/plan1..8.mp3` + `src/voix.json` (texte, mots avec début/fin en s).
  Voix edge-tts `fr-FR-HenriNeural` (+8 %). Durées : 4.46, 6.71, 2.30, 4.69, 7.41, 4.76, 6.40, 4.26 s.
- `public/ecrans/ecran1..6.jpg` : captures 860x4800 du site au format téléphone
  (1 accueil, 2 configurateur, 3 estimer-fps vide = ne pas utiliser, 4 fiche RTX 5060 avec courbe de prix
  vers 30-55 % de défilement, 5 guide 1080p avec FPS, 6 comparatifs).

## Reste à faire
1. `src/v2/Scenes.tsx` + composition `PcRadarPromo` (1080x1920, 30 i/s), un plan par fichier voix,
   durée = voix + ~0,6 s, voix posée à +6 images dans chaque plan (`<Sequence from={6}><Audio src={staticFile(...)}/>`).
   Plans : 1 accroche (gros plan GPU, flou de profondeur) ; 2 problème (ventirad / alim / GPU en colonne,
   étiquette rouge quand le mot « socket », « faible », « boîtier » est prononcé) ; 3 logo radar ;
   4 configurateur (téléphone ecran2 qui défile) ; 5 assistant IA (chat 2D : « Un PC pour Fortnite,
   1 000 € max » -> RX 9060 XT + Ryzen 5 5600XT, 978 €, ~110 FPS en 1080p) ; 6 prix (téléphone ecran4,
   courbe) ; 7 alerte e-mail (exemple) + FPS du guide 1080p à 842 € (Cyberpunk 80, Fortnite 80, CS2 210) ;
   8 appel à l'action (PC réel qui tourne, pcradar.tech, Gratuit).
2. Sous-titres animés mot à mot (voix.json), entre y=1250 et 1400 (zone utile TikTok).
3. Images fixes de contrôle, puis `npx remotion render src/index.ts PcRadarPromo out/pcradar-promo.mp4`.
   Sous Linux sans GPU : `Config.setChromiumOpenGlRenderer("swangle")` dans remotion.config.ts.
