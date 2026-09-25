(function () {
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

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  const CATEGORIES = ['CPU', 'Carte mère', 'RAM', 'Boîtier', 'Alimentation', 'GPU', 'Stockage', 'Refroidissement', 'Accessoire'];
  const LOGO_SVG = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" stroke="#2dd4bf" stroke-width="1.6" opacity="0.35"/>
      <circle cx="12" cy="12" r="5.5" stroke="#2dd4bf" stroke-width="1.6" opacity="0.6"/>
      <circle cx="12" cy="12" r="1.8" fill="#2dd4bf"/>
      <path d="M12 12 L18 6.5" stroke="#2dd4bf" stroke-width="1.6" stroke-linecap="round"/>
    </svg>`;

  function extractPageAsin() {
    const match = window.location.pathname.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i);
    if (match) return match[1].toUpperCase();
    // Repli : Amazon expose aussi l'ASIN dans un champ caché sur la page.
    const hidden = document.getElementById('ASIN') || document.querySelector('input[name="ASIN"]');
    return hidden ? hidden.value.toUpperCase() : null;
  }

  // ---------------------------------------------------------------------
  // Panneau flottant : uniquement sur une page produit (URL /dp/<ASIN>).
  // ---------------------------------------------------------------------
  function initProductPanel(asin) {
    const panel = document.createElement('div');
    panel.id = 'pcradar-panel';
    panel.innerHTML = `
      <div id="pcradar-header">
        <div id="pcradar-header-left">
          ${LOGO_SVG}
          <span id="pcradar-title">PC <span class="pcradar-accent">RADAR</span></span>
        </div>
        <button id="pcradar-collapse" title="Réduire">–</button>
      </div>
      <div id="pcradar-body">
        <div id="pcradar-status">Vérification du catalogue…</div>
        <div id="pcradar-info"></div>
        <div id="pcradar-controls" style="display:none;">
          <select id="pcradar-categorie"></select>
          <button id="pcradar-fetch"><span class="pcradar-btn-label">Ajouter au catalogue</span></button>
        </div>
        <div id="pcradar-result" style="display:none;">
          <img id="pcradar-result-img" alt="">
          <div id="pcradar-result-nom"></div>
          <div id="pcradar-result-prix"></div>
          <button id="pcradar-remove" class="pcradar-secondary"><span class="pcradar-btn-label">Retirer</span></button>
        </div>
        <div id="pcradar-msg"></div>
      </div>
    `;
    document.documentElement.appendChild(panel);

    // Devinée à partir du fil d'Ariane Amazon (sa propre catégorisation, lue
    // directement sur la page) avant de construire le menu, pour pouvoir
    // l'afficher EN CLAIR dans l'option "Auto" plutôt que de la présélectionner
    // silencieusement — l'utilisateur voit ce qui sera réellement envoyé.
    const breadcrumbText = document.querySelector('#wayfinding-breadcrumbs_feature_div')?.innerText
      || document.querySelector('.a-breadcrumb')?.innerText
      || '';
    const titleText = document.getElementById('productTitle')?.innerText || document.title || '';
    const guessedCategorie = pcradarGuessCategorie(breadcrumbText, titleText);

    const select = panel.querySelector('#pcradar-categorie');
    const autoOpt = document.createElement('option');
    autoOpt.value = '';
    autoOpt.textContent = 'Auto (' + guessedCategorie + ')';
    select.appendChild(autoOpt);
    CATEGORIES.forEach((cat) => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      select.appendChild(opt);
    });
    select.value = ''; // "Auto" sélectionné par défaut

    function resolvedCategorie() {
      return select.value || guessedCategorie;
    }

    const statusEl = panel.querySelector('#pcradar-status');
    const controlsEl = panel.querySelector('#pcradar-controls');
    const resultEl = panel.querySelector('#pcradar-result');
    const msgEl = panel.querySelector('#pcradar-msg');

    function setMsg(text, kind) {
      msgEl.textContent = text || '';
      msgEl.className = kind === 'error' ? 'pcradar-msg-error' : kind === 'ok' ? 'pcradar-msg-ok' : '';
    }

    function setLoading(btn, isLoading) {
      btn.disabled = isLoading;
      btn.classList.toggle('pcradar-loading', isLoading);
    }

    panel.querySelector('#pcradar-collapse').addEventListener('click', () => {
      const collapsed = panel.classList.toggle('pcradar-collapsed');
      panel.querySelector('#pcradar-collapse').textContent = collapsed ? '+' : '–';
    });

    let lastComponentId = null;
    const infoEl = panel.querySelector('#pcradar-info');

    function formatEuros(v) {
      return Number(v).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    }

    // Infos utiles sur un produit déjà catalogué : variante, écart entre le prix
    // affiché sur cette page et le prix du catalogue (mise à jour en un clic),
    // prix signalé suspect par le contrôle quotidien.
    function renderKnownInfo(c) {
      const parts = [];
      if (c.nb_variantes > 1) {
        parts.push('<div class="pcradar-line">Variante' + (c.variante ? ' « ' + escapeHtml(c.variante) + ' »' : '')
          + ' d\'un produit à ' + c.nb_variantes + ' annonces.</div>');
      }
      const pagePrice = pcradarExtractQuickData(document).prix;
      const catalogPrice = Number(c.prix_indicatif) || 0;
      if (pagePrice && catalogPrice && Math.abs(pagePrice - catalogPrice) / catalogPrice > 0.01) {
        const diff = pagePrice - catalogPrice;
        parts.push('<div class="pcradar-line pcradar-price-diff">Prix sur cette page : <strong>' + formatEuros(pagePrice)
          + '</strong> (catalogue : ' + formatEuros(catalogPrice) + ', ' + (diff > 0 ? '+' : '') + formatEuros(diff) + ')</div>'
          + '<button id="pcradar-update-price" class="pcradar-secondary"><span class="pcradar-btn-label">Mettre à jour le prix (' + formatEuros(pagePrice) + ')</span></button>');
      }
      if (c.prix_suspect) {
        parts.push('<div class="pcradar-line pcradar-warn">⚠ Prix signalé suspect : ' + formatEuros(c.prix_suspect.prix)
          + ' au lieu d\'environ ' + formatEuros(c.prix_suspect.reference) + ' pour les autres annonces du même produit.</div>');
      }
      if (c.page) {
        parts.push('<a class="pcradar-link" href="' + escapeHtml('https://pcradar.tech' + c.page) + '" target="_blank" rel="noopener">Voir la fiche PC Radar ↗</a>');
      }
      infoEl.innerHTML = parts.join('');
      const btn = infoEl.querySelector('#pcradar-update-price');
      if (btn) {
        btn.addEventListener('click', async () => {
          setLoading(btn, true);
          try {
            await sendMessage({ type: 'UPDATE_PRICE', componentId: c.id, prix: pagePrice, asin });
            setMsg('✓ Prix mis à jour : ' + formatEuros(pagePrice), 'ok');
            refreshStatus();
          } catch (e) {
            setMsg(e.message === 'NO_SECRET' ? "Clé admin manquante — clique sur l'icône de l'extension." : 'Erreur : ' + e.message, 'error');
            setLoading(btn, false);
          }
        });
      }
    }

    // Produit pas encore catalogué : un produit proche existe-t-il déjà ?
    async function renderSimilar() {
      try {
        const { proches } = await sendMessage({ type: 'SIMILAR', titre: titleText, categorie: resolvedCategorie() });
        if (!proches || !proches.length) { infoEl.innerHTML = ''; return; }
        infoEl.innerHTML = '<div class="pcradar-line pcradar-warn">Déjà au catalogue sous une autre annonce ? Vérifie avant d\'ajouter :</div>'
          + proches.map((p) => '<a class="pcradar-link" href="' + escapeHtml('https://pcradar.tech' + (p.page || '')) + '" target="_blank" rel="noopener">'
            + escapeHtml(p.nom) + (p.nb_variantes > 1 ? ' (' + p.nb_variantes + ' variantes)' : '')
            + ' — ' + formatEuros(p.prix_indicatif) + ' ↗</a>').join('')
          + '<div class="pcradar-line pcradar-muted">Si c\'est le même produit, l\'ajouter en fera une variante (même fiche, plusieurs prix).</div>';
      } catch (e) {
        infoEl.innerHTML = '';
      }
    }

    async function refreshStatus() {
      try {
        const result = await sendMessage({ type: 'CHECK_ASIN', asin });
        if (result.exists) {
          const c = result.component;
          lastComponentId = c.id;
          statusEl.className = 'pcradar-status-in';
          statusEl.innerHTML =
            '✓ Déjà dans le catalogue : <strong>' + escapeHtml(c.nom) + '</strong> (' + escapeHtml(c.categorie) + ')' +
            (c.en_stock === false ? ' — <span style="color:#ff5d5d;">épuisé</span>' : ' — ' + c.prix_indicatif + '€');
          controlsEl.style.display = 'block';
          panel.querySelector('#pcradar-fetch .pcradar-btn-label').textContent = 'Rafraîchir depuis Amazon';
          renderKnownInfo(c);
        } else {
          lastComponentId = null;
          statusEl.className = 'pcradar-status-out';
          statusEl.textContent = 'Pas encore dans le catalogue PC Radar.';
          controlsEl.style.display = 'block';
          renderSimilar();
        }
      } catch (e) {
        statusEl.className = '';
        statusEl.textContent = '';
        setMsg('Erreur : ' + e.message, 'error');
        controlsEl.style.display = 'block';
      }
    }

    panel.querySelector('#pcradar-fetch').addEventListener('click', async () => {
      const btn = panel.querySelector('#pcradar-fetch');
      const categorie = resolvedCategorie();
      setLoading(btn, true);
      resultEl.style.display = 'none';
      setMsg('Ajout en cours…', null);
      try {
        const quickData = pcradarExtractQuickData(document);
        const { fetched, componentId } = await sendMessage({ type: 'QUICK_ADD', asin, categorie, quickData });
        lastComponentId = componentId;
        panel.querySelector('#pcradar-result-img').src = fetched.image_url || '';
        panel.querySelector('#pcradar-result-nom').textContent = fetched.nom || '(nom introuvable)';
        panel.querySelector('#pcradar-result-prix').textContent =
          fetched.prix != null ? fetched.prix + ' €' : 'Prix introuvable (épuisé ou indisponible)';
        resultEl.style.display = 'block';
        setMsg('✓ Ajouté ! Specs précises en cours de complétion en arrière-plan…', 'ok');
        statusEl.className = 'pcradar-status-in';
        statusEl.innerHTML = '✓ Dans le catalogue : <strong>' + escapeHtml(fetched.nom || asin) + '</strong>';
        panel.querySelector('#pcradar-fetch .pcradar-btn-label').textContent = 'Rafraîchir depuis Amazon';
      } catch (e) {
        if (e.message === 'NO_SECRET') {
          setMsg("Clé admin manquante — clique sur l'icône de l'extension pour la renseigner.", 'error');
        } else {
          setMsg('Erreur : ' + e.message, 'error');
        }
      } finally {
        setLoading(btn, false);
      }
    });

    panel.querySelector('#pcradar-remove').addEventListener('click', async () => {
      if (!lastComponentId) return;
      const btn = panel.querySelector('#pcradar-remove');
      setLoading(btn, true);
      setMsg('Retrait en cours…', null);
      try {
        await sendMessage({ type: 'REMOVE_COMPONENT', componentId: lastComponentId, asin });
        resultEl.style.display = 'none';
        setMsg('Retiré du catalogue.', null);
        refreshStatus();
      } catch (e) {
        setMsg('Erreur au retrait : ' + e.message, 'error');
      } finally {
        setLoading(btn, false);
      }
    });

    refreshStatus();
  }

  // ---------------------------------------------------------------------
  // Boutons "+" sur chaque carte produit des pages de résultats/listes
  // (recherche, catégorie, "vu précédemment"...) — Amazon marque chaque
  // carte avec un attribut data-asin sur son conteneur, qu'elle soit dans
  // une recherche, un carrousel ou une grille de catégorie : un seul
  // sélecteur générique couvre tous ces cas sans dépendre d'une mise en
  // page Amazon précise (qui change régulièrement).
  // ---------------------------------------------------------------------
  const injectedCards = new WeakSet();

  function guessCategorieForCard(card) {
    const titleText = card.querySelector('h2')?.innerText || card.innerText.slice(0, 300);
    return pcradarGuessCategorie('', titleText);
  }

  function setCardBtnState(btn, state, label) {
    btn.className = 'pcradar-card-btn pcradar-card-' + state;
    btn.title = label || '';
  }

  async function fetchAndAddFromCard(cardAsin, btn) {
    if (btn.classList.contains('pcradar-card-loading') || btn.classList.contains('pcradar-card-in')) return;
    setCardBtnState(btn, 'loading', 'Ajout en cours…');
    try {
      const card = btn.closest('[data-asin]');
      const categorie = guessCategorieForCard(card);
      const quickData = pcradarExtractQuickData(card);
      const { fetched } = await sendMessage({ type: 'QUICK_ADD', asin: cardAsin, categorie, quickData });
      setCardBtnState(btn, 'in', '✓ Ajouté : ' + (fetched.nom || cardAsin));
    } catch (e) {
      setCardBtnState(btn, 'error', 'Erreur : ' + e.message);
      setTimeout(() => setCardBtnState(btn, 'out', 'Ajouter à PC Radar'), 2500);
    }
  }

  function buildCardButton(cardAsin) {
    const btn = document.createElement('button');
    btn.type = 'button';
    setCardBtnState(btn, 'out', 'Ajouter à PC Radar');
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      fetchAndAddFromCard(cardAsin, btn);
    });

    // Vérifie discrètement si le produit est déjà catalogué, pour afficher
    // directement l'état "✓" plutôt qu'un "+" trompeur.
    sendMessage({ type: 'CHECK_ASIN', asin: cardAsin }).then((result) => {
      if (result.exists) setCardBtnState(btn, 'in', 'Déjà dans le catalogue : ' + result.component.nom);
    }).catch(() => {});

    return btn;
  }

  function tryInjectCard(card) {
    const cardAsin = card.getAttribute('data-asin');
    if (!cardAsin || !/^[A-Z0-9]{10}$/i.test(cardAsin)) return;
    if (injectedCards.has(card)) return;
    // Pas de titre exploitable = pas la vraie carte produit (juste un
    // widget interne comme le bouton "Ajouter au panier", ou une vignette
    // du panier sur le côté) : on ignore plutôt que de deviner une
    // catégorie au hasard sur du texte non pertinent (c'est ce qui causait
    // un classement systématique en "Accessoire").
    if (!card.querySelector('h2')) return;
    injectedCards.add(card);

    const style = window.getComputedStyle(card);
    if (style.position === 'static') card.style.position = 'relative';
    card.appendChild(buildCardButton(cardAsin.toUpperCase()));
  }

  function injectCardButtons(root) {
    const scope = root || document;

    // Vraies cartes de résultats de recherche : Amazon les marque avec ce
    // data-component-type précis, structure fiable avec un h2 titre —
    // sélecteur à privilégier avant le repli générique ci-dessous.
    scope.querySelectorAll('div[data-component-type="s-search-result"][data-asin]').forEach(tryInjectCard);

    // Repli générique pour les autres types de pages (carrousels "vu avec
    // cet article", grilles de catégorie...) qui n'ont pas ce marqueur —
    // en excluant tout ce que le sélecteur précis a déjà couvert, et tout
    // conteneur qui imbrique lui-même un [data-asin] enfant (widget interne
    // plutôt que vraie carte produit, comme découvert avec le bug ci-dessus).
    scope.querySelectorAll('[data-asin]').forEach((card) => {
      if (card.matches('div[data-component-type="s-search-result"]')) return;
      if (card.closest('div[data-component-type="s-search-result"]')) return;
      if (card.querySelector('[data-asin]')) return;
      tryInjectCard(card);
    });
  }

  injectCardButtons();
  // Les résultats de recherche se chargent aussi en scroll infini /
  // pagination AJAX sur certaines pages Amazon : on observe le DOM plutôt
  // que de ne scanner qu'une fois au chargement. Amazon déclenche BEAUCOUP
  // de petites mutations mineures en continu (images lazy-load, compteurs...) :
  // un débounce évite de rescanner tout le document à chaque micro-mutation.
  let rescanTimer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(rescanTimer);
    rescanTimer = setTimeout(() => injectCardButtons(), 200);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  const pageAsin = extractPageAsin();
  if (pageAsin) initProductPanel(pageAsin);
})();
