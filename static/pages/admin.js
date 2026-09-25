  // =====================================================================
  // Administration PC Radar
  //
  // Une page, plusieurs vues (menu de gauche) : tableau de bord, contrôle
  // « à surveiller », catalogue + tiroir d'édition, import, liens,
  // statistiques, configurations recommandées. Tous les gestionnaires
  // d'événements passent par data-on* (voir csp-handlers.js : pas de script
  // inline autorisé), d'où les fonctions globales.
  // =====================================================================

  const API_BASE = window.location.origin;
  const ADMIN_SECRET_STORAGE_KEY = 'pc_configurator_admin_secret';
  const CATEGORIES = ['CPU', 'Carte mère', 'RAM', 'GPU', 'Stockage', 'Alimentation', 'Boîtier', 'Refroidissement', 'Accessoire'];

  // Champs utilisés par le contrôle de compatibilité (miroir de schema.REQUIRED_FIELDS),
  // avec leur type pour convertir la saisie (« 5 x M.2 » -> 5, « AM4, AM5 » -> liste).
  const REQUIRED_FIELDS = {
    'CPU': { socket: 'str', tdp: 'number' },
    'Carte mère': { socket: 'str', ram_type: 'str', format: 'str', m2_slots: 'number', sata_ports: 'number' },
    'RAM': { type: 'str' },
    'Boîtier': { formats_supportes: 'list', gpu_max_length_mm: 'number', cpu_cooler_max_height_mm: 'number' },
    'Alimentation': { wattage: 'number' },
    'GPU': { tdp: 'number', longueur_mm: 'number' },
    'Stockage': { type: 'str' },
    'Refroidissement': { sockets_supportes: 'list', hauteur_mm: 'number' },
  };
  const FIELD_LABELS = {
    prix: 'prix', image: 'image', socket: 'socket', tdp: 'TDP', ram_type: 'type de RAM', format: 'format',
    m2_slots: 'slots M.2', sata_ports: 'ports SATA', type: 'type', formats_supportes: 'formats supportés',
    gpu_max_length_mm: 'longueur GPU max', cpu_cooler_max_height_mm: 'hauteur ventirad max', wattage: 'puissance',
    longueur_mm: 'longueur', sockets_supportes: 'sockets', hauteur_mm: 'hauteur',
  };

  let adminSecret = '';
  let components = [];          // catalogue complet (version admin : vraies URL d'image)
  let watchData = null;         // rapport du contrôle du catalogue
  let watchTab = 'prix';
  let brokenLinks = [];
  let corrections = [];
  let lastLinkCheck = null;
  let editing = null;           // composant ouvert dans le tiroir (null = création)
  let currentAmazonDetails = [];
  let currentAmazonDescription = null;
  let rowsShown = 150;

  // ---------------------------------------------------------------------
  // Utilitaires
  // ---------------------------------------------------------------------
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
      .replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  // Pour une chaîne placée entre apostrophes dans un data-onclick="...".
  function jsArg(str){
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }
  const euros = v => Number(v || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  const nombre = v => Number(v || 0).toLocaleString('fr-FR');
  const norm = s => (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const $ = id => document.getElementById(id);

  async function api(path, options = {}){
    const res = await fetch(API_BASE + path, {
      ...options,
      headers: { 'X-Admin-Secret': adminSecret, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if(!res.ok || data.status === 'error'){
      const details = (data.errors || []).join('\n');
      throw new Error((data.detail || data.message || ('Erreur ' + res.status)) + (details ? '\n' + details : ''));
    }
    return data;
  }
  const post = (path, body) => api(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

  let toastTimer = null;
  function toast(message, isError){
    const el = $('toast');
    el.textContent = message;
    el.className = 'toast' + (isError ? ' error' : '');
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 6000 : 2800);
  }

  // ---------------------------------------------------------------------
  // Connexion
  // ---------------------------------------------------------------------
  async function login(){
    const val = $('secret-input').value.trim();
    if(!val) return;
    $('login-btn').disabled = true;
    $('login-error').hidden = true;
    try{
      const res = await fetch(API_BASE + '/api/admin/verify', { headers: { 'X-Admin-Secret': val } });
      if(res.status === 200){
        adminSecret = val;
        try{ localStorage.setItem(ADMIN_SECRET_STORAGE_KEY, val); }catch(e){}
        startApp();
      }else{
        $('login-error').textContent = res.status === 429 ? 'Trop de tentatives, réessaie plus tard.' : 'Mot de passe incorrect.';
        $('login-error').hidden = false;
      }
    }catch(e){
      $('login-error').textContent = 'Erreur réseau : ' + e.message;
      $('login-error').hidden = false;
    }finally{
      $('login-btn').disabled = false;
    }
  }

  async function tryAutoLogin(){
    let saved = null;
    try{ saved = localStorage.getItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
    if(!saved) return;
    try{
      const res = await fetch(API_BASE + '/api/admin/verify', { headers: { 'X-Admin-Secret': saved } });
      if(res.status === 200){ adminSecret = saved; startApp(); }
      else{ try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){} }
    }catch(e){ /* formulaire de connexion laissé tel quel */ }
  }

  function logout(){
    try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
    window.location.reload();
  }

  function openSite(){ window.open('/', '_blank', 'noopener'); }

  function startApp(){
    $('login-view').hidden = true;
    $('app').hidden = false;
    $('dash-date').textContent = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    const catOptions = CATEGORIES.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    $('catalog-category').insertAdjacentHTML('beforeend', catOptions);
    $('import-category').insertAdjacentHTML('beforeend', catOptions);
    $('f-categorie').innerHTML = catOptions;
    const initial = (location.hash || '').slice(1);
    showView(document.querySelector(`[data-section="${initial}"]`) ? initial : 'dashboard');
    refreshAll();
  }

  // Tout ce qui alimente le tableau de bord, chargé en parallèle.
  async function refreshAll(){
    await Promise.allSettled([loadComponents(), loadWatch(), loadLinks(), loadStats(), loadQuotas(), loadBuilds()]);
    renderDashboard();
  }

  // ---------------------------------------------------------------------
  // Navigation entre les vues
  // ---------------------------------------------------------------------
  function showView(name){
    document.querySelectorAll('[data-section]').forEach(s => { s.hidden = s.dataset.section !== name; });
    document.querySelectorAll('.nav [data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    if(location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    window.scrollTo(0, 0);
    if(name === 'catalog') setTimeout(() => $('catalog-search').focus(), 0);
  }

  // ---------------------------------------------------------------------
  // Tableau de bord
  // ---------------------------------------------------------------------
  let statsData = null;
  let quotas = null;

  function renderDashboard(){
    const enStock = components.filter(c => c.en_stock !== false).length;
    const produits = new Set(components.map(c => c.groupe_id ?? c.id)).size;
    const suspects = watchData ? watchData.prix_suspects.length : 0;
    const aRattacher = watchData ? watchData.annonces_isolees.length : 0;
    const bd = quotas && quotas.brightdata;
    const kpi = (label, value, hint, cls = '', view = '') => `
      <${view ? `button class="kpi ${cls}" data-onclick="showView('${view}')"` : `div class="kpi ${cls}"`}>
        <span class="label">${label}</span><span class="value">${value}</span>${hint ? `<span class="hint">${hint}</span>` : ''}
      </${view ? 'button' : 'div'}>`;
    $('dash-kpis').innerHTML = [
      kpi('Visiteurs sur 7 jours', statsData ? nombre(statsData.semaine.visiteurs) : '—',
          statsData ? `${nombre(statsData.jours[statsData.jours.length - 1].visiteurs)} aujourd'hui` : '', '', 'stats'),
      kpi('Pages vues sur 7 jours', statsData ? nombre(statsData.semaine.pages_vues) : '—', '', '', 'stats'),
      kpi('Produits au catalogue', nombre(produits), `${nombre(components.length)} annonces, ${nombre(enStock)} en stock`, '', 'catalog'),
      kpi('Prix suspects', nombre(suspects), aRattacher ? `${aRattacher} annonce${aRattacher > 1 ? 's' : ''} à rattacher` : 'aucune annonce à rattacher',
          suspects ? 'is-alert' : 'is-ok', 'watch'),
      kpi('Liens morts', nombre(brokenLinks.length), lastLinkCheck ? 'vérifiés le ' + new Date(lastLinkCheck).toLocaleDateString('fr-FR') : 'pas encore vérifiés',
          brokenLinks.length ? 'is-alert' : '', 'links'),
      kpi('Corrections de liens', nombre(corrections.length), 'proposées par les visiteurs', corrections.length ? 'is-alert' : '', 'links'),
      kpi('Fiches incomplètes', watchData ? nombre(watchData.fiches_incompletes.length) : '—', 'champs de compatibilité manquants', '', 'watch'),
      bd ? `<div class="kpi"><span class="label">Bright Data ce mois-ci</span><span class="value">${nombre(bd.utilise)}<span class="faint"> / ${nombre(bd.quota)}</span></span>
            <div class="meter"><span style="width:${Math.min(100, Math.round(bd.utilise / bd.quota * 100))}%"></span></div>
            <span class="hint">${nombre(bd.ajouts_restants)} ajouts encore possibles</span></div>`
         : kpi('Bright Data ce mois-ci', '—', ''),
    ].join('');

    // « À traiter » : les signalements qui demandent une décision, avec leurs actions.
    const todo = [];
    if(watchData){
      watchData.prix_suspects.slice(0, 5).forEach(s => todo.push(priceItem(s)));
      watchData.annonces_isolees.slice(0, 3).forEach(p => todo.push(isolatedItem(p)));
    }
    brokenLinks.slice(0, 3).forEach(b => todo.push(brokenItem(b)));
    corrections.slice(0, 3).forEach(c => todo.push(correctionItem(c)));
    $('dash-todo').innerHTML = todo.join('') || '<p class="empty">Rien à traiter. Le catalogue est propre.</p>';

    const setCount = (id, n, alert) => { const el = $(id); el.textContent = n ? String(n) : ''; el.classList.toggle('alert', !!alert && n > 0); };
    setCount('nav-watch', suspects + aRattacher, true);
    setCount('nav-links', brokenLinks.length + corrections.length, true);
    setCount('nav-catalog', components.length, false);
  }

  // ---------------------------------------------------------------------
  // À surveiller
  // ---------------------------------------------------------------------
  async function loadWatch(){
    try{
      watchData = await api('/api/admin/controle-catalogue');
      const counts = { prix: watchData.prix_suspects.length, isolees: watchData.annonces_isolees.length, incompletes: watchData.fiches_incompletes.length };
      const labels = { prix: 'Prix suspects', isolees: 'Annonces à rattacher', incompletes: 'Fiches incomplètes' };
      Object.entries(counts).forEach(([k, n]) => { $('watch-tab-' + k).innerHTML = `${labels[k]}<span class="n">${n}</span>`; });
      renderWatch();
    }catch(e){
      $('watch-content').innerHTML = '<p class="empty">Contrôle indisponible pour le moment.</p>';
    }
  }

  function showWatchTab(tab){
    watchTab = tab;
    renderWatch();
  }

  function priceItem(s){
    return `<div class="item">
      <div><div class="t">${escapeHtml(s.nom)}</div>
        <div class="why"><b>${euros(s.prix)}</b> au lieu d'environ ${euros(s.reference)} · ${escapeHtml(s.motif)}</div></div>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" data-onclick="openComponent(${s.id})">Ouvrir</button>
        <button class="btn btn-danger btn-sm" data-onclick="deleteComponent(${s.id})">Supprimer</button>
        <button class="btn btn-secondary btn-sm" data-onclick="ignoreWatch('prix:${s.id}:${s.prix}')">Prix normal</button>
      </div></div>`;
  }

  function isolatedItem(p){
    const cle = `isolee:${Math.min(p.id, p.proche_id)}:${Math.max(p.id, p.proche_id)}`;
    return `<div class="item">
      <div><div class="t">${escapeHtml(p.nom)}</div>
        <div class="why">Ressemble à ${escapeHtml(p.proche_nom)}${p.proche_variantes > 1 ? ` (${p.proche_variantes} variantes)` : ''}. Même produit ?</div></div>
      <div class="actions">
        <button class="btn btn-primary btn-sm" data-onclick="attachVariant(${p.id}, ${p.proche_id})">Oui, en faire une variante</button>
        <button class="btn btn-secondary btn-sm" data-onclick="ignoreWatch('${cle}')">Non</button>
      </div></div>`;
  }

  function renderWatch(){
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.id === 'watch-tab-' + watchTab));
    if(!watchData) return;
    let html;
    if(watchTab === 'prix'){
      html = watchData.prix_suspects.map(priceItem).join('') || '<p class="empty">Aucun prix suspect.</p>';
    }else if(watchTab === 'isolees'){
      html = watchData.annonces_isolees.map(isolatedItem).join('') || '<p class="empty">Aucune annonce à rattacher.</p>';
    }else{
      html = watchData.fiches_incompletes.map(f => `<div class="item">
        <div><div class="t">${escapeHtml(f.nom)} <span class="faint">· ${escapeHtml(f.categorie)}</span></div>
          <div class="why">${f.manques.map(m => `<span class="tag">${escapeHtml(FIELD_LABELS[m] || m)}</span>`).join('')}</div></div>
        <div class="actions"><button class="btn btn-secondary btn-sm" data-onclick="openComponent(${f.id})">Compléter</button></div>
      </div>`).join('') || '<p class="empty">Toutes les fiches sont complètes.</p>';
    }
    $('watch-content').innerHTML = html;
  }

  async function ignoreWatch(cle){
    try{ await post('/api/admin/controle/ignorer', { cle }); toast('Signalement ignoré.'); await refreshAll(); }
    catch(e){ toast(e.message, true); }
  }

  async function attachVariant(id, cible){
    try{ await post('/api/admin/variantes/rattacher', { id, cible }); toast('Rattaché comme variante.'); await refreshAll(); }
    catch(e){ toast(e.message, true); }
  }

  // ---------------------------------------------------------------------
  // Catalogue
  // ---------------------------------------------------------------------
  async function loadComponents(){
    try{
      const data = await api('/api/admin/components');
      components = Object.values(data.components || {}).flat();
      $('spec-keys').innerHTML = [...new Set(components.flatMap(c => Object.keys(parseSpecs(c))))].sort()
        .map(k => `<option value="${escapeHtml(k)}">`).join('');
      renderCatalog();
    }catch(e){
      $('catalog-rows').innerHTML = `<tr><td colspan="5" class="empty">Catalogue indisponible : ${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function parseSpecs(c){
    if(c.specs && typeof c.specs === 'object') return c.specs;
    try{ return JSON.parse(c.specs_json || '{}') || {}; }catch(e){ return {}; }
  }

  function filteredComponents(){
    const q = norm($('catalog-search').value.trim()).split(/\s+/).filter(Boolean);
    const cat = $('catalog-category').value;
    const f = $('catalog-filter').value;
    return components.filter(c => {
      if(cat && c.categorie !== cat) return false;
      if(f === 'stock' && c.en_stock === false) return false;
      if(f === 'epuise' && c.en_stock !== false) return false;
      if(f === 'suspect' && !c.prix_suspect) return false;
      if(f === 'variantes' && !(c.nb_variantes > 1)) return false;
      if(f === 'sans-image' && c.image_url) return false;
      if(q.length){
        const hay = norm(`${c.nom} ${c.asin || ''} ${c.id}`);
        if(!q.every(t => hay.includes(t))) return false;
      }
      return true;
    }).sort((a, b) => a.categorie.localeCompare(b.categorie) || a.nom.localeCompare(b.nom));
  }

  function renderCatalog(){
    const list = filteredComponents();
    $('catalog-summary').textContent = `${nombre(list.length)} annonce${list.length > 1 ? 's' : ''} affichée${list.length > 1 ? 's' : ''} sur ${nombre(components.length)}`;
    $('catalog-rows').innerHTML = list.slice(0, rowsShown).map(c => {
      const thumb = c.image_url
        ? `<div class="thumb${String(c.image_url).startsWith('data:') ? ' transparent' : ''}"><img src="/api/components/${c.id}/image?w=80" alt="" loading="lazy"></div>`
        : '<div class="thumb none"><i class="ph ph-image"></i></div>';
      const tags = [
        c.en_stock === false ? '<span class="tag">Épuisé</span>' : '<span class="tag ok">En stock</span>',
        c.prix_suspect ? '<span class="tag danger">Prix suspect</span>' : '',
      ].join('');
      return `<tr class="${editing && editing.id === c.id ? 'active' : ''}" data-onclick="openComponent(${c.id})">
        <td>${thumb}</td>
        <td><div class="name">${escapeHtml(c.nom)}</div>${c.nb_variantes > 1 ? `<div class="faint">${escapeHtml(c.variante || '')} · ${c.nb_variantes} variantes</div>` : ''}</td>
        <td class="hide-sm muted">${escapeHtml(c.categorie)}</td>
        <td class="num">${c.prix_indicatif ? euros(c.prix_indicatif) : '<span class="muted">—</span>'}</td>
        <td class="hide-sm">${tags}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5" class="empty" style="padding:18px 12px;">Aucun produit ne correspond.</td></tr>';
    $('catalog-more').hidden = list.length <= rowsShown;
  }

  function showMoreRows(){ rowsShown += 300; renderCatalog(); }

  // ---------------------------------------------------------------------
  // Tiroir d'édition
  // ---------------------------------------------------------------------
  function openDrawer(){
    $('drawer').hidden = false;
    $('drawer-backdrop').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer(){
    $('drawer').hidden = true;
    $('drawer-backdrop').hidden = true;
    document.body.style.overflow = '';
    editing = null;
    renderCatalog();
  }

  function setNote(text, kind){
    const el = $('drawer-note');
    if(!text){ el.hidden = true; return; }
    el.className = 'note' + (kind ? ' ' + kind : '');
    el.textContent = text;
    el.hidden = false;
  }

  function openComponent(id){
    const c = components.find(x => x.id === id);
    if(!c){ toast('Produit introuvable (peut-être supprimé).', true); return; }
    editing = c;
    currentAmazonDetails = c.caracteristiques_amazon || [];
    currentAmazonDescription = c.description || null;
    $('drawer-title').textContent = c.nom;
    $('drawer-page').hidden = !c.page;
    if(c.page) $('drawer-page').href = c.page;
    $('f-nom').value = c.nom;
    $('f-categorie').value = c.categorie;
    $('f-prix').value = c.prix_indicatif ?? '';
    $('f-asin').value = c.asin || '';
    $('f-image').value = c.image_url || '';
    $('f-specs').innerHTML = '';
    Object.entries(parseSpecs(c)).forEach(([k, v]) => addSpecRow(k, Array.isArray(v) ? v.join(', ') : v));
    $('f-prices').innerHTML = '';
    (c.prix_marche || []).forEach(p => addPriceRow(p));
    $('f-delete').hidden = false;
    $('f-regen').hidden = !c.asin;
    $('f-separate').hidden = !(c.nb_variantes > 1);
    const notes = [];
    if(c.nb_variantes > 1) notes.push(`Variante « ${c.variante || ''} » d'un produit à ${c.nb_variantes} annonces.`);
    if(c.prix_suspect) notes.push('Prix signalé suspect par le contrôle du catalogue.');
    setNote(notes.join(' '), c.prix_suspect ? 'error' : '');
    renderRequiredHint();
    updatePreview();
    openDrawer();
    renderCatalog();
  }

  function openNewComponent(){
    editing = null;
    currentAmazonDetails = [];
    currentAmazonDescription = null;
    $('drawer-title').textContent = 'Nouveau composant';
    $('drawer-page').hidden = true;
    ['f-nom', 'f-prix', 'f-asin', 'f-image'].forEach(id => { $(id).value = ''; });
    $('f-categorie').value = $('catalog-category').value || 'CPU';
    $('f-specs').innerHTML = '';
    $('f-prices').innerHTML = '';
    $('f-delete').hidden = true;
    $('f-regen').hidden = true;
    $('f-separate').hidden = true;
    setNote('Astuce : renseigne l\'ASIN puis « Reprendre depuis Amazon » pour tout remplir automatiquement.');
    renderRequiredHint();
    updatePreview();
    openDrawer();
  }

  // Ajoute les champs de compatibilité manquants de la catégorie (vides, à remplir).
  function renderRequiredHint(){
    const required = Object.keys(REQUIRED_FIELDS[$('f-categorie').value] || {});
    const present = new Set([...document.querySelectorAll('#f-specs .s-key')].map(i => i.value.trim()));
    required.filter(k => !present.has(k)).forEach(k => addSpecRow(k, ''));
    document.querySelectorAll('#f-specs .kv-row').forEach(row => {
      row.classList.toggle('required', required.includes(row.querySelector('.s-key').value.trim()));
    });
    $('f-required').textContent = required.length
      ? 'En vert : champs utilisés par le contrôle de compatibilité (' + required.map(k => FIELD_LABELS[k] || k).join(', ') + ').'
      : 'Aucun champ obligatoire pour cette catégorie.';
  }

  function addSpecRow(key, value){
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.innerHTML = `<input type="text" class="s-key" list="spec-keys" placeholder="champ (ex : socket)" value="${escapeHtml(key)}">
      <input type="text" class="s-value" placeholder="valeur (liste : a, b, c)" value="${escapeHtml(value)}">
      <button class="icon-btn" data-onclick="this.parentElement.remove()" title="Retirer"><i class="ph ph-x"></i></button>`;
    $('f-specs').appendChild(row);
  }

  function addPriceRow(p){
    const row = document.createElement('div');
    row.className = 'price-row';
    row.dataset.date = p?.date_releve || '';
    row.innerHTML = `<input type="text" class="p-vendeur" placeholder="Marchand" value="${escapeHtml(p?.vendeur || '')}">
      <input type="number" class="p-prix mono" step="0.01" placeholder="Prix" value="${p?.prix ?? ''}">
      <input type="text" class="p-lien" placeholder="Lien" value="${escapeHtml(p?.lien || '')}">
      <button class="icon-btn" data-onclick="this.parentElement.remove()" title="Retirer"><i class="ph ph-x"></i></button>`;
    $('f-prices').appendChild(row);
  }

  function updatePreview(){
    const url = $('f-image').value.trim();
    const box = $('f-preview');
    box.classList.toggle('transparent', url.startsWith('data:'));
    box.innerHTML = url ? `<img src="${escapeHtml(url)}" alt="">` : '<i class="ph ph-image muted"></i>';
  }

  function parseSpecValue(raw, type){
    const v = (raw || '').trim();
    if(v === '') return '';
    if(type === 'number'){ const m = v.match(/-?\d+(\.\d+)?/); return m ? Number(m[0]) : v; }
    if(type === 'list' || v.includes(',')) return v.split(',').map(x => x.trim()).filter(Boolean);
    if(type !== 'str' && !isNaN(v)) return Number(v);
    return v;
  }

  async function saveComponent(){
    const categorie = $('f-categorie').value;
    const types = REQUIRED_FIELDS[categorie] || {};
    const specs = {};
    document.querySelectorAll('#f-specs .kv-row').forEach(row => {
      const key = row.querySelector('.s-key').value.trim();
      const value = parseSpecValue(row.querySelector('.s-value').value, types[key]);
      if(key && value !== '') specs[key] = value;
    });
    // lien_mort / dernier_check (vérification automatique) gardés tant que le lien ne change pas.
    const original = {};
    (editing?.prix_marche || []).forEach(p => { original[p.vendeur] = p; });
    const today = new Date().toISOString().slice(0, 10);
    const prix_marche = [...document.querySelectorAll('#f-prices .price-row')].map(row => {
      const vendeur = row.querySelector('.p-vendeur').value.trim();
      const lien = row.querySelector('.p-lien').value.trim();
      const prix = Number(row.querySelector('.p-prix').value);
      const o = original[vendeur];
      const entry = { vendeur, prix, lien, date_releve: (o && o.prix === prix && row.dataset.date) || today };
      if(o && o.lien === lien){
        if('lien_mort' in o) entry.lien_mort = o.lien_mort;
        if('dernier_check' in o) entry.dernier_check = o.dernier_check;
      }
      return entry;
    }).filter(p => p.vendeur && p.lien);
    const prixRaw = $('f-prix').value;
    const payload = {
      categorie, nom: $('f-nom').value.trim(), prix_indicatif: prixRaw === '' ? null : Number(prixRaw),
      specs, prix_marche, image_url: $('f-image').value.trim() || null, asin: $('f-asin').value.trim() || null,
      caracteristiques_amazon: currentAmazonDetails, description: currentAmazonDescription,
    };
    $('f-save').disabled = true;
    try{
      if(editing){
        await api(`/api/admin/components/${editing.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      }else{
        await post('/api/admin/components', { components: [payload] });
      }
      toast('Enregistré.');
      const id = editing?.id;
      await loadComponents();
      const saved = id ? components.find(c => c.id === id) : components.find(c => c.categorie === categorie && c.nom === payload.nom);
      if(saved) openComponent(saved.id);
      loadWatch().then(renderDashboard);
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-save').disabled = false;
    }
  }

  async function deleteComponent(id){
    const c = components.find(x => x.id === id);
    if(!confirm(`Supprimer définitivement « ${c ? c.nom : id} » ? Les configurations qui l'utilisent le perdront.`)) return;
    try{
      await api(`/api/admin/components/${id}`, { method: 'DELETE' });
      toast('Supprimé.');
      if(editing && editing.id === id) closeDrawer();
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  function deleteCurrent(){ if(editing) deleteComponent(editing.id); }

  async function separateCurrent(){
    if(!editing || !confirm(`Sortir « ${editing.nom} » de son produit (il redevient une fiche à part) ?`)) return;
    try{
      await post('/api/admin/variantes/separer', { id: editing.id });
      toast('Séparé de ses variantes.');
      const id = editing.id;
      await refreshAll();
      openComponent(id);
    }catch(e){ toast(e.message, true); }
  }

  // Reprend nom (si vide), prix, image et caractéristiques depuis Amazon ; rien n'est
  // enregistré tant que « Enregistrer » n'est pas cliqué.
  async function refetchFromAmazon(){
    const asin = $('f-asin').value.trim();
    if(!asin){ setNote('Renseigne d\'abord l\'ASIN (ou colle un lien Amazon).', 'error'); return; }
    const categorie = $('f-categorie').value;
    $('f-refetch').disabled = true;
    setNote('Récupération depuis Amazon…');
    try{
      const d = await post('/api/admin/fetch-asin', { asin, categorie });
      $('f-asin').value = d.asin;
      if(!$('f-nom').value.trim() && d.nom) $('f-nom').value = d.nom;
      if(d.prix != null) $('f-prix').value = d.prix;
      if(d.image_url){ $('f-image').value = d.image_url; updatePreview(); }
      if(d.prix != null && d.lien){
        document.querySelectorAll('#f-prices .price-row').forEach(r => { if(r.querySelector('.p-vendeur').value.trim() === 'Amazon') r.remove(); });
        addPriceRow({ vendeur: 'Amazon', prix: d.prix, lien: d.lien, date_releve: new Date().toISOString().slice(0, 10) });
      }
      const present = {};
      document.querySelectorAll('#f-specs .kv-row').forEach(r => { present[r.querySelector('.s-key').value.trim()] = r; });
      Object.entries(d.specs || {}).forEach(([k, v]) => {
        if(v === null || v === undefined || v === '') return;
        const val = Array.isArray(v) ? v.join(', ') : v;
        if(present[k]){ if(!present[k].querySelector('.s-value').value.trim()) present[k].querySelector('.s-value').value = val; }
        else addSpecRow(k, val);
      });
      currentAmazonDetails = Array.isArray(d.caracteristiques_amazon) ? d.caracteristiques_amazon : currentAmazonDetails;
      currentAmazonDescription = d.description || currentAmazonDescription;
      renderRequiredHint();
      setNote('Données Amazon reprises. Vérifie puis clique « Enregistrer ».', 'ok');
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-refetch').disabled = false;
    }
  }

  // Nouvelle photo Amazon pour cet ASIN (enregistrée tout de suite, détourée ensuite
  // automatiquement par la surveillance locale).
  async function regenerateImage(){
    if(!editing) return;
    $('f-regen').disabled = true;
    try{
      const d = await post(`/api/admin/components/${editing.id}/regenerate-image`);
      $('f-image').value = d.image_url;
      updatePreview();
      setNote('Nouvelle photo enregistrée. Elle sera détourée automatiquement d\'ici une vingtaine de secondes.', 'ok');
      loadComponents();
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-regen').disabled = false;
    }
  }

  // ---------------------------------------------------------------------
  // Import (ASIN, liens Amazon ou noms, un par ligne)
  // ---------------------------------------------------------------------
  let importState = null;

  async function importOne(entry, signal, forcedCategorie){
    const d = await api('/api/admin/fetch-asin', { method: 'POST', signal, body: JSON.stringify(forcedCategorie ? { asin: entry, categorie: forcedCategorie } : { asin: entry }) });
    const categorie = forcedCategorie || d.categorie;
    if(!categorie) return { ok: false, text: `${entry} : catégorie non reconnue, choisis-la dans la liste et relance.` };
    const payload = {
      categorie, nom: d.nom || `${categorie} (ASIN ${d.asin})`, prix_indicatif: d.prix != null ? d.prix : 0,
      specs: d.specs || {},
      prix_marche: (d.prix != null && d.lien) ? [{ vendeur: 'Amazon', prix: d.prix, lien: d.lien, date_releve: new Date().toISOString().slice(0, 10) }] : [],
      image_url: d.image_url || null, asin: d.asin,
      caracteristiques_amazon: Array.isArray(d.caracteristiques_amazon) ? d.caracteristiques_amazon : [],
      description: d.description || null,
    };
    await api('/api/admin/components', { method: 'POST', body: JSON.stringify({ components: [payload] }), signal });
    return { ok: true, text: `${payload.nom} · ${categorie} · ${d.prix == null ? 'prix introuvable (mis à 0 €)' : euros(d.prix)}` };
  }

  async function startImport(){
    const entries = $('import-input').value.split(/\r?\n|,/).map(s => s.trim()).filter(Boolean);
    if(!entries.length){ toast('Colle au moins un ASIN, lien ou nom de produit.', true); return; }
    const forced = $('import-category').value || null;
    const log = $('import-log');
    const bar = $('import-progress');
    log.innerHTML = '';
    bar.hidden = false;
    bar.firstElementChild.style.transform = 'scaleX(0)';
    $('import-btn').disabled = true;
    $('import-pause').hidden = false;
    $('import-cancel').hidden = false;
    $('import-pause').textContent = 'Pause';
    importState = { paused: false, cancelled: false, controller: new AbortController() };
    let next = 0, done = 0, ok = 0;
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    // 2 imports en parallèle : au-delà, le nettoyage des titres par IA et le détourage
    // des images (ressources partagées modestes) deviennent le goulot.
    async function worker(){
      while(next < entries.length && !importState.cancelled){
        if(importState.paused){ await sleep(300); continue; }
        const entry = entries[next++];
        let outcome;
        try{ outcome = await importOne(entry, importState.controller.signal, forced); }
        catch(e){ outcome = { ok: false, text: `${entry} : ${importState.cancelled ? 'annulé' : e.message}` }; }
        done++;
        if(outcome.ok) ok++;
        log.insertAdjacentHTML('beforeend', `<li class="${outcome.ok ? 'ok' : 'ko'}"><i class="ph ph-${outcome.ok ? 'check-circle' : 'x-circle'}"></i><span>${escapeHtml(outcome.text)}</span></li>`);
        bar.firstElementChild.style.transform = `scaleX(${done / entries.length})`;
      }
    }
    await Promise.all([worker(), worker()]);
    const cancelled = importState.cancelled;
    importState = null;
    $('import-btn').disabled = false;
    $('import-pause').hidden = true;
    $('import-cancel').hidden = true;
    toast(cancelled ? `Import annulé (${ok} ajouté${ok > 1 ? 's' : ''}).` : `${ok} produit${ok > 1 ? 's' : ''} sur ${entries.length} ajouté${ok > 1 ? 's' : ''}.`, ok < done);
    if(!cancelled && ok === entries.length) $('import-input').value = '';
    refreshAll();
  }

  function pauseImport(){
    if(!importState) return;
    importState.paused = !importState.paused;
    $('import-pause').textContent = importState.paused ? 'Reprendre' : 'Pause';
  }

  function cancelImport(){
    if(!importState) return;
    importState.cancelled = true;
    importState.controller.abort();
  }

  async function loadQuotas(){
    try{
      quotas = await api('/api/admin/quotas');
      const q = quotas.brightdata;
      $('quota-info').textContent = `Bright Data : ${nombre(q.ajouts_restants)} ajouts encore possibles ce mois-ci.`;
    }catch(e){ quotas = null; }
  }

  // ---------------------------------------------------------------------
  // Liens morts et corrections proposées
  // ---------------------------------------------------------------------
  function brokenItem(b){
    return `<div class="item">
      <div><div class="t">${escapeHtml(b.nom)} <span class="faint">· ${escapeHtml(b.vendeur)}</span></div>
        <div class="why"><a href="${escapeHtml(b.lien)}" target="_blank" rel="noopener noreferrer">${escapeHtml(b.lien)}</a></div></div>
      <div class="actions">
        <button class="btn btn-secondary btn-sm" data-onclick="fixBrokenLink(${b.component_id}, '${jsArg(b.vendeur)}', '${jsArg(b.lien)}')">Remplacer le lien</button>
        <button class="btn btn-ghost btn-sm" data-onclick="openComponent(${b.component_id})">Ouvrir</button>
      </div></div>`;
  }

  function correctionItem(c){
    return `<div class="item">
      <div><div class="t">${escapeHtml(c.component_nom)} <span class="faint">· ${escapeHtml(c.vendeur)} · ${escapeHtml(c.user_email)}, le ${new Date(c.date).toLocaleDateString('fr-FR')}</span></div>
        ${c.ancien_lien ? `<div class="link-old">${escapeHtml(c.ancien_lien)}</div>` : ''}
        <div class="link-new">${escapeHtml(c.nouveau_lien)}</div></div>
      <div class="actions">
        <button class="btn btn-primary btn-sm" data-onclick="reviewCorrection(${c.id}, 'approve')">Approuver</button>
        <button class="btn btn-danger btn-sm" data-onclick="reviewCorrection(${c.id}, 'reject')">Rejeter</button>
      </div></div>`;
  }

  async function loadLinks(){
    try{
      const d = await api('/api/admin/broken-links');
      brokenLinks = d.broken_links || [];
      const s = d.check_status;
      lastLinkCheck = s && s.dernier_lancement;
      $('links-status').textContent = lastLinkCheck
        ? `Dernière vérification le ${new Date(lastLinkCheck).toLocaleString('fr-FR')} : ${nombre(s.liens_testes)} liens testés, ${nombre(s.liens_non_verifiables)} non vérifiables (protection anti-robot d'Amazon)`
          + (s.liens_corriges_auto ? `, ${nombre(s.liens_corriges_auto)} corrigés automatiquement` : '') + '.'
        : 'Vérifiés automatiquement une fois par jour.';
      $('broken-links').innerHTML = brokenLinks.map(brokenItem).join('') || '<p class="empty">Aucun lien confirmé mort.</p>';
    }catch(e){
      $('broken-links').innerHTML = '<p class="empty">Liste indisponible.</p>';
    }
    try{
      const d = await api('/api/admin/link-corrections');
      corrections = d.corrections || [];
      $('link-corrections').innerHTML = corrections.map(correctionItem).join('') || '<p class="empty">Aucune correction en attente.</p>';
    }catch(e){
      $('link-corrections').innerHTML = '<p class="empty">Liste indisponible.</p>';
    }
  }

  async function fixBrokenLink(componentId, vendeur, ancienLien){
    const nouveau = prompt(`Nouveau lien ${vendeur} :`, ancienLien);
    if(!nouveau || nouveau === ancienLien) return;
    try{
      await post('/api/admin/fix-link', { component_id: componentId, vendeur, nouveau_lien: nouveau });
      toast('Lien remplacé.');
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  async function reviewCorrection(id, action){
    try{
      await post(`/api/admin/link-corrections/${id}/${action}`);
      toast(action === 'approve' ? 'Correction appliquée.' : 'Correction rejetée.');
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  // Lancée en arrière-plan côté serveur ; on sonde jusqu'à ce que la date de
  // dernière vérification change (un gros catalogue dépasse le délai d'une requête).
  async function checkLinksNow(){
    const btn = $('check-links-btn');
    btn.disabled = true;
    const before = lastLinkCheck;
    $('links-status').textContent = 'Vérification en cours, ça peut prendre plusieurs minutes…';
    try{
      await post('/api/admin/check-links');
      for(let i = 0; i < 72; i++){
        await new Promise(r => setTimeout(r, 5000));
        await loadLinks();
        if(lastLinkCheck && lastLinkCheck !== before) break;
      }
      renderDashboard();
    }catch(e){ toast(e.message, true); }
    finally{ btn.disabled = false; }
  }

  // ---------------------------------------------------------------------
  // Statistiques
  // ---------------------------------------------------------------------
  async function loadStats(){
    try{
      statsData = await api('/api/admin/stats');
      renderStats();
    }catch(e){
      statsData = null;
      $('stats-content').innerHTML = '<p class="empty">Statistiques indisponibles pour le moment.</p>';
    }
  }

  // Graduation « ronde » au-dessus du maximum (10, 20, 50, 100, 200…).
  function niceMax(v){
    if(v <= 4) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const step = [1, 2, 2.5, 5, 10].find(s => s * p * 4 >= v) * p;
    return step * 4;
  }

  function renderStats(){
    const s = statsData;
    const jours = s.jours;
    const today = jours[jours.length - 1];
    const moyenne = Math.round(jours.slice(-7).reduce((a, j) => a + j.visiteurs, 0) / 7);
    const pagesParVisiteur = s.semaine.visiteurs ? (s.semaine.pages_vues / s.semaine.visiteurs) : 0;
    const max = niceMax(Math.max(1, ...jours.map(j => j.visiteurs)));
    const axis = [4, 3, 2, 1, 0].map(i => `<span>${nombre(max * i / 4)}</span>`).join('');
    const bars = jours.map((j, i) => `
      <div class="bar${i === jours.length - 1 ? ' is-today' : ''}" title="${new Date(j.date).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })} : ${j.visiteurs} visiteurs, ${j.pages_vues} pages vues">
        <div class="fill" style="height:calc((100% - 22px) * ${j.visiteurs / max})"></div>
        <small>${j.date.slice(8, 10)}</small>
      </div>`).join('');
    const rank = (rows, label, value) => {
      if(!rows.length) return '<p class="empty">Pas encore de données.</p>';
      const top = Math.max(...rows.map(r => r[value]));
      return `<ul class="rank">${rows.map(r => `<li><div class="bg" style="width:${Math.round(r[value] / top * 100)}%"></div>
        <span title="${escapeHtml(r[label])}">${escapeHtml(r[label])}</span><b>${nombre(r[value])}</b></li>`).join('')}</ul>`;
    };
    const total = Object.values(s.appareils).reduce((a, b) => a + b, 0) || 1;
    const shades = ['var(--accent)', '#2a9d6b', 'var(--line-strong)', 'var(--text-3)'];
    const devices = Object.entries(s.appareils).sort((a, b) => b[1] - a[1]);
    $('stats-content').innerHTML = `
      <div class="kpis">
        <div class="kpi"><span class="label">Visiteurs sur 7 jours</span><span class="value">${nombre(s.semaine.visiteurs)}</span><span class="hint">${nombre(moyenne)} par jour en moyenne</span></div>
        <div class="kpi"><span class="label">Pages vues sur 7 jours</span><span class="value">${nombre(s.semaine.pages_vues)}</span><span class="hint">${pagesParVisiteur.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} pages par visiteur</span></div>
        <div class="kpi"><span class="label">Visiteurs aujourd'hui</span><span class="value">${nombre(today.visiteurs)}</span><span class="hint">${nombre(today.pages_vues)} pages vues</span></div>
        <div class="kpi"><span class="label">Meilleur jour (14 j)</span><span class="value">${nombre(Math.max(...jours.map(j => j.visiteurs)))}</span>
          <span class="hint">${new Date(jours.reduce((a, j) => j.visiteurs > a.visiteurs ? j : a).date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })}</span></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Visiteurs par jour</h3><div class="legend"><span><i style="background:var(--accent)"></i>Visiteurs uniques</span></div></div>
        <div class="chart"><div class="chart-axis">${axis}</div><div class="chart-bars">${bars}</div></div>
      </div>
      <div class="grid-2">
        <div class="panel" style="margin:0;"><div class="panel-head"><h3>Pages les plus vues</h3><span class="faint">7 jours</span></div>${rank(s.pages, 'page', 'vues')}</div>
        <div class="panel" style="margin:0;">
          <div class="panel-head"><h3>Provenance</h3><span class="faint">7 jours</span></div>${rank(s.provenance, 'source', 'visites')}
          <div class="panel-head" style="margin:18px 0 0;"><h3>Appareils</h3></div>
          <div class="devices">${devices.map(([k, v], i) => `<span style="width:${v / total * 100}%; background:${shades[i % shades.length]}" title="${escapeHtml(k)}"></span>`).join('')}</div>
          <div class="devices-legend">${devices.map(([k, v], i) => `<span><i style="background:${shades[i % shades.length]}"></i>${escapeHtml(k)} ${Math.round(v / total * 100)} %</span>`).join('') || '<span>—</span>'}</div>
        </div>
      </div>`;
  }

  // ---------------------------------------------------------------------
  // Configurations recommandées
  // ---------------------------------------------------------------------
  async function loadBuilds(){
    try{
      const d = await api('/api/admin/builds');
      const builds = (d.builds || []).slice().sort((a, b) => (b.est_officielle ? 1 : 0) - (a.est_officielle ? 1 : 0));
      $('builds-list').innerHTML = builds.map(b => `<div class="item">
        <div><div class="t">${escapeHtml(b.nom)} ${b.est_officielle ? '<span class="tag ok">Recommandée</span>' : ''}</div>
          <div class="why">${escapeHtml(b.user_email || 'anonyme')} · ${new Date(b.date).toLocaleDateString('fr-FR')}</div></div>
        <div class="actions">
          <a class="btn btn-ghost btn-sm" href="/build/${b.id}" target="_blank" rel="noopener">Voir</a>
          <button class="btn ${b.est_officielle ? 'btn-secondary' : 'btn-primary'} btn-sm" data-onclick="toggleOfficialBuild(${b.id})">${b.est_officielle ? 'Retirer' : 'Mettre en avant'}</button>
        </div></div>`).join('') || '<p class="empty">Aucune configuration sauvegardée pour l\'instant.</p>';
    }catch(e){
      $('builds-list').innerHTML = '<p class="empty">Liste indisponible.</p>';
    }
  }

  async function toggleOfficialBuild(id){
    try{ await post(`/api/admin/builds/${id}/toggle-officielle`); await loadBuilds(); }
    catch(e){ toast(e.message, true); }
  }

  // ---------------------------------------------------------------------
  // Raccourcis et écouteurs
  // ---------------------------------------------------------------------
  ['catalog-search', 'catalog-category', 'catalog-filter'].forEach(id => {
    $(id).addEventListener(id === 'catalog-search' ? 'input' : 'change', () => { rowsShown = 150; renderCatalog(); });
  });
  document.addEventListener('keydown', e => {
    if(e.key === 'Escape' && !$('drawer').hidden){ closeDrawer(); return; }
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if(e.key === '/' && !typing && !$('app').hidden){
      e.preventDefault();
      showView('catalog');
    }
    if((e.ctrlKey || e.metaKey) && e.key === 's' && !$('drawer').hidden){
      e.preventDefault();
      saveComponent();
    }
  });
  window.addEventListener('hashchange', () => {
    const name = location.hash.slice(1);
    if(document.querySelector(`[data-section="${name}"]`)) showView(name);
  });

  tryAutoLogin();
