  const API_BASE = window.location.origin;
  let allComponents = [];

  // Échappe une valeur pour l'insérer comme texte affiché OU comme valeur
  // d'attribut HTML (href="...", src="...") — le nom d'une build et les
  // clés de composants_json sont saisis librement par l'utilisateur (ou
  // envoyés directement à l'API sans passer par l'interface), jamais
  // fiables tels quels dans du innerHTML.
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  async function loadComponents(){
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      allComponents = Object.values(data.components || {}).flat();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  function switchTab(tab){
    document.getElementById('tab-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-register').classList.toggle('active', tab === 'register');
    document.getElementById('login-form').classList.toggle('show', tab === 'login');
    document.getElementById('register-form').classList.toggle('show', tab === 'register');
  }

  function showError(id, message){
    const el = document.getElementById(id);
    el.textContent = message;
    el.classList.add('show');
  }
  function hideError(id){
    document.getElementById(id).classList.remove('show');
  }

  async function handleLogin(event){
    event.preventDefault();
    hideError('login-error');
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    try{
      const res = await fetch(API_BASE + '/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      });
      if(res.status === 401){
        showError('login-error', 'E-mail ou mot de passe incorrect.');
        return false;
      }
      if(!res.ok){
        showError('login-error', "Erreur lors de la connexion.");
        return false;
      }
      await refreshView();
    }catch(e){
      showError('login-error', 'Erreur réseau.');
    }
    return false;
  }

  async function handleRegister(event){
    event.preventDefault();
    hideError('register-error');
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value;

    try{
      const res = await fetch(API_BASE + '/api/auth/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, password }),
        credentials: 'include',
      });
      if(res.status === 409){
        showError('register-error', 'Un compte existe déjà avec cet e-mail.');
        return false;
      }
      if(!res.ok){
        const data = await res.json().catch(() => ({}));
        showError('register-error', data.detail || "Erreur lors de l'inscription.");
        return false;
      }
      await refreshView();
    }catch(e){
      showError('register-error', 'Erreur réseau.');
    }
    return false;
  }

  async function handleLogout(){
    await fetch(API_BASE + '/api/auth/logout', { method: 'POST', credentials: 'include' });
    await refreshView();
  }

  // Suppression du compte (RGPD) : confirmation en tapant SUPPRIMER.
  function showDeleteAccount(){
    document.getElementById('delete-account-box').hidden = false;
    document.getElementById('delete-account-confirm').focus();
  }

  function hideDeleteAccount(){
    document.getElementById('delete-account-box').hidden = true;
    document.getElementById('delete-account-confirm').value = '';
    document.getElementById('delete-account-btn').disabled = true;
    document.getElementById('delete-account-error').textContent = '';
  }

  function onDeleteConfirmInput(){
    const typed = document.getElementById('delete-account-confirm').value.trim().toUpperCase();
    document.getElementById('delete-account-btn').disabled = typed !== 'SUPPRIMER';
  }

  async function deleteAccount(){
    const btn = document.getElementById('delete-account-btn');
    const errorEl = document.getElementById('delete-account-error');
    btn.disabled = true;
    errorEl.textContent = '';
    try{
      const res = await fetch(API_BASE + '/api/auth/account', { method: 'DELETE', credentials: 'include' });
      if(!res.ok) throw new Error();
      try{ localStorage.removeItem('pc_configurator_draft'); }catch(e){}
      hideDeleteAccount();
      await refreshView();
      uiAlert('Ton compte et toutes tes données ont été supprimés.', { title: 'Compte supprimé', tone: 'ok' });
    }catch(e){
      errorEl.textContent = 'La suppression a échoué. Réessaie, ou écris à contact.pcradar@gmail.com.';
      btn.disabled = false;
    }
  }

  let lastLoadedBuilds = [];

  async function loadBuilds(){
    const listEl = document.getElementById('builds-list');
    try{
      if(allComponents.length === 0) await loadComponents();

      const res = await fetch(API_BASE + '/api/builds', { credentials: 'include' });
      const data = await res.json();
      lastLoadedBuilds = data.builds || [];

      if(!data.builds || data.builds.length === 0){
        listEl.innerHTML = '<div class="no-price">Aucune configuration sauvegardée pour l\'instant. Va sur le <a href="/configurateur" style="color:var(--led);">configurateur</a> pour en créer une.</div>';
        return;
      }

      listEl.innerHTML = data.builds.map((b, i) => `
        <div class="build-card chip-card">
          <div class="build-card-header" data-onclick="toggleBuildDetail(${i})">
            <div>
              <div class="build-name">${escapeHtml(b.nom)}</div>
              <div class="build-date">Sauvegardée le ${new Date(b.date).toLocaleDateString('fr-FR')}</div>
              ${renderBuildTotal(b)}
            </div>
            <div style="display:flex; align-items:center; gap:12px;">
              <button class="btn ${b.alerte ? 'btn-primary' : 'btn-secondary'}" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); toggleBuildAlert(${b.id})" aria-expanded="${b.alerte ? 'true' : 'false'}" aria-controls="build-alert-${b.id}"><i class="ph ph-bell-simple" aria-hidden="true"></i> ${b.alerte ? 'Alerte active' : 'Suivre le prix'}</button>
              <button class="btn btn-secondary" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); editBuild(${b.id})">Modifier</button>
              <button class="btn btn-secondary" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); estimateFpsForBuild(${b.id})"><i class="ph ph-game-controller" aria-hidden="true"></i> Estimer FPS</button>
              <button class="btn btn-secondary" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); copyBuildLink(${b.id})">Copier le lien</button>
              <button class="btn btn-secondary" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); addAllToAmazonCart(${b.id})"><i class="ph ph-shopping-cart" aria-hidden="true"></i> Tout ajouter au panier</button>
              <button class="btn btn-danger" style="padding:8px 14px; font-size:0.8rem;" data-onclick="event.stopPropagation(); deleteBuild(${b.id})">Supprimer</button>
              <span class="build-card-toggle" id="toggle-${i}"><i class="ph ph-caret-down" aria-hidden="true"></i></span>
            </div>
          </div>
          ${renderBuildAlert(b)}
          <div class="build-detail" id="detail-${i}">
            ${renderBuildDetail(b.composants_json)}
          </div>
        </div>
      `).join('');
    }catch(e){
      listEl.innerHTML = '<div class="no-price">Erreur lors du chargement de tes configurations.</div>';
    }
  }

  function buildCurrentTotal(b){
    const ids = Object.values(b.composants_json || {}).flat();
    const items = ids.map(id => allComponents.find(c => c.id === Number(id))).filter(Boolean);
    return items.length ? items.reduce((sum, c) => sum + Number(c.prix_indicatif || 0), 0) : null;
  }

  // Suivi du prix de la configuration entière : e-mail quand le TOTAL passe
  // sous le prix cible (proposé par défaut à 5 % sous le total actuel).
  function renderBuildAlert(b){
    const total = buildCurrentTotal(b);
    const cible = b.alerte ? b.alerte.prix_cible : (total ? Math.floor(total * 0.95) : '');
    return `
      <div class="build-alert${b.alerte ? ' is-active' : ''}" id="build-alert-${b.id}" ${b.alerte ? '' : 'hidden'}>
        <form class="follow-target" data-onsubmit="saveBuildAlert(event, ${b.id})">
          <label for="build-alert-input-${b.id}">${b.alerte
            ? `<i class="ph ph-check-circle" aria-hidden="true"></i> Tu recevras un e-mail quand le total passe sous`
            : 'Recevoir un e-mail quand le total de cette config passe sous'}</label>
          <input id="build-alert-input-${b.id}" type="number" min="1" step="1" inputmode="decimal" value="${cible}" required>
          <span class="build-alert-unit">€</span>
          <button type="submit" class="btn btn-secondary">${b.alerte ? 'Modifier' : 'Activer l\'alerte'}</button>
          ${b.alerte ? `<button type="button" class="btn-link" data-onclick="removeBuildAlert(${b.id})">Arrêter le suivi</button>` : ''}
        </form>
        <p class="follow-error" role="alert" id="build-alert-error-${b.id}"></p>
      </div>`;
  }

  function toggleBuildAlert(id){
    const box = document.getElementById('build-alert-' + id);
    box.hidden = !box.hidden;
    if(!box.hidden) document.getElementById('build-alert-input-' + id).focus();
  }

  async function saveBuildAlert(event, id){
    event.preventDefault();
    const value = Number(document.getElementById('build-alert-input-' + id).value);
    const errorEl = document.getElementById('build-alert-error-' + id);
    try{
      const res = await fetch(API_BASE + `/api/builds/${id}/alerte`, {
        method: 'PUT', credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ prix_cible: value }),
      });
      if(!res.ok){
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = data.detail || "L'alerte n'a pas pu être enregistrée.";
        return;
      }
      await loadBuilds();
    }catch(e){
      errorEl.textContent = 'Erreur réseau, réessaie dans un instant.';
    }
  }

  async function removeBuildAlert(id){
    try{
      await fetch(API_BASE + `/api/builds/${id}/alerte`, { method: 'DELETE', credentials: 'include' });
      await loadBuilds();
    }catch(e){
      document.getElementById('build-alert-error-' + id).textContent = 'Erreur réseau, réessaie dans un instant.';
    }
  }

  // Total actuel (prix du jour) comparé au total au moment de la sauvegarde.
  function renderBuildTotal(b){
    const total = buildCurrentTotal(b);
    if(total === null) return '';
    let delta = '';
    if(b.prix_total_sauvegarde){
      const diff = total - b.prix_total_sauvegarde;
      delta = Math.abs(diff) < 0.01
        ? '<span class="delta">stable depuis la sauvegarde</span>'
        : `<span class="delta ${diff < 0 ? 'down' : 'up'}">${diff < 0 ? '−' : '+'}${PCAccount.fmtPrice(Math.abs(diff))} depuis la sauvegarde</span>`;
    }
    return `<div class="build-total"><span class="now">${PCAccount.fmtPrice(total)}</span>${delta}</div>`;
  }

  function toggleBuildDetail(i){
    document.getElementById('detail-' + i).classList.toggle('show');
    const arrow = document.getElementById('toggle-' + i);
    arrow.classList.toggle('open', document.getElementById('detail-' + i).classList.contains('show'));
  }

  // Dépose la build à modifier en sessionStorage puis redirige vers le
  // configurateur, qui la charge et bascule "Sauvegarder" en mode mise à
  // jour (PUT) plutôt que création d'une nouvelle configuration.
  function editBuild(buildId){
    const build = lastLoadedBuilds.find(b => b.id === buildId);
    if(!build) return;
    sessionStorage.setItem('editBuild', JSON.stringify({
      id: build.id,
      nom: build.nom,
      composants_json: build.composants_json,
    }));
    window.location.href = '/configurateur';
  }

  // Dépose la build en sessionStorage puis redirige vers l'estimateur FPS,
  // qui la pré-sélectionne automatiquement (voir applyIncomingFpsBuild côté
  // estimer-fps.html) — évite d'avoir à la rechercher dans la liste "Mes
  // configurations" là-bas.
  function estimateFpsForBuild(buildId){
    const build = lastLoadedBuilds.find(b => b.id === buildId);
    if(!build) return;
    sessionStorage.setItem('fpsBuild', JSON.stringify({
      nom: build.nom,
      composants_json: build.composants_json,
    }));
    window.location.href = '/estimer-fps';
  }

  async function deleteBuild(buildId){
    const build = lastLoadedBuilds.find(b => b.id === buildId);
    if(!build) return;
    if(!await uiConfirm(`« ${build.nom} » sera supprimée définitivement. Cette action est irréversible.`,
      { title: 'Supprimer cette configuration ?', confirmLabel: 'Supprimer', danger: true })) return;

    try{
      const res = await fetch(API_BASE + `/api/builds/${buildId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if(res.ok){
        await loadBuilds();
      }else{
        const data = await res.json().catch(() => ({}));
        uiAlert(data.detail || 'Réessaie dans un instant.', { title: 'Suppression impossible' });
      }
    }catch(e){
      uiAlert('Vérifie ta connexion puis réessaie.', { title: 'Erreur réseau' });
    }
  }

  async function copyBuildLink(buildId){
    const url = window.location.origin + '/build/' + buildId;
    try{
      await navigator.clipboard.writeText(url);
      uiAlert(url, { title: 'Lien copié', tone: 'ok' });
    }catch(e){
      uiPrompt('Copie ce lien', url, { confirmLabel: 'Fermer' });
    }
  }

  // Même principe que sur le configurateur (voir configurateur.html) :
  // ajoute tous les composants de cette configuration sauvegardée au panier
  // Amazon de la personne, via /gp/aws/cart/add.html, en un seul lien.
  async function addAllToAmazonCart(buildId){
    const build = lastLoadedBuilds.find(b => b.id === buildId);
    if(!build) return;

    const items = Object.values(build.composants_json || {})
      .map(id => allComponents.find(c => c.id === id))
      .filter(item => item && item.asin);

    if(items.length === 0){
      uiAlert('Aucun composant de cette configuration n\'a de lien Amazon connu.', { title: 'Panier Amazon indisponible' });
      return;
    }

    const params = new URLSearchParams();
    if(amazonTag) params.set('AssociateTag', amazonTag);
    items.forEach((item, i) => {
      params.set(`ASIN.${i + 1}`, item.asin);
      params.set(`Quantity.${i + 1}`, '1');
    });

    const total = Object.keys(build.composants_json || {}).length;
    if(items.length < total){
      const suite = await uiConfirm(`${total - items.length} composant(s) sans lien Amazon connu ne seront pas ajoutés au panier.`,
        { title: 'Panier incomplet', confirmLabel: 'Continuer vers Amazon' });
      if(!suite) return;
    }

    window.open(`https://www.amazon.fr/gp/aws/cart/add.html?${params.toString()}`, '_blank', 'noopener');
  }

  // composants_json est de la forme { "CPU": 42, "RAM": 17, ... } (catégorie -> id).
  // On résout chaque id contre la liste complète des composants pour afficher
  // le nom, le prix, et un lien d'achat si un prix de marché est disponible.
  function renderBuildDetail(composantsJson){
    const entries = Object.entries(composantsJson || {});
    if(entries.length === 0) return '<p style="color:var(--text-dim); font-size:0.88rem;">Aucun composant enregistré.</p>';

    return entries.map(([categorie, id]) => {
      const item = allComponents.find(c => c.id === id);
      if(!item){
        return `<div class="build-detail-row"><span class="cat">${escapeHtml(categorie)}</span><span class="nom">Composant introuvable</span></div>`;
      }

      const prixMarche = (item.prix_marche || []).slice().sort((a, b) => a.prix - b.prix);
      const meilleurPrix = prixMarche[0];

      const buyBtn = meilleurPrix
        ? `<a href="${escapeHtml(withAffiliateTag(meilleurPrix.lien, meilleurPrix.vendeur))}" target="_blank" rel="noopener noreferrer sponsored" class="buy-btn">Acheter ${meilleurPrix.prix}€</a>`
        : `<a href="/comparateur" class="buy-btn" style="background:var(--border); color:var(--text-dim);">Voir prix</a>`;

      const thumbHtml = item.image_url ? `<div class="row-thumb${item.image_processed ? ' is-transparent' : ''}"><img src="${escapeHtml(item.image_url)}?w=100" alt="${escapeHtml(item.nom)}" loading="lazy" decoding="async"></div>` : '';

      return `
        <div class="build-detail-row" data-onclick="showComponentDetail(${item.id})" style="cursor:pointer;">
          <div class="item-info">
            ${thumbHtml}
            <div>
              <span class="cat">${escapeHtml(categorie)}</span>
              <span class="nom">${escapeHtml(item.nom)}</span>
            </div>
          </div>
          <span data-onclick="event.stopPropagation()">${buyBtn}</span>
        </div>
      `;
    }).join('');
  }

  // Reprend la même modale de détail (specs, description, prix, tous les
  // détails Amazon) que le configurateur et le comparateur, pour pouvoir
  // inspecter chaque composant d'une config sauvegardée sans changer de page.
  function showComponentDetail(id){
    const item = allComponents.find(c => c.id === id);
    if(!item) return;

    const specs = item.specs || {};
    const specsHtml = Object.entries(specs).map(([k, v]) => `
      <div class="detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(Array.isArray(v) ? v.join(', ') : v)}</span></div>
    `).join('') || '<p style="color:var(--text-dim); font-size:0.85rem;">Aucune spec enregistrée.</p>';

    const prixMarche = (item.prix_marche || []).slice().sort((a, b) => a.prix - b.prix);
    const pricesHtml = prixMarche.length
      ? prixMarche.map(p => `
          <div class="detail-row">
            <span class="k">${escapeHtml(p.vendeur)}</span>
            <span class="v">
              ${p.prix}€
              ${p.lien ? `<a href="${escapeHtml(withAffiliateTag(p.lien, p.vendeur))}" target="_blank" rel="noopener noreferrer sponsored" style="margin-left:8px; color:var(--led);">Voir l'offre ↗</a>` : ''}
            </span>
          </div>
        `).join('')
      : '<p style="color:var(--text-dim); font-size:0.85rem;">Aucun prix de marché relevé. Voir le <a href="/comparateur" style="color:var(--led);">comparateur</a>.</p>';

    const imageHtml = item.image_url ? `<div class="detail-image${item.image_processed ? ' is-transparent' : ''}"><img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.nom)}"></div>` : '';

    const descriptionHtml = item.description
      ? `<details style="margin-top:10px;">
          <summary style="cursor:pointer; color:var(--led); font-size:0.88rem;">Description</summary>
          <p style="color:var(--text-dim); font-size:0.88rem; margin-top:8px; line-height:1.5;">${escapeHtml(item.description)}</p>
        </details>`
      : '';

    const amazonDetails = item.caracteristiques_amazon || [];
    const amazonDetailsHtml = amazonDetails.length ? `
      <details style="margin-top:14px;">
        <summary style="cursor:pointer; color:var(--led);">Tous les détails</summary>
        <div class="detail-specs" style="margin-top:8px;">
          ${amazonDetails.map(d => `
            <div class="detail-row"><span class="k">${escapeHtml(d.type)}</span><span class="v">${escapeHtml(d.value)}</span></div>
          `).join('')}
        </div>
      </details>
    ` : '';

    document.getElementById('detail-modal-content').innerHTML = `
      <span class="cat-badge">${escapeHtml(item.categorie)}</span>
      <h2>${escapeHtml(item.nom)}</h2>
      ${item.page ? `<a class="detail-page-link" href="${escapeHtml(item.page)}">Fiche complète : prix, FPS, compatibilité <i class="ph ph-arrow-right" aria-hidden="true"></i></a>` : ''}
      ${imageHtml}
      <p class="detail-price-ref">Prix de référence : ${item.prix_indicatif}€</p>
      <div class="follow-slot"></div>
      <div class="price-history-slot"></div>
      ${descriptionHtml}
      <div class="detail-specs">${specsHtml}</div>
      <h3 style="margin-top:18px; margin-bottom:8px;">Prix relevés</h3>
      <div class="detail-prices">${pricesHtml}</div>
      ${amazonDetailsHtml}
    `;
    document.getElementById('detail-modal-overlay').classList.add('show');
    PCAccount.mountFollow(document.querySelector('#detail-modal-content .follow-slot'), item);
    if(window.PCPriceHistory) PCPriceHistory.mount(document.querySelector('#detail-modal-content .price-history-slot'), item.id);
  }

  function closeDetailModal(){
    document.getElementById('detail-modal-overlay').classList.remove('show');
    // Un suivi ajouté ou retiré depuis la fenêtre doit se refléter dans la liste.
    PCAccount.renderFavorites(document.getElementById('favorites-list'), showComponentDetail);
  }

  async function refreshView(){
    let data = { logged_in: false };
    try{
      const res = await fetch(API_BASE + '/api/auth/me', { credentials: 'include' });
      data = await res.json();
    }catch(e){
      // Réseau indisponible : on montre le formulaire plutôt qu'une page vide.
    }
    document.getElementById('account-loading').hidden = true;

    if(data.logged_in){
      document.getElementById('guest-view').style.display = 'none';
      document.getElementById('user-view').style.display = 'block';
      document.getElementById('account-email').textContent = data.user.email;
      const next = safeNext();
      if(next){ window.location.href = next; return; }
      loadBuilds();
      PCAccount.renderFavorites(document.getElementById('favorites-list'), id => {
        if(allComponents.length === 0) loadComponents().then(() => showComponentDetail(id));
        else showComponentDetail(id);
      });
    }else{
      document.getElementById('guest-view').style.display = 'block';
      document.getElementById('user-view').style.display = 'none';
    }
  }

  // ?next=/configurateur : page d'où vient l'utilisateur (ex: bouton
  // "Suivre" sans être connecté). Chemin interne uniquement.
  function safeNext(){
    const next = new URLSearchParams(window.location.search).get('next');
    return next && next.startsWith('/') && !next.startsWith('//') && next !== '/compte' ? next : null;
  }

  async function setupGoogleLogin(){
    const params = new URLSearchParams(window.location.search);
    const notice = document.getElementById('google-notice');
    const messages = {
      'erreur': "La connexion avec Google n'a pas abouti. Réessaie, ou utilise ton e-mail.",
      'non-verifie': "Ton adresse Google n'est pas vérifiée. Vérifie-la chez Google ou utilise ton e-mail.",
    };
    if(messages[params.get('google')]){
      notice.textContent = messages[params.get('google')];
      notice.hidden = false;
    }
    try{
      const providers = await fetch(API_BASE + '/api/auth/providers').then(r => r.json());
      if(providers.google){
        const next = safeNext();
        document.getElementById('google-btn').href = '/api/auth/google/login' + (next ? '?next=' + encodeURIComponent(next) : '');
        document.getElementById('google-block').hidden = false;
      }
    }catch(e){ /* bouton Google simplement masqué */ }
  }

  setupGoogleLogin();
  refreshView();
  loadAffiliateConfig();
