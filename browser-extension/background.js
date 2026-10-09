const DEFAULT_SITE_URL = 'https://pcradar.tech';

function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['siteUrl', 'adminSecret'], (result) => {
      resolve({
        siteUrl: (result.siteUrl || DEFAULT_SITE_URL).replace(/\/$/, ''),
        adminSecret: result.adminSecret || '',
      });
    });
  });
}

function saveSettings(siteUrl, adminSecret) {
  return new Promise((resolve) => {
    chrome.storage.local.set(
      { siteUrl: (siteUrl || DEFAULT_SITE_URL).replace(/\/$/, ''), adminSecret: adminSecret || '' },
      resolve
    );
  });
}

// Lookup ciblé côté serveur (/api/components/by-asin/{asin}) plutôt que de
// télécharger tout le catalogue pour vérifier un seul ASIN — reste rapide
// même quand le catalogue grossit. Résultat mis en cache en mémoire (le
// service worker vit le temps de la session de navigation) : évite de
// refaire l'appel si le même ASIN est revérifié (popup ouvert après le
// panneau injecté, par ex.) dans la même minute.
const asinCache = new Map();
const ASIN_CACHE_TTL_MS = 60_000;

async function checkAsin(asin) {
  const key = asin.toUpperCase();
  const cached = asinCache.get(key);
  if (cached && Date.now() - cached.at < ASIN_CACHE_TTL_MS) {
    return cached.result;
  }

  const settings = await getSettings();
  const res = await fetch(settings.siteUrl + '/api/components/by-asin/' + encodeURIComponent(key));
  if (!res.ok) throw new Error('Vérification impossible (' + res.status + ')');
  const result = await res.json();
  asinCache.set(key, { result, at: Date.now() });
  return result;
}

async function fetchAsinInfo(asin, categorie) {
  const settings = await getSettings();
  if (!settings.adminSecret) throw new Error('NO_SECRET');
  const res = await fetch(settings.siteUrl + '/api/admin/fetch-asin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
    body: JSON.stringify({ asin, categorie }),
  });
  const data = await res.json();
  if (!res.ok || data.status !== 'ok') {
    throw new Error(data.detail || data.message || ('Erreur ' + res.status));
  }
  return data;
}

async function addComponent(asin, categorie, fetched) {
  const settings = await getSettings();
  if (!settings.adminSecret) throw new Error('NO_SECRET');

  const prix = fetched.prix;
  const lien = fetched.lien;
  const prixMarche = (prix != null && lien)
    ? [{ vendeur: 'Amazon', prix, lien, date_releve: new Date().toISOString().slice(0, 10) }]
    : [];

  const payload = {
    categorie,
    nom: fetched.nom || ('Composant (ASIN ' + asin + ')'),
    prix_indicatif: prix != null ? prix : 0,
    specs: fetched.specs || {},
    prix_marche: prixMarche,
    image_url: fetched.image_url,
    asin,
    caracteristiques_amazon: fetched.caracteristiques_amazon || [],
    description: fetched.description,
  };

  const res = await fetch(settings.siteUrl + '/api/admin/components', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
    body: JSON.stringify({ components: [payload] }),
  });
  const data = await res.json();
  if (!res.ok || data.status !== 'ok') {
    throw new Error(data.message || ('Erreur ' + res.status));
  }
  asinCache.delete(asin.toUpperCase()); // le statut "déjà catalogué" vient de changer
  return data;
}

// Enchaîne récupération + enregistrement en un seul aller-retour depuis
// content.js/popup.js — évite l'étape "aperçu, cliquer pour confirmer" :
// l'utilisateur voit un seul temps de chargement plutôt que deux (récupérer
// PUIS valider), pour un flux qui parait nettement plus rapide même si le
// temps serveur (Bright Data + IA) ne change pas.
async function fetchAndAdd(asin, categorie) {
  const fetched = await fetchAsinInfo(asin, categorie);
  await addComponent(asin, categorie, fetched);
  const status = await checkAsin(asin); // pour récupérer l'id, utile au bouton "Retirer"
  return { fetched, componentId: status.exists ? status.component.id : null };
}

