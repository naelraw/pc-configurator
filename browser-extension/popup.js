function extractAsin(url) {
  if (!url) return null;
  const match = url.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i);
  return match ? match[1].toUpperCase() : null;
}

function sendMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response || !response.ok) {
        reject(new Error((response && response.error) || 'Erreur inconnue'));
        return;
      }
      resolve(response.data);
    });
  });
}

function setStatus(text, kind) {
  const el = document.getElementById('status');
  el.textContent = text;
  el.className = kind === 'error' ? 'is-error' : kind === 'ok' ? 'is-ok' : '';
}

function setLoading(btn, isLoading) {
  btn.disabled = isLoading;
  btn.classList.toggle('loading', isLoading);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

let currentAsin = null;
let guessedCategorie = 'Accessoire';
let lastComponentId = null;

function resolvedCategorie() {
  const value = document.getElementById('categorie-select').value;
  return value || guessedCategorie;
}

async function refreshCatalogStatus() {
  const el = document.getElementById('catalog-status');
  try {
    const result = await sendMessage({ type: 'CHECK_ASIN', asin: currentAsin });
    if (result.exists) {
      const c = result.component;
      lastComponentId = c.id;
      el.className = 'status-in';
      el.innerHTML =
        '✓ Déjà dans le catalogue : <strong>' + escapeHtml(c.nom) + '</strong> (' + escapeHtml(c.categorie) + ')' +
        (c.en_stock === false ? ' — <span style="color:#ff5d5d;">épuisé</span>' : ' — ' + c.prix_indicatif + '€');
    } else {
      lastComponentId = null;
      el.className = 'status-out';
      el.textContent = 'Pas encore dans le catalogue PC Radar.';
    }
  } catch (e) {
    el.className = '';
    el.textContent = '';
  }
}

// Lit le fil d'Ariane + le titre produit directement sur l'onglet Amazon
// actif (la popup n'a pas accès au DOM de la page comme content.js) pour
// présélectionner la même catégorie devinée que le panneau injecté.
async function guessCategorieFromTab(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        breadcrumb: document.querySelector('#wayfinding-breadcrumbs_feature_div')?.innerText
          || document.querySelector('.a-breadcrumb')?.innerText
          || '',
        title: document.getElementById('productTitle')?.innerText || document.title || '',
      }),
    });
    return pcradarGuessCategorie(result.breadcrumb, result.title);
  } catch (e) {
    return null; // page pas encore chargée, permissions refusées... on garde le choix par défaut
  }
}

// Même logique que pcradarExtractQuickData (categorize.js), dupliquée ici
// en autonome : le code passé à executeScript() s'exécute DANS l'onglet
// Amazon, isolé du contexte de la popup où categorize.js est chargé — pas
// moyen d'appeler une fonction partagée depuis là sans l'injecter en plus.
async function extractQuickDataFromTab(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const nomEl = document.querySelector('#productTitle') || document.querySelector('h2');
        const nom = nomEl ? nomEl.innerText.trim() : null;
        const priceEl = document.querySelector('#corePrice_feature_div .a-price .a-offscreen')
          || document.querySelector('.a-price .a-offscreen');
        const priceText = priceEl ? priceEl.textContent : null;
        let prix = null;
        if (priceText) {
          const cleaned = String(priceText).replace(/[^\d,.\s]/g, '').trim();
          const normalized = cleaned.replace(/\s/g, '').replace(',', '.');
          const value = parseFloat(normalized);
          prix = Number.isFinite(value) ? value : null;
        }
        const imgEl = document.querySelector('#landingImage')
          || document.querySelector('#imgTagWrapperId img')
          || document.querySelector('img.s-image')
          || document.querySelector('img');
        return { nom, prix, image_url: imgEl ? imgEl.src : null };
      },
    });
    return result;
  } catch (e) {
    return { nom: null, prix: null, image_url: null };
  }
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentAsin = extractAsin(tab && tab.url);

  if (!currentAsin) {
    document.getElementById('no-asin').style.display = 'block';
    document.getElementById('main-ui').style.display = 'none';
    return;
  }
  document.getElementById('asin-display').textContent = 'ASIN détecté : ' + currentAsin;

  const settings = await sendMessage({ type: 'GET_SETTINGS' });
  document.getElementById('site-url').value = settings.siteUrl;
  document.getElementById('admin-secret').value = settings.adminSecret;

  const guessed = await guessCategorieFromTab(tab.id);
  if (guessed) {
    guessedCategorie = guessed;
    document.getElementById('categorie-auto-opt').textContent = 'Auto (' + guessed + ')';
  }
  document.getElementById('categorie-select').value = ''; // "Auto" sélectionné par défaut

  refreshCatalogStatus();
}

document.getElementById('save-settings-btn').addEventListener('click', async () => {
  const siteUrl = document.getElementById('site-url').value.trim();
  const adminSecret = document.getElementById('admin-secret').value;
  await sendMessage({ type: 'SAVE_SETTINGS', siteUrl, adminSecret });
  setStatus('Réglages enregistrés.', null);
});

// Un seul clic : récupère depuis Amazon ET enregistre directement, sans
// étape de confirmation intermédiaire — l'utilisateur ne voit qu'un seul
// temps de chargement. "Retirer" sert de filet de sécurité si le résultat
// ne convient pas, plutôt qu'une validation systématique avant coup.
document.getElementById('fetch-btn').addEventListener('click', async () => {
  const categorie = resolvedCategorie();
  const btn = document.getElementById('fetch-btn');
  setLoading(btn, true);
  document.getElementById('preview').style.display = 'none';
  setStatus('Ajout en cours…', null);

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const quickData = await extractQuickDataFromTab(tab.id);
    const { fetched, componentId } = await sendMessage({ type: 'QUICK_ADD', asin: currentAsin, categorie, quickData });
    lastComponentId = componentId;
    document.getElementById('preview-img').src = fetched.image_url || '';
    document.getElementById('preview-nom').textContent = fetched.nom || '(nom introuvable)';
    document.getElementById('preview-prix').textContent =
      fetched.prix != null ? fetched.prix + ' €' : 'Prix introuvable (épuisé ou indisponible)';
    document.getElementById('preview').style.display = 'block';
    setStatus('✓ Ajouté ! Specs précises en cours de complétion en arrière-plan…', 'ok');
    refreshCatalogStatus();
  } catch (e) {
    if (e.message === 'NO_SECRET') {
      setStatus("Renseigne d'abord ta clé admin dans les réglages ci-dessous.", 'error');
      document.getElementById('settings').open = true;
    } else {
      setStatus('Erreur : ' + e.message, 'error');
    }
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('remove-btn').addEventListener('click', async () => {
  if (!lastComponentId) return;
  const btn = document.getElementById('remove-btn');
  setLoading(btn, true);
  setStatus('Retrait en cours…', null);

  try {
    await sendMessage({ type: 'REMOVE_COMPONENT', componentId: lastComponentId, asin: currentAsin });
    document.getElementById('preview').style.display = 'none';
    setStatus('Retiré du catalogue.', null);
    refreshCatalogStatus();
  } catch (e) {
    setStatus('Erreur au retrait : ' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
});

init();
