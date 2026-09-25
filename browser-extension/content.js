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
    <svg class="pcradar-logo" width="20" height="20" viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="15" fill="#141517"/>
      <rect x=".75" y=".75" width="62.5" height="62.5" rx="14.25" fill="none" stroke="#35363c" stroke-width="1.5"/>
      <g transform="translate(0 1.5)" fill="none" stroke="#ececee" stroke-width="7">
        <path d="M21 49V15h12.5a9.5 9.5 0 0 1 0 19H21"/><path d="M31.5 34 44.6 49"/>
      </g>
      <circle cx="50" cy="13" r="4.5" fill="#3ecf8e"/>
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
          <span id="pcradar-title">PC Radar</span>
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
            (c.en_stock === false ? ' — <span style="color:#f07171;">épuisé</span>' : ' — ' + c.prix_indicatif + '€');
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
  // Pages de résultats et listes (recherche, catégorie, carrousels) : une
  // étiquette sur chaque produit (au catalogue avec son prix, pas encore
  // catalogué, ou proche d'un produit existant) et une barre d'actions
  // groupées. Amazon marque chaque carte produit d'un attribut data-asin.
  // Tout l'état de la page est demandé au site en UNE requête
  // (/api/admin/analyse-page), pas une par produit.
  // ---------------------------------------------------------------------
  const entries = [];              // { asin, card, pill, categorie, data, state, selected }
  const seenCards = new WeakSet();
  const pending = new Set();
  let analyseTimer = null;
  let secretMissing = false;
  let hideKnown = false;
  let bar = null;
  let busy = false;

  const euros = (v) => Number(v).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  const cardTitle = (card) => (card.querySelector('h2')?.innerText || '').replace(/\s+/g, ' ').trim();

  function priceGap(entry) {
    const c = entry.data && entry.data.catalogue;
    const pagePrice = pcradarExtractQuickData(entry.card).prix;
    const catalogPrice = c ? Number(c.prix_indicatif) || 0 : 0;
    if (!c || !pagePrice || !catalogPrice) return null;
    return Math.abs(pagePrice - catalogPrice) / catalogPrice > 0.01 ? pagePrice : null;
  }

  function registerCard(card) {
    const asin = (card.getAttribute('data-asin') || '').toUpperCase();
    if (!/^[A-Z0-9]{10}$/.test(asin) || seenCards.has(card)) return;
    // Pas de titre = widget interne (bouton panier, vignette), pas une vraie carte produit.
    if (!card.querySelector('h2')) return;
    seenCards.add(card);
    if (window.getComputedStyle(card).position === 'static') card.style.position = 'relative';
    const pill = document.createElement('div');
    pill.className = 'pcradar-pill pcradar-pill-loading';
    pill.innerHTML = '<span class="pcradar-pill-spin"></span>';
    card.appendChild(pill);
    const entry = { asin, card, pill, categorie: pcradarGuessCategorie('', cardTitle(card)), data: null, state: 'loading', selected: false };
    entries.push(entry);
    pill.addEventListener('click', (e) => onPillClick(e, entry));
    pill.addEventListener('change', (e) => onPillChange(e, entry));
    pending.add(asin);
    scheduleAnalyse();
  }

  function scheduleAnalyse() {
    clearTimeout(analyseTimer);
    analyseTimer = setTimeout(runAnalyse, 250);
  }

  async function runAnalyse() {
    if (!pending.size) return;
    const asins = [...pending].slice(0, 60);
    asins.forEach((a) => pending.delete(a));
    const items = asins.map((asin) => {
      const e = entries.find((x) => x.asin === asin);
      return { asin, titre: e ? cardTitle(e.card) : '', categorie: e ? e.categorie : '' };
    });
    try {
      const resultats = await sendMessage({ type: 'ANALYSE_PAGE', items });
      entries.filter((e) => asins.includes(e.asin)).forEach((e) => {
        e.data = resultats[e.asin] || { catalogue: null, proche: null };
        e.state = e.data.catalogue ? 'in' : 'out';
        renderPill(e);
      });
    } catch (err) {
      secretMissing = err.message === 'NO_SECRET';
      entries.filter((e) => asins.includes(e.asin)).forEach((e) => {
        e.state = 'error';
        e.error = secretMissing ? 'Clé admin manquante' : err.message;
        renderPill(e);
      });
    }
    if (pending.size) scheduleAnalyse();
    renderBar();
  }

  function categorySelect(entry) {
    return '<select class="pcradar-pill-cat" title="Catégorie">' + CATEGORIES.map((c) =>
      '<option value="' + escapeHtml(c) + '"' + (c === entry.categorie ? ' selected' : '') + '>' + escapeHtml(c) + '</option>').join('') + '</select>';
  }

  function renderPill(entry) {
    const pill = entry.pill;
    const c = entry.data && entry.data.catalogue;
    pill.className = 'pcradar-pill pcradar-pill-' + entry.state;
    entry.card.classList.toggle('pcradar-hidden-card', hideKnown && entry.state === 'in');
    if (entry.state === 'in') {
      const gap = priceGap(entry);
      pill.innerHTML =
        '<span class="pcradar-pill-row">'
        + '<span class="pcradar-pill-check" aria-hidden="true">✓</span>'
        + '<b>' + euros(c.prix_indicatif) + '</b>'
        + (c.en_stock === false ? '<span class="pcradar-pill-muted">épuisé</span>' : '')
        + (c.prix_suspect ? '<span class="pcradar-pill-flag" title="Prix signalé suspect dans le catalogue">!</span>' : '')
        + (c.page ? '<a class="pcradar-pill-link" href="https://pcradar.tech' + escapeHtml(c.page) + '" target="_blank" rel="noopener" title="Voir la fiche PC Radar">↗</a>' : '')
        + '</span>'
        + (c.nb_variantes > 1 ? '<span class="pcradar-pill-sub">' + escapeHtml(c.variante || '') + ' · ' + c.nb_variantes + ' variantes</span>' : '')
        + (gap ? '<button class="pcradar-pill-btn" data-act="price" title="Remplacer le prix du catalogue par celui de cette page">Prix Amazon : ' + euros(gap) + ' · mettre à jour</button>' : '');
    } else if (entry.state === 'out') {
      const p = entry.data && entry.data.proche;
      pill.innerHTML =
        '<span class="pcradar-pill-row">'
        + '<input type="checkbox" class="pcradar-pill-select" title="Sélectionner pour un ajout groupé"' + (entry.selected ? ' checked' : '') + '>'
        + '<button class="pcradar-pill-btn pcradar-pill-add" data-act="add">+ Ajouter</button>'
        + categorySelect(entry)
        + '</span>'
        + (p ? '<a class="pcradar-pill-sub pcradar-pill-near" href="https://pcradar.tech' + escapeHtml(p.page || '') + '" target="_blank" rel="noopener" title="Produit proche déjà au catalogue : si c\'est le même, l\'ajouter en fera une variante">≈ ' + escapeHtml(p.nom) + (p.nb_variantes > 1 ? ' (' + p.nb_variantes + ' variantes)' : '') + '</a>' : '');
    } else if (entry.state === 'busy') {
      pill.innerHTML = '<span class="pcradar-pill-spin"></span><span>' + escapeHtml(entry.busyText || 'En cours…') + '</span>';
    } else if (entry.state === 'error') {
      pill.innerHTML = '<span class="pcradar-pill-flag">!</span><span>' + escapeHtml(entry.error || 'Erreur') + '</span>'
        + (secretMissing ? '' : '<button class="pcradar-pill-btn" data-act="retry">Réessayer</button>');
    }
  }

  function onPillClick(e, entry) {
    // Les cartes Amazon sont des liens : un clic dans l'étiquette ne doit pas ouvrir le produit.
    e.stopPropagation();
    const link = e.target.closest('a');
    if (link) return;
    if (e.target.closest('select, input')) return;
    e.preventDefault();
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'add') addEntry(entry).then(renderBar);
    else if (act === 'price') updateEntryPrice(entry).then(renderBar);
    else if (act === 'retry') { entry.state = 'loading'; renderPill(entry); pending.add(entry.asin); scheduleAnalyse(); }
  }

  function onPillChange(e, entry) {
    e.stopPropagation();
    if (e.target.classList.contains('pcradar-pill-cat')) entry.categorie = e.target.value;
    if (e.target.classList.contains('pcradar-pill-select')) { entry.selected = e.target.checked; renderBar(); }
  }

  async function addEntry(entry) {
    if (entry.state !== 'out') return false;
    entry.state = 'busy';
    entry.busyText = 'Ajout…';
    renderPill(entry);
    try {
      await sendMessage({ type: 'QUICK_ADD', asin: entry.asin, categorie: entry.categorie, quickData: pcradarExtractQuickData(entry.card) });
      entry.selected = false;
      entry.state = 'loading';
      renderPill(entry);
      pending.add(entry.asin);
      scheduleAnalyse();
      return true;
    } catch (err) {
      entry.state = 'error';
      entry.error = err.message === 'NO_SECRET' ? 'Clé admin manquante' : err.message;
      renderPill(entry);
      return false;
    }
  }

  async function updateEntryPrice(entry) {
    const prix = priceGap(entry);
    if (!prix) return false;
    const c = entry.data.catalogue;
    entry.state = 'busy';
    entry.busyText = 'Mise à jour du prix…';
    renderPill(entry);
    try {
      await sendMessage({ type: 'UPDATE_PRICE', componentId: c.id, prix, asin: entry.asin });
      c.prix_indicatif = prix;
      entry.state = 'in';
      renderPill(entry);
      return true;
    } catch (err) {
      entry.state = 'in';
      renderPill(entry);
      setBarMsg('Erreur : ' + err.message, true);
      return false;
    }
  }

  // Deux à la fois : chaque ajout lance ensuite un enrichissement (specs, nom
  // nettoyé) côté site, inutile de saturer.
  async function runBatch(list, action, label) {
    if (busy || !list.length) return;
    busy = true;
    let done = 0, ok = 0, next = 0;
    const worker = async () => {
      while (next < list.length) {
        const e = list[next++];
        if (await action(e)) ok++;
        done++;
        setBarMsg(label + ' ' + done + '/' + list.length + '…');
      }
    };
    await Promise.all([worker(), worker()]);
    busy = false;
    setBarMsg(ok + ' sur ' + list.length + ' : ' + (label === 'Ajout' ? 'ajouté(s) au catalogue.' : 'prix mis à jour.'), ok < list.length);
    renderBar();
  }

  function setBarMsg(text, isError) {
    if (!bar) return;
    const el = bar.querySelector('.pcradar-bar-msg');
    el.textContent = text || '';
    el.classList.toggle('pcradar-bar-error', !!isError);
  }

  function isListingPage() {
    return !!document.querySelector('div[data-component-type="s-search-result"]') || !extractPageAsin();
  }

  function renderBar() {
    if (!isListingPage() || entries.length < 2) return;
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'pcradar-bar';
      bar.innerHTML = '<div class="pcradar-bar-head">' + LOGO_SVG + '<span class="pcradar-bar-title">PC Radar</span>'
        + '<span class="pcradar-bar-counts"></span><button class="pcradar-bar-toggle" data-act="collapse" title="Réduire">–</button></div>'
        + '<div class="pcradar-bar-body"><div class="pcradar-bar-actions"></div><div class="pcradar-bar-msg"></div></div>';
      document.documentElement.appendChild(bar);
      bar.addEventListener('click', onBarClick);
    }
    const unique = (list) => [...new Map(list.map((e) => [e.asin, e])).values()];
    const known = unique(entries.filter((e) => e.state === 'in'));
    const fresh = unique(entries.filter((e) => e.state === 'out'));
    const selected = unique(entries.filter((e) => e.state === 'out' && e.selected));
    const gaps = unique(known.filter((e) => priceGap(e)));
    bar.querySelector('.pcradar-bar-counts').textContent =
      known.length + ' au catalogue · ' + fresh.length + ' nouveaux' + (gaps.length ? ' · ' + gaps.length + ' prix différents' : '');
    const actions = secretMissing
      ? '<span class="pcradar-bar-note">Clé admin manquante : clique sur l\'icône de l\'extension pour la renseigner.</span>'
      : '<button data-act="select-all"' + (fresh.length ? '' : ' disabled') + '>' + (selected.length && selected.length === fresh.length ? 'Tout désélectionner' : 'Sélectionner les nouveaux') + '</button>'
        + '<button class="pcradar-primary" data-act="add-selected"' + (selected.length && !busy ? '' : ' disabled') + '>Ajouter la sélection (' + selected.length + ')</button>'
        + '<button data-act="update-prices"' + (gaps.length && !busy ? '' : ' disabled') + '>Mettre à jour ' + gaps.length + ' prix</button>'
        + '<button data-act="hide-known"' + (known.length ? '' : ' disabled') + '>' + (hideKnown ? 'Afficher' : 'Masquer') + ' ceux déjà au catalogue</button>';
    bar.querySelector('.pcradar-bar-actions').innerHTML = actions;
  }

  function onBarClick(e) {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    const fresh = entries.filter((x) => x.state === 'out');
    if (act === 'collapse') {
      const collapsed = bar.classList.toggle('pcradar-bar-collapsed');
      e.target.textContent = collapsed ? '+' : '–';
    } else if (act === 'select-all') {
      const all = fresh.length && fresh.every((x) => x.selected);
      fresh.forEach((x) => { x.selected = !all; renderPill(x); });
      renderBar();
    } else if (act === 'add-selected') {
      const seen = new Set();
      const list = fresh.filter((x) => x.selected && !seen.has(x.asin) && seen.add(x.asin));
      runBatch(list, addEntry, 'Ajout');
    } else if (act === 'update-prices') {
      const seen = new Set();
      const list = entries.filter((x) => x.state === 'in' && priceGap(x) && !seen.has(x.asin) && seen.add(x.asin));
      runBatch(list, updateEntryPrice, 'Mise à jour');
    } else if (act === 'hide-known') {
      hideKnown = !hideKnown;
      entries.forEach((x) => x.card.classList.toggle('pcradar-hidden-card', hideKnown && x.state === 'in'));
      renderBar();
    }
  }

  function scanCards(root) {
    const scope = root || document;
    // Vraies cartes de résultats de recherche : marquage fiable, à privilégier.
    scope.querySelectorAll('div[data-component-type="s-search-result"][data-asin]').forEach(registerCard);
    // Repli pour les autres listes (carrousels, grilles de catégorie), en excluant
    // les conteneurs qui imbriquent eux-mêmes un [data-asin] (widgets internes).
    scope.querySelectorAll('[data-asin]').forEach((card) => {
      if (card.matches('div[data-component-type="s-search-result"]')) return;
      if (card.closest('div[data-component-type="s-search-result"]')) return;
      if (card.querySelector('[data-asin]')) return;
      registerCard(card);
    });
  }

  scanCards();
  // Résultats chargés au fil du défilement : on observe le DOM, avec un délai
  // pour ne pas rescanner à chaque petite mutation d'Amazon.
  let rescanTimer = null;
  new MutationObserver(() => {
    clearTimeout(rescanTimer);
    rescanTimer = setTimeout(() => scanCards(), 250);
  }).observe(document.body, { childList: true, subtree: true });

  const pageAsin = extractPageAsin();
  if (pageAsin) initProductPanel(pageAsin);
})();