// Enregistre immédiatement le composant avec les infos déjà visibles sur la
// page Amazon (nom, prix, image — extraites côté content.js/popup.js, sans
// appel réseau), puis lance l'enrichissement complet (Bright Data + IA) en
// arrière-plan SANS le faire attendre : Bright Data seul prend de 4 à 40s
// selon les cas (mesuré en prod), largement le plus gros poste de temps du
// flux complet — le contourner pour l'ajout initial est ce qui fait
// vraiment la différence de rapidité perçue, pas juste fusionner des clics.
async function quickAdd(asin, categorie, quickData) {
  const fetched = {
    nom: quickData.nom || ('Composant (ASIN ' + asin + ')'),
    prix: quickData.prix,
    lien: 'https://www.amazon.fr/dp/' + asin,
    image_url: quickData.image_url,
    specs: {},
    caracteristiques_amazon: [],
    description: null,
  };
  await addComponent(asin, categorie, fetched);
  const status = await checkAsin(asin);
  const componentId = status.exists ? status.component.id : null;

  if (componentId) {
    enrichComponent(asin, categorie, componentId).catch((e) => {
      console.warn('[PC Radar] Enrichissement en arrière-plan échoué pour', asin, e.message);
    });
  }

  return { fetched, componentId };
}

// Remplace la fiche rapide par les données complètes Bright Data (specs
// précises, nom nettoyé par IA) une fois prêtes — par id plutôt que par
// nom+catégorie pour ne jamais créer de doublon si le nom nettoyé diffère
// du titre brut utilisé par quickAdd.
async function enrichComponent(asin, categorie, componentId) {
  const settings = await getSettings();
  const enriched = await fetchAsinInfo(asin, categorie);

  const prix = enriched.prix;
  const lien = enriched.lien;
  const prixMarche = (prix != null && lien)
    ? [{ vendeur: 'Amazon', prix, lien, date_releve: new Date().toISOString().slice(0, 10) }]
    : [];

  const payload = {
    categorie,
    nom: enriched.nom || ('Composant (ASIN ' + asin + ')'),
    prix_indicatif: prix != null ? prix : 0,
    specs: enriched.specs || {},
    prix_marche: prixMarche,
    image_url: enriched.image_url,
    asin,
    caracteristiques_amazon: enriched.caracteristiques_amazon || [],
    description: enriched.description,
  };

  const res = await fetch(settings.siteUrl + '/api/admin/components/' + componentId, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || data.status === 'error') {
    throw new Error(data.message || ('Erreur ' + res.status));
  }
  asinCache.delete(asin.toUpperCase());
}

async function removeComponent(componentId, asin) {
  const settings = await getSettings();
  if (!settings.adminSecret) throw new Error('NO_SECRET');
  const res = await fetch(settings.siteUrl + '/api/admin/components/' + componentId, {
    method: 'DELETE',
    headers: { 'X-Admin-Secret': settings.adminSecret },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.message || data.detail || ('Erreur ' + res.status));
  }
  if (asin) asinCache.delete(asin.toUpperCase());
  return data;
}

// Produits déjà catalogués qui ressemblent au produit Amazon affiché (autre
// annonce du même modèle, autre couleur/capacité) : évite d'ajouter un doublon.
// Réservé à l'admin (clé requise) ; sans clé, simplement aucun résultat.
async function similarProducts(titre, categorie) {
  const settings = await getSettings();
  if (!settings.adminSecret || !titre) return { proches: [] };
  const url = settings.siteUrl + '/api/admin/produits-proches?titre=' + encodeURIComponent(titre)
    + '&categorie=' + encodeURIComponent(categorie || '');
  const res = await fetch(url, { headers: { 'X-Admin-Secret': settings.adminSecret } });
  if (!res.ok) return { proches: [] };
  return res.json();
}

