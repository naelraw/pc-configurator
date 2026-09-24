// Devine la catégorie PC Radar à partir du fil d'Ariane et/ou du titre
// Amazon — même esprit que guess_categorie_from_amazon() côté serveur
// (main.py), en plus simple : le fil d'Ariane Amazon donne sa PROPRE
// catégorisation ("Processeurs", "Cartes graphiques"...), un signal plus
// fiable que de deviner depuis le titre, donc vérifié en premier.
// Utilisé à la fois par popup.js (via chrome.scripting.executeScript) et
// content.js (lecture directe du DOM de la page).
function pcradarGuessCategorie(breadcrumbText, titleText) {
  const breadcrumbRules = [
    [/processeur/i, 'CPU'],
    [/carte[s]?\s*graphique/i, 'GPU'],
    [/carte[s]?\s*m[eè]re/i, 'Carte mère'],
    [/m[eé]moire|barrette/i, 'RAM'],
    [/bo[iî]tier/i, 'Boîtier'],
    [/alimentation/i, 'Alimentation'],
    [/disque|ssd|stockage|nvme/i, 'Stockage'],
    [/ventilateur|refroidiss|watercooling|ventirad/i, 'Refroidissement'],
  ];
  const titleRules = [
    [/processeur|ryzen|threadripper|core\s*i[3579]|core\s*ultra/i, 'CPU'],
    [/carte\s*graphique|geforce|radeon\s*rx|\brtx\b|\bgtx\b/i, 'GPU'],
    [/carte\s*m[eè]re|motherboard/i, 'Carte mère'],
    [/m[eé]moire\s*vive|barrette|ram\s*ddr|\bdimm\b|\bsodimm\b/i, 'RAM'],
    [/\bssd\b|disque\s*dur|\bnvme\b|\bhdd\b/i, 'Stockage'],
    [/alimentation|80\s*plus|\bpsu\b/i, 'Alimentation'],
    [/ventirad|watercooling|\baio\b|refroidisseur/i, 'Refroidissement'],
    [/bo[iî]tier/i, 'Boîtier'],
  ];

  const breadcrumb = breadcrumbText || '';
  for (const [re, categorie] of breadcrumbRules) {
    if (re.test(breadcrumb)) return categorie;
  }

  const title = titleText || '';
  for (const [re, categorie] of titleRules) {
    if (re.test(title)) return categorie;
  }

  return 'Accessoire';
}

// "319,99 €" / "1 234,56 €" / "$319.99" -> nombre. Utilisé pour lire un prix
// déjà affiché sur la page SANS attendre Bright Data (voir
// pcradarExtractQuickData ci-dessous).
function pcradarParsePrice(text) {
  if (!text) return null;
  const cleaned = String(text).replace(/[^\d,.\s]/g, '').trim();
  const normalized = cleaned.replace(/\s/g, '').replace(',', '.');
  const value = parseFloat(normalized);
  return Number.isFinite(value) ? value : null;
}

// Lit nom/prix/image directement dans le DOM Amazon (fiche produit ou
// carte de résultat — mêmes sélecteurs Amazon dans les deux cas) : permet
// un ajout catalogue instantané, l'enrichissement précis (specs, nom
// nettoyé par IA) venant compléter la fiche après coup en arrière-plan.
function pcradarExtractQuickData(root) {
  const scope = root || document;
  const nomEl = scope.querySelector('#productTitle') || scope.querySelector('h2');
  const nom = nomEl ? nomEl.innerText.trim() : null;
  const priceEl = scope.querySelector('#corePrice_feature_div .a-price .a-offscreen')
    || scope.querySelector('.a-price .a-offscreen');
  const prix = pcradarParsePrice(priceEl ? priceEl.textContent : null);
  const imgEl = scope.querySelector('#landingImage')
    || scope.querySelector('#imgTagWrapperId img')
    || scope.querySelector('img.s-image')
    || scope.querySelector('img');
  const image_url = imgEl ? imgEl.src : null;
  return { nom, prix, image_url };
}

// Node/extension contexts partagent ce fichier tel quel (pas de module
// bundler ici) : on l'expose aussi explicitement sur window par sécurité
// selon l'ordre de chargement des scripts.
if (typeof window !== 'undefined') {
  window.pcradarGuessCategorie = pcradarGuessCategorie;
  window.pcradarParsePrice = pcradarParsePrice;
  window.pcradarExtractQuickData = pcradarExtractQuickData;
}