// Page de résultats Amazon : état de tous les produits affichés en une seule
// requête (au catalogue ou non, prix du catalogue, produit proche...).
async function analysePage(items) {
  const settings = await getSettings();
  if (!settings.adminSecret) throw new Error('NO_SECRET');
  const res = await fetch(settings.siteUrl + '/api/admin/analyse-page', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
    body: JSON.stringify({ items }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(res.status === 401 ? 'Clé admin refusée' : (data.detail || ('Erreur ' + res.status)));
  return data.resultats || {};
}

// Met à jour le prix Amazon d'un composant avec celui lu sur la page produit.
async function updatePrice(componentId, prix, asin) {
  const settings = await getSettings();
  if (!settings.adminSecret) throw new Error('NO_SECRET');
  const res = await fetch(settings.siteUrl + '/api/admin/components/' + componentId + '/prix-amazon', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
    body: JSON.stringify({ prix }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || ('Erreur ' + res.status));
  if (asin) asinCache.delete(asin.toUpperCase());
  return data;
}

// ---------------------------------------------------------------------------
// Relevé automatique des prix (interrupteur dans la fenêtre de l'extension).
// Toutes les 30 s, tant que Chrome est ouvert : le site donne la fiche la plus
// urgente, l'extension ouvre sa page Amazon en arrière-plan (sans cookies, donc
// sans lien avec ton compte Amazon) et renvoie au site la zone du prix et de la
// disponibilité. Vérification « robot » d'Amazon : pause d'une heure, jamais
// de contournement. Au plus RELEVE_MAX_PAR_JOUR fiches par jour.
// ---------------------------------------------------------------------------
const RELEVE_ALARME = 'pcr-releve-prix';
const RELEVE_MAX_PAR_JOUR = 800;
const RELEVE_PAUSE_BLOCAGE_MS = 60 * 60 * 1000;

function aujourdhui() {
  return new Date().toISOString().slice(0, 10);
}

function extraitAmazon(html) {
  // Seulement ce dont le site a besoin : titre, zone du prix, disponibilité.
  const morceaux = [];
  const bloc = (repere, longueur) => {
    const i = html.indexOf(repere);
    if (i >= 0) morceaux.push(html.slice(i, i + longueur));
  };
  bloc('id="productTitle"', 600);
  bloc('id="corePriceDisplay_desktop_feature_div"', 8000);
  bloc('id="availability"', 2000);
  if (html.includes('validateCaptcha')) morceaux.push('validateCaptcha');
  return morceaux.join('\n');
}

async function releveEtat() {
  const st = await chrome.storage.local.get(['releveActif', 'relevePauseJusqua', 'releveJour', 'releveCompte', 'releveDernier']);
  if (st.releveJour !== aujourdhui()) { st.releveJour = aujourdhui(); st.releveCompte = 0; }
  return st;
}

async function releverUnPrix() {
  const st = await releveEtat();
  if (!st.releveActif) return;
  if (Date.now() < (st.relevePauseJusqua || 0)) return;
  if ((st.releveCompte || 0) >= RELEVE_MAX_PAR_JOUR) return;
  const settings = await getSettings();
  if (!settings.adminSecret) return;
  const entete = { 'X-Admin-Secret': settings.adminSecret };
  const res = await fetch(settings.siteUrl + '/api/admin/prix-a-relire?n=1&origine=extension', { headers: entete });
  if (!res.ok) { await chrome.storage.local.set({ releveDernier: 'Site : erreur ' + res.status }); return; }
  const fiche = ((await res.json()).fiches || [])[0];
  if (!fiche) return;
  const page = await fetch('https://www.amazon.fr/dp/' + fiche.asin + '?th=1&psc=1', { credentials: 'omit' });
  const html = await page.text();
  const envoi = await fetch(settings.siteUrl + '/api/admin/prix-extension', {
    method: 'POST',
    headers: Object.assign({ 'Content-Type': 'application/json' }, entete),
    body: JSON.stringify({ id: fiche.id, asin: fiche.asin, extrait: extraitAmazon(html), origine: 'extension' }),
  });
  const r = await envoi.json().catch(() => ({}));
  const maj = { releveJour: st.releveJour, releveCompte: (st.releveCompte || 0) + 1 };
  if (r.resultat === 'bloque') {
    maj.relevePauseJusqua = Date.now() + RELEVE_PAUSE_BLOCAGE_MS;
    maj.releveDernier = 'Amazon demande une vérification : pause d\'une heure.';
  } else if (r.resultat === 'lu') {
    maj.releveDernier = fiche.nom + ' : ' + String(r.prix).replace('.', ',') + ' €';
  } else if (r.resultat === 'ignore') {
    maj.releveDernier = fiche.nom + ' : prix inhabituel, en attente de confirmation.';
  } else {
    maj.releveDernier = fiche.nom + ' : pas de prix sur la page.';
  }
  await chrome.storage.local.set(maj);
}

function programmerReleve() {
  chrome.alarms.get(RELEVE_ALARME, (alarme) => {
    if (!alarme) chrome.alarms.create(RELEVE_ALARME, { periodInMinutes: 0.5 });
  });
}
chrome.runtime.onInstalled.addListener(programmerReleve);
chrome.runtime.onStartup.addListener(programmerReleve);
programmerReleve();
chrome.alarms.onAlarm.addListener((alarme) => {
  if (alarme.name === RELEVE_ALARME) {
    releverUnPrix().catch((e) => chrome.storage.local.set({ releveDernier: 'Erreur : ' + e.message }));
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message.type) {
        case 'GET_SETTINGS':
          sendResponse({ ok: true, data: await getSettings() });
          break;
        case 'SAVE_SETTINGS':
          await saveSettings(message.siteUrl, message.adminSecret);
          sendResponse({ ok: true });
          break;
        case 'CHECK_ASIN':
          sendResponse({ ok: true, data: await checkAsin(message.asin) });
          break;
        case 'FETCH_ASIN':
          sendResponse({ ok: true, data: await fetchAsinInfo(message.asin, message.categorie) });
          break;
        case 'ADD_COMPONENT':
          sendResponse({ ok: true, data: await addComponent(message.asin, message.categorie, message.fetched) });
          break;
        case 'FETCH_AND_ADD':
          sendResponse({ ok: true, data: await fetchAndAdd(message.asin, message.categorie) });
          break;
        case 'QUICK_ADD':
          sendResponse({ ok: true, data: await quickAdd(message.asin, message.categorie, message.quickData) });
          break;
        case 'ANALYSE_PAGE':
          sendResponse({ ok: true, data: await analysePage(message.items) });
          break;
        case 'SIMILAR':
          sendResponse({ ok: true, data: await similarProducts(message.titre, message.categorie) });
          break;
        case 'UPDATE_PRICE':
          sendResponse({ ok: true, data: await updatePrice(message.componentId, message.prix, message.asin) });
          break;
        case 'RELEVE_RESUME': {
          const settings = await getSettings();
          if (!settings.adminSecret) throw new Error('NO_SECRET');
          const res = await fetch(settings.siteUrl + '/api/admin/releve-prix', { headers: { 'X-Admin-Secret': settings.adminSecret } });
          if (!res.ok) throw new Error('Erreur ' + res.status);
          sendResponse({ ok: true, data: await res.json() });
          break;
        }
        case 'AUTO_PRICE': {
          // Fiche Amazon ouverte par l'admin : le site lit le prix de la page et l'applique.
          const settings = await getSettings();
          if (!settings.adminSecret) throw new Error('NO_SECRET');
          const res = await fetch(settings.siteUrl + '/api/admin/prix-extension', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': settings.adminSecret },
            body: JSON.stringify({ id: message.componentId, asin: message.asin, extrait: message.extrait, origine: 'navigation' }),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.detail || ('Erreur ' + res.status));
          asinCache.delete(String(message.asin).toUpperCase());
          sendResponse({ ok: true, data });
          break;
        }
        case 'RELEVE_ETAT':
          sendResponse({ ok: true, data: await releveEtat() });
          break;
        case 'RELEVE_ACTIVER':
          await chrome.storage.local.set({ releveActif: !!message.actif, relevePauseJusqua: 0 });
          programmerReleve();
          if (message.actif) releverUnPrix().catch(() => {});
          sendResponse({ ok: true });
          break;
        case 'REMOVE_COMPONENT':
          sendResponse({ ok: true, data: await removeComponent(message.componentId, message.asin) });
          break;
        default:
          sendResponse({ ok: false, error: 'Type de message inconnu.' });
      }
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true; // réponse asynchrone
});
