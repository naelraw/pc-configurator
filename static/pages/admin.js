  const API_BASE = window.location.origin;
  let adminSecret = '';
  let lastKnownCheckTimestamp = null;

  const ADMIN_SECRET_STORAGE_KEY = 'pc_configurator_admin_secret';

  // Réduit/agrandit le contenu d'un bloc admin — chaque carte a un bouton
  // ▾/▸ dans son en-tête. Purement visuel, aucun état à sauvegarder.
  function toggleCardBody(btn){
    const card = btn.closest('.card');
    const body = card?.querySelector('.card-body');
    if(!body) return;
    const collapsed = body.classList.toggle('hidden');
    btn.textContent = collapsed ? '▸' : '▾';
  }

  // Quota Bright Data du mois : les ajouts de composants ont une réserve
  // dédiée que la mise à jour quotidienne des prix ne peut pas consommer.
  async function loadQuotas(){
    const el = document.getElementById('quota-info');
    try{
      const res = await fetch(API_BASE + '/api/admin/quotas', { headers: { 'X-Admin-Secret': adminSecret } });
      if(!res.ok) return;
      const q = (await res.json()).brightdata;
      el.textContent = `Bright Data ce mois-ci : ${q.utilise} / ${q.quota} fiches utilisées. `
        + `Ajouts de composants encore possibles : ${q.ajouts_restants} `
        + `(dont ${q.reserve_ajouts} réservés, que la mise à jour des prix ne touche pas).`;
    }catch(e){ /* compteur simplement masqué */ }
  }

  function revealAdminUI(){
    document.getElementById('login-card').classList.add('hidden');
    document.getElementById('browse-card').classList.remove('hidden');
    document.getElementById('edit-card').classList.remove('hidden');
    document.getElementById('link-check-controls').classList.remove('hidden');
    document.getElementById('link-corrections-card').classList.remove('hidden');
    document.getElementById('recommended-builds-card').classList.remove('hidden');
    document.getElementById('logout-btn').classList.remove('hidden');
    loadAllComponentsForEdit();
    loadBrokenLinksBanner();
    loadLinkCorrections();
    loadAdminBuilds();
    loadQuotas();
    // Faire apparaître/disparaître toutes ces cartes d'un coup change
    // beaucoup la hauteur de page — sans ça, la page peut rester scrollée
    // au milieu/en bas là où elle était pendant l'écran de connexion.
    window.scrollTo(0, 0);
  }

  async function login(){
    const val = document.getElementById('secret-input').value.trim();
    const loginBtn = document.getElementById('login-btn');
    const loginResult = document.getElementById('login-result');
    if(!val) return;

    loginBtn.disabled = true;
    loginResult.classList.add('hidden');

    try{
      const res = await fetch(API_BASE + '/api/admin/verify', {
        headers: { 'X-Admin-Secret': val },
      });

      if(res.status === 200){
        adminSecret = val;
        // Mémorisé dans ce navigateur pour ne pas avoir à le retaper à
        // chaque visite — même niveau de sécurité que le mot de passe admin
        // lui-même (un secret partagé envoyé en clair dans un header), donc
        // pas de recul de sécurité à le garder côté client.
        try{ localStorage.setItem(ADMIN_SECRET_STORAGE_KEY, val); }catch(e){}
        revealAdminUI();
      }else{
        loginResult.className = 'result error';
        loginResult.classList.remove('hidden');
        loginResult.textContent = 'Mot de passe incorrect.';
      }
    }catch(e){
      loginResult.className = 'result error';
      loginResult.classList.remove('hidden');
      loginResult.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      loginBtn.disabled = false;
    }
  }

  // Reconnexion automatique si un mot de passe valide est déjà mémorisé
  // dans ce navigateur — sinon on retombe simplement sur le formulaire.
  async function tryAutoLogin(){
    let saved;
    try{ saved = localStorage.getItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){ saved = null; }
    if(!saved) return;

    try{
      const res = await fetch(API_BASE + '/api/admin/verify', {
        headers: { 'X-Admin-Secret': saved },
      });
      if(res.status === 200){
        adminSecret = saved;
        revealAdminUI();
      }else{
        try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
      }
    }catch(e){
      // Erreur réseau au chargement : on laisse simplement le formulaire de
      // connexion, l'utilisateur peut réessayer manuellement.
    }
  }

  function logout(){
    adminSecret = '';
    try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
    window.location.reload();
  }

  tryAutoLogin();

  // --- Catalogue complet : parcours, édition et suppression ---

  const REQUIRED_SPECS_BY_CATEGORY = {
    'CPU': ['socket', 'tdp'],
    'Carte mère': ['socket', 'ram_type', 'format', 'm2_slots', 'sata_ports'],
    'RAM': ['type'],
    'Boîtier': ['formats_supportes', 'gpu_max_length_mm', 'cpu_cooler_max_height_mm'],
    'Alimentation': ['wattage'],
    'GPU': ['tdp', 'longueur_mm'],
    'Stockage': ['type'],
    'Refroidissement': ['sockets_supportes', 'hauteur_mm'],
  };

  // Type attendu de chaque champ requis (miroir de schema.REQUIRED_FIELDS
  // côté serveur) — sert uniquement à parser correctement la valeur saisie
  // (ex: extraire "5" d'un texte collé comme "5 x M.2"), jamais à valider :
  // la validation stricte reste faite côté serveur.
  const SPEC_FIELD_TYPES = {
    'CPU': { socket: 'str', tdp: 'number' },
    'Carte mère': { socket: 'str', ram_type: 'str', format: 'str', m2_slots: 'number', sata_ports: 'number' },
    'RAM': { type: 'str' },
    'Boîtier': { formats_supportes: 'list', gpu_max_length_mm: 'number', cpu_cooler_max_height_mm: 'number' },
    'Alimentation': { wattage: 'number' },
    'GPU': { tdp: 'number', longueur_mm: 'number' },
    'Stockage': { type: 'str' },
    'Refroidissement': { sockets_supportes: 'list', hauteur_mm: 'number' },
  };

  let allComponentsForEdit = [];
  let currentEditComponent = null; // null = création d'un nouveau composant
  let collapsedBrowseCategories = new Set();
  let browseCategoriesInitialized = false;
  // Détails produit Amazon du composant en cours d'édition — préservés tels
  // quels si on ré-enregistre sans recliquer sur "Récupérer depuis Amazon"
  // (sinon un simple ajustement de prix effacerait ces données déjà stockées).
  let currentAmazonDetails = [];
  let currentAmazonDescription = null;

  // État de l'import groupé en cours (null quand rien n'est en cours) —
  // permet aux boutons Pause/Annuler d'agir sur une boucle d'import lancée
  // par fetchAsinInfo(), qui tourne dans sa propre fonction.
  let importControl = null;

  function pauseResumeImport(){
    if(!importControl) return;
    importControl.paused = !importControl.paused;
    document.getElementById('pause-import-btn').textContent = importControl.paused ? '▶ Reprendre' : '⏸ Pause';
  }

  function cancelImport(){
    if(!importControl) return;
    importControl.cancelled = true;
    importControl.controller.abort();
  }

  async function loadAllComponentsForEdit(){
    try{
      // /api/admin/components (pas /api/components) : la version publique
      // renvoie un chemin proxy pour image_url, pas exploitable pour
      // ré-enregistrer le composant tel quel — voir le commentaire de la
      // route côté serveur pour l'incident que ça causait à l'édition.
      const res = await fetch(API_BASE + '/api/admin/components', {
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json();
      allComponentsForEdit = Object.values(data.components || {}).flat();

      // Toutes les catégories démarrent repliées, une seule fois (pas à
      // chaque rechargement de la liste après un ajout/suppression, sinon
      // on écraserait les catégories que l'admin vient d'ouvrir).
      if(!browseCategoriesInitialized){
        browseCategoriesInitialized = true;
        [...new Set(allComponentsForEdit.map(c => c.categorie))].forEach(cat => collapsedBrowseCategories.add(cat));
      }

      renderBrowseList();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  function normalize(str){
    return (str || '')
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function matchesQuery(nom, query){
    const normalizedNom = normalize(nom);
    const tokens = normalize(query).split(/\s+/).filter(Boolean);
    return tokens.every(token => normalizedNom.includes(token));
  }

  function toggleBrowseCategory(categorie){
    if(collapsedBrowseCategories.has(categorie)) collapsedBrowseCategories.delete(categorie);
    else collapsedBrowseCategories.add(categorie);
    renderBrowseList();
  }

  function renderBrowseList(){
    const query = document.getElementById('browse-search').value.trim();
    const filtered = query ? allComponentsForEdit.filter(c => matchesQuery(c.nom, query)) : allComponentsForEdit;
    document.getElementById('browse-count').textContent = filtered.length;

    const byCategory = {};
    filtered.forEach(c => {
      if(!byCategory[c.categorie]) byCategory[c.categorie] = [];
      byCategory[c.categorie].push(c);
    });

    const listEl = document.getElementById('browse-list');
    const categories = Object.keys(byCategory).sort();

    if(categories.length === 0){
      listEl.innerHTML = '<p style="color:var(--text-dim); font-size:0.88rem;">Aucun composant ne correspond.</p>';
      return;
    }

    listEl.innerHTML = categories.map(categorie => {
      const items = byCategory[categorie].slice().sort((a, b) => a.nom.localeCompare(b.nom));
      const isCollapsed = collapsedBrowseCategories.has(categorie);
      const rowsHtml = items.map(c => `
        <div class="browse-row ${currentEditComponent && currentEditComponent.id === c.id ? 'active' : ''}">
          <div>
            <span class="nom">${escapeHtml(c.nom)}</span>
            <span class="prix"> — ${c.prix_indicatif}€</span>
            ${c.en_stock === false ? '<span class="epuise-badge">Épuisé</span>' : ''}
          </div>
          <div class="row-actions">
            <button class="edit-btn" data-onclick="selectComponentToEdit(${c.id})">Éditer</button>
            <button class="delete-btn" data-onclick="quickDeleteComponent(${c.id})">Supprimer</button>
          </div>
        </div>
      `).join('');

      return `
        <div class="browse-category">
          <div class="browse-category-header" data-onclick="toggleBrowseCategory('${categorie.replace(/'/g, "\\'")}')">
            <span>${categorie} <span class="count">(${items.length})</span></span>
            <span>${isCollapsed ? '▶' : '▼'}</span>
          </div>
          <div class="browse-category-body ${isCollapsed ? '' : 'show'}">${rowsHtml}</div>
        </div>
      `;
    }).join('');
  }

  function selectComponentToEdit(id){
    const component = allComponentsForEdit.find(c => c.id === id);
    if(!component) return;

    // Édition d'un composant existant : formulaire complet visible (relecture
    // et corrections manuelles), contrairement à l'ajout rapide par ASIN.
    document.getElementById('full-edit-fields').classList.remove('hidden');
    document.getElementById('categorie-field').classList.remove('hidden');
    document.getElementById('categorie-auto-hint').classList.add('hidden');
    document.getElementById('batch-categorie-field').classList.add('hidden');
    document.getElementById('edit-asin-label').textContent = 'ASIN, lien Amazon ou nom du produit';

    currentEditComponent = component;
    currentAmazonDetails = component.caracteristiques_amazon || [];
    currentAmazonDescription = component.description || null;
    document.getElementById('edit-empty-hint').classList.add('hidden');
    document.getElementById('delete-btn').classList.remove('hidden');

    document.getElementById('edit-categorie').value = component.categorie;
    document.getElementById('edit-nom-input').value = component.nom;
    document.getElementById('edit-asin-input').value = component.asin || '';
    document.getElementById('fetch-asin-result').classList.add('hidden');
    onCategorieChange();

    let specs = {};
    try{ specs = JSON.parse(component.specs_json); }catch(e){}
    document.getElementById('specs-rows').innerHTML = '';
    Object.entries(specs).forEach(([k, v]) => addSpecRow(k, Array.isArray(v) ? v.join(', ') : v));

    document.getElementById('edit-prix-indicatif').value = component.prix_indicatif ?? '';
    document.getElementById('edit-image-url').value = component.image_url || '';
    document.getElementById('find-image-result').classList.add('hidden');
    document.getElementById('remove-bg-result').classList.add('hidden');
    updateImagePreview();

    const rowsContainer = document.getElementById('price-rows');
    rowsContainer.innerHTML = '';
    (component.prix_marche || []).forEach(p => addPriceRow(p));

    document.getElementById('edit-panel').classList.add('show');
    document.getElementById('edit-result').classList.add('hidden');
    renderBrowseList();
    // Le formulaire d'édition est en haut de page (avant la liste) — sans
    // ça, cliquer "Éditer" plus bas ne montre aucun changement visible.
    document.getElementById('edit-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function startNewComponent(){
    currentEditComponent = null;
    currentAmazonDetails = [];
    currentAmazonDescription = null;
    // Ajout rapide : seul l'ASIN est visible, la catégorie est devinée
    // automatiquement depuis Amazon pour chaque composant importé — plus
    // besoin de la sélectionner à la main, y compris pour plusieurs ASIN
    // de catégories différentes collés en une fois.
    document.getElementById('full-edit-fields').classList.add('hidden');
    document.getElementById('categorie-field').classList.add('hidden');
    document.getElementById('categorie-auto-hint').classList.remove('hidden');
    document.getElementById('batch-categorie-field').classList.remove('hidden');
    document.getElementById('batch-categorie-select').value = '';
    document.getElementById('edit-empty-hint').classList.add('hidden');
    document.getElementById('delete-btn').classList.add('hidden');

    document.getElementById('edit-categorie').value = 'CPU';
    document.getElementById('edit-nom-input').value = '';
    document.getElementById('edit-asin-input').value = '';
    document.getElementById('edit-asin-label').textContent = 'ASIN, lien Amazon ou nom du produit (un ou plusieurs, un par ligne)';
    document.getElementById('fetch-asin-result').classList.add('hidden');
    onCategorieChange();

    document.getElementById('specs-rows').innerHTML = '';
    document.getElementById('edit-prix-indicatif').value = '';
    document.getElementById('edit-image-url').value = '';
    document.getElementById('find-image-result').classList.add('hidden');
    document.getElementById('remove-bg-result').classList.add('hidden');
    updateImagePreview();

    document.getElementById('price-rows').innerHTML = '';
    document.getElementById('edit-panel').classList.add('show');
    document.getElementById('edit-result').classList.add('hidden');
    renderBrowseList();
  }

  function onCategorieChange(){
    const categorie = document.getElementById('edit-categorie').value;
    const required = REQUIRED_SPECS_BY_CATEGORY[categorie] || [];
    document.getElementById('specs-required-hint').textContent =
      `Champs requis pour "${categorie}" : ${required.join(', ')}`;
  }

  function addSpecRow(key, value){
    const rowsContainer = document.getElementById('specs-rows');
    const row = document.createElement('div');
    row.className = 'spec-row';
    row.innerHTML = `
      <input type="text" placeholder="Nom du champ (ex: socket)" class="s-key" value="${escapeHtml(key)}">
      <input type="text" placeholder="Valeur (ex: AM5, ou a,b,c pour une liste)" class="s-value" value="${escapeHtml(value)}">
      <button data-onclick="this.parentElement.remove()" title="Supprimer">✕</button>
    `;
    rowsContainer.appendChild(row);
  }

  // Convertit la valeur texte d'un champ spec en nombre ou en liste quand
  // c'est manifestement le cas, sinon la garde telle quelle (chaîne).
  function parseSpecValue(rawValue, expectedType){
    const trimmed = (rawValue || '').trim();
    if(trimmed === '') return '';

    if(expectedType === 'number'){
      // Tolère du texte parasite autour du nombre (ex: "5 x M.2" copié
      // depuis une fiche produit) : on extrait le premier nombre trouvé
      // plutôt que d'échouer à la validation pour une simple mise en forme.
      const match = trimmed.match(/-?\d+(\.\d+)?/);
      return match ? Number(match[0]) : trimmed;
    }

    if(trimmed.includes(',')){
      return trimmed.split(',').map(v => v.trim()).filter(Boolean);
    }
    // Un champ explicitement "str" (ex: socket "AM5") ne doit jamais être
    // converti en nombre même s'il contient des chiffres.
    if(expectedType !== 'str' && !isNaN(trimmed)){
      return Number(trimmed);
    }
    return trimmed;
  }

  async function deleteCurrentComponent(){
    if(!currentEditComponent) return;
    if(!confirm(`Supprimer définitivement "${currentEditComponent.nom}" ? Cette action est irréversible.`)) return;

    try{
      const res = await fetch(API_BASE + `/api/admin/components/${currentEditComponent.id}`, {
        method: 'DELETE',
        headers: { 'X-Admin-Secret': adminSecret },
      });
      if(res.ok){
        currentEditComponent = null;
        document.getElementById('edit-panel').classList.remove('show');
        document.getElementById('edit-empty-hint').classList.remove('hidden');
        await loadAllComponentsForEdit();
      }else{
        const data = await res.json().catch(() => ({}));
        alert(data.detail || data.message || 'Erreur lors de la suppression.');
      }
    }catch(e){
      alert('Erreur réseau : ' + e.message);
    }
  }

  async function quickDeleteComponent(id){
    const component = allComponentsForEdit.find(c => c.id === id);
    if(!component) return;
    if(!confirm(`Supprimer définitivement "${component.nom}" ? Cette action est irréversible.`)) return;

    try{
      await fetch(API_BASE + `/api/admin/components/${id}`, {
        method: 'DELETE',
        headers: { 'X-Admin-Secret': adminSecret },
      });
      if(currentEditComponent && currentEditComponent.id === id){
        currentEditComponent = null;
        document.getElementById('edit-panel').classList.remove('show');
        document.getElementById('edit-empty-hint').classList.remove('hidden');
      }
      await loadAllComponentsForEdit();
    }catch(e){
      alert('Erreur réseau : ' + e.message);
    }
  }

  function updateImagePreview(){
    const url = document.getElementById('edit-image-url').value.trim();
    const img = document.getElementById('edit-image-preview');
    const wrap = document.getElementById('edit-image-preview-wrap');
    if(url){
      img.src = url;
      wrap.classList.remove('hidden');
    }else{
      wrap.classList.add('hidden');
    }
  }

  // Retire l'arrière-plan de l'image courante via Poof.bg. Ne remplace RIEN
  // automatiquement : l'admin voit un aperçu (fond en damier pour bien
  // visualiser la transparence) et clique "Utiliser cette image détourée"
  // pour l'appliquer — le résultat est une image encodée directement dans
  // le champ (pas de stockage de fichiers permanent sur ce serveur).
  async function removeBackgroundFromImage(){
    const imageUrl = document.getElementById('edit-image-url').value.trim();
    if(!imageUrl){
      alert('Renseigne d\'abord une image (URL).');
      return;
    }
    if(imageUrl.startsWith('data:')){
      alert('Cette image est déjà détourée (ou collée directement) — il faut une URL publique pour la traiter.');
      return;
    }

    const btn = document.getElementById('remove-bg-btn');
    const resultBox = document.getElementById('remove-bg-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Détourage en cours...';

    try{
      const res = await fetch(API_BASE + '/api/admin/remove-background', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
        body: JSON.stringify({ image_url: imageUrl }),
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Détourage échoué.';
        return;
      }

      resultBox.className = 'result ok';
      resultBox.innerHTML = '<p>Aperçu (fond en damier = transparence) :</p>' +
        `<img src="${data.image_data_url}" alt="Image détourée" style="max-width:160px; max-height:160px; background:repeating-conic-gradient(#3a3a3a 0% 25%, #2a2a2a 0% 50%) 50% / 16px 16px; border-radius:8px; margin:8px 0; display:block;">`;
      const useBtn = document.createElement('button');
      useBtn.className = 'btn-secondary-admin';
      useBtn.textContent = 'Utiliser cette image détourée';
      useBtn.onclick = () => {
        document.getElementById('edit-image-url').value = data.image_data_url;
        updateImagePreview();
      };
      resultBox.appendChild(useBtn);
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  // Repart d'une image Amazon fraîche pour ce composant (via son ASIN) —
  // utile quand l'image actuelle a un problème visible. Ne détoure rien ici
  // : remet juste l'URL Amazon brute, que la surveillance locale (BiRefNet)
  // détecte et traite toute seule dans les secondes qui suivent, comme pour
  // un nouveau composant.
  async function regenerateImage(){
    if(!currentEditComponent){
      alert('Sélectionne d\'abord un composant à éditer.');
      return;
    }
    if(!currentEditComponent.asin){
      alert('Ce composant n\'a pas d\'ASIN associé — régénération impossible, modifie l\'URL de l\'image à la main.');
      return;
    }

    const btn = document.getElementById('regenerate-image-btn');
    const resultBox = document.getElementById('regenerate-image-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Récupération d\'une image fraîche depuis Amazon…';

    try{
      const res = await fetch(API_BASE + `/api/admin/components/${currentEditComponent.id}/regenerate-image`, {
        method: 'POST',
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Régénération échouée.';
        return;
      }

      document.getElementById('edit-image-url').value = data.image_url;
      updateImagePreview();
      resultBox.className = 'result ok';
      resultBox.textContent = 'Nouvelle image récupérée et enregistrée — elle sera détourée automatiquement sous ~20s si la surveillance locale tourne (recharge la page ensuite pour la voir).';
      await loadAllComponentsForEdit();
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  // Cherche dans le feed produit AliExpress local (CPU + RAM uniquement,
  // voir main.py) et propose d'ajouter chaque résultat comme ligne de prix
  // "AliExpress" toute prête (lien d'affiliation Awin déjà inclus).
  async function searchAliexpress(){
    const query = document.getElementById('aliexpress-search-input').value.trim();
    const resultBox = document.getElementById('aliexpress-search-result');
    if(!query){
      alert('Tape au moins un mot-clé (ex: le nom du CPU ou de la RAM).');
      return;
    }

    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Recherche…';

    try{
      const res = await fetch(API_BASE + '/api/admin/aliexpress-search?q=' + encodeURIComponent(query), {
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Recherche échouée.';
        return;
      }

      if(!data.results.length){
        resultBox.className = 'result';
        resultBox.textContent = 'Aucun résultat — essaie un mot-clé plus simple (ex: juste le modèle, sans la marque).';
        return;
      }

      resultBox.className = 'result ok';
      resultBox.innerHTML = '';
      data.results.forEach(item => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; gap:10px; padding:6px 0; border-bottom:1px solid var(--border);';
        row.innerHTML = `
          ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.nom)}" style="width:48px; height:48px; object-fit:contain; background:#ffffff; border-radius:4px; flex-shrink:0;">` : ''}
          <div style="flex:1; min-width:0;">
            <div style="font-size:0.85rem;">${escapeHtml(item.nom)}</div>
            <div style="font-size:0.78rem; color:var(--text-dim);">${item.prix != null ? item.prix + '€' : 'prix inconnu'} ${item.en_stock ? '' : '— rupture de stock'}</div>
          </div>
        `;
        const useBtn = document.createElement('button');
        useBtn.className = 'btn-secondary-admin';
        useBtn.textContent = 'Ajouter ce prix';
        useBtn.style.flexShrink = '0';
        useBtn.onclick = () => {
          addPriceRow({
            vendeur: 'AliExpress',
            prix: item.prix,
            lien: item.lien,
            date_releve: new Date().toISOString().slice(0, 10),
          });
        };
        row.appendChild(useBtn);
        resultBox.appendChild(row);
      });
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }
  }

  // Récupère nom/marque/prix/image/disponibilité via Bright Data à partir d'un
  // ASIN (ou d'une URL Amazon collée directement). Ne remplace jamais un nom
  // déjà saisi (juste au cas où le composant existe déjà sous un nom choisi
  // à la main) — pré-remplit tout le reste. L'admin doit relire et cliquer
  // "Enregistrer les modifications" comme pour les autres assistants IA.
  // Traite un seul ASIN en mode "ajout rapide" : récupère + devine la
  // catégorie + enregistre directement, sans étape de relecture. Renvoie une
  // ligne de résumé (succès ou échec) pour ce seul ASIN.
  async function fetchAndSaveOneAsin(asinRaw, signal, forcedCategorie){
    const res = await fetch(API_BASE + '/api/admin/fetch-asin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
      body: JSON.stringify(forcedCategorie ? { asin: asinRaw, categorie: forcedCategorie } : { asin: asinRaw }),
      signal,
    });
    const data = await res.json().catch(() => ({}));

    if(!res.ok || data.status !== 'ok'){
      return { ok: false, text: `${asinRaw} : ${data.detail || data.message || 'récupération Amazon échouée'}` };
    }

    const categorie = forcedCategorie || data.categorie;
    if(!categorie){
      return { ok: false, text: `${asinRaw} : catégorie non reconnue automatiquement — ajoute-le seul, en choisissant sa catégorie via "Éditer" après un premier enregistrement minimal.` };
    }

    const prix_marche = (data.prix != null && data.lien)
      ? [{ vendeur: 'Amazon', prix: data.prix, lien: data.lien, date_releve: new Date().toISOString().slice(0, 10) }]
      : [];
    const payload = {
      categorie,
      nom: data.nom || `${categorie} (ASIN ${data.asin})`,
      prix_indicatif: data.prix != null ? data.prix : 0,
      specs: data.specs || {},
      prix_marche,
      image_url: data.image_url || null,
      asin: data.asin,
      caracteristiques_amazon: Array.isArray(data.caracteristiques_amazon) ? data.caracteristiques_amazon : [],
      description: data.description || null,
    };

    const saveRes = await fetch(API_BASE + '/api/admin/components', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
      body: JSON.stringify({ components: [payload] }),
      signal,
    });
    const saveData = await saveRes.json().catch(() => ({}));

    if(saveData.status === 'ok'){
      const prixTxt = data.prix == null ? ' (prix introuvable, mis à 0€ — à corriger via "Éditer")' : ` (${payload.prix_indicatif}€)`;
      return { ok: true, text: `"${payload.nom}" — ${categorie}${prixTxt}` };
    }
    const errList = (saveData.errors || []).join(' — ');
    return { ok: false, text: `${asinRaw} : ${(saveData.message || 'erreur à l\'enregistrement')}${errList ? ' ' + errList : ''}` };
  }

  async function fetchAsinInfo(){
    const rawInput = document.getElementById('edit-asin-input').value.trim();
    if(!rawInput){
      alert('Colle d\'abord un ASIN ou une URL Amazon (un ou plusieurs, un par ligne).');
      return;
    }

    const btn = document.getElementById('fetch-asin-btn');
    const resultBox = document.getElementById('fetch-asin-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');

    // Mode "ajout rapide" (currentEditComponent est null tant qu'on n'édite
    // pas un composant existant) : un ou plusieurs ASIN (un par ligne),
    // chacun récupéré, sa catégorie devinée, et enregistré indépendamment.
    if(currentEditComponent === null){
      const asinList = rawInput.split(/\r?\n|,/).map(s => s.trim()).filter(Boolean);
      const results = new Array(asinList.length);
      let nextIndex = 0;
      let completedCount = 0;

      // Traite plusieurs ASIN en parallèle plutôt qu'un par un — gain de temps
      // notable sur un import groupé. Concurrence limitée à 2, que ce soit un
      // ASIN/lien direct ou un nom de produit : CHAQUE import (peu importe la
      // source) déclenche un nettoyage de titre par IA (petit quota Groq
      // séparé, ~1000 tokens/minute) ET un détourage d'image sur le service
      // rembg auto-hébergé (VM modeste, un seul cœur) — au-delà de 2 en
      // parallèle, ces deux ressources partagées deviennent le goulot
      // d'étranglement et ralentissent tout au lieu d'accélérer.
      const CONCURRENCY = 2;
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const forcedCategorie = document.getElementById('batch-categorie-select').value || null;

      importControl = { paused: false, cancelled: false, controller: new AbortController() };
      const pauseBtn = document.getElementById('pause-import-btn');
      const cancelBtn = document.getElementById('cancel-import-btn');
      pauseBtn.textContent = '⏸ Pause';
      pauseBtn.classList.remove('hidden');
      cancelBtn.classList.remove('hidden');

      async function worker(){
        while(nextIndex < asinList.length){
          if(importControl.cancelled) return;
          if(importControl.paused){ await sleep(300); continue; }

          const i = nextIndex++;
          try{
            const outcome = await fetchAndSaveOneAsin(asinList[i], importControl.controller.signal, forcedCategorie);
            results[i] = (outcome.ok ? '✅ ' : '❌ ') + outcome.text;
          }catch(e){
            results[i] = importControl.cancelled
              ? `⏹ ${asinList[i]} : annulé.`
              : `❌ ${asinList[i]} : erreur réseau.`;
          }
          completedCount++;
          if(!importControl.cancelled){
            resultBox.textContent = `Import en cours... (${completedCount}/${asinList.length} terminé${completedCount > 1 ? 's' : ''})`;
          }
        }
      }

      resultBox.textContent = `Import de ${asinList.length} composant(s) en cours...`;
      await Promise.all(Array.from({ length: Math.min(CONCURRENCY, asinList.length) }, worker));

      const doneResults = results.filter(Boolean);
      const wasCancelled = importControl.cancelled;
      importControl = null;
      pauseBtn.classList.add('hidden');
      cancelBtn.classList.add('hidden');

      resultBox.className = doneResults.some(l => l.startsWith('❌')) ? 'result error' : (wasCancelled ? 'result' : 'result ok');
      resultBox.innerHTML = (wasCancelled ? '⏹ Import annulé.<br>' : '') + doneResults.map(escapeHtml).join('<br>');
      document.getElementById('edit-asin-input').value = '';
      btn.disabled = false;
      await loadAllComponentsForEdit();
      return;
    }

    // Mode édition d'un composant existant : un seul ASIN, formulaire complet,
    // l'admin relit et clique "Enregistrer les modifications" lui-même. La
    // catégorie reste celle choisie dans le formulaire (le composant existe
    // déjà dans une catégorie donnée, pas de raison de la redeviner).
    const categorie = document.getElementById('edit-categorie').value;
    const missing = [];

    try{
      const res = await fetch(API_BASE + '/api/admin/fetch-asin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
        body: JSON.stringify({ asin: rawInput, categorie }),
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Récupération Amazon échouée.';
        return;
      }

      // L'ASIN reconnu remplace ce qui a été collé (utile si une URL
      // complète a été collée à la place de l'ASIN nu).
      document.getElementById('edit-asin-input').value = data.asin;

      // data.nom est déjà composé côté serveur (marque + modèle nettoyé +
      // couleur si utile) — voir build_component_name().
      if(!document.getElementById('edit-nom-input').value.trim() && data.nom){
        document.getElementById('edit-nom-input').value = data.nom;
      }else if(!data.nom){
        missing.push('nom');
      }

      if(data.prix != null){
        document.getElementById('edit-prix-indicatif').value = data.prix;
      }else{
        missing.push('prix');
      }

      if(data.image_url){
        document.getElementById('edit-image-url').value = data.image_url;
        updateImagePreview();
      }else{
        missing.push('image');
      }

      if(data.prix != null && data.lien){
        // Remplace un éventuel relevé "Amazon" déjà présent plutôt que d'en
        // ajouter un doublon — même règle que /api/admin/refresh-prices.
        [...document.querySelectorAll('#price-rows .price-row')].forEach(row => {
          if(row.querySelector('.p-vendeur').value.trim() === 'Amazon') row.remove();
        });
        addPriceRow({
          vendeur: 'Amazon',
          prix: data.prix,
          lien: data.lien,
          date_releve: new Date().toISOString().slice(0, 10),
        });
      }

      // Specs déduites d'Amazon : on les pose dans les champs correspondants,
      // et on ajoute une ligne vide pour chaque champ requis non déduit
      // (numérique/dimension, ou pas trouvé) — à compléter à la main.
      document.getElementById('specs-rows').innerHTML = '';
      const specsAmazon = data.specs || {};
      (REQUIRED_SPECS_BY_CATEGORY[categorie] || []).forEach(key => {
        const value = specsAmazon[key];
        if(value === null || value === undefined || value === ''){
          missing.push(`specs.${key}`);
          addSpecRow(key, '');
        }else{
          addSpecRow(key, value);
        }
      });
      // Champs supplémentaires déduits par Amazon au-delà des champs requis
      // (ex: "couleur" — purement informatif, jamais un champ de
      // compatibilité obligatoire).
      Object.entries(specsAmazon).forEach(([key, value]) => {
        if((REQUIRED_SPECS_BY_CATEGORY[categorie] || []).includes(key)) return;
        if(value === null || value === undefined || value === '') return;
        addSpecRow(key, value);
      });

      const amazonSummary = `Amazon (ASIN ${escapeHtml(data.asin)})` +
        (data.disponibilite ? ` — ${escapeHtml(String(data.disponibilite))}` : '') + '.';

      // Conservé pour être envoyé avec le composant à l'enregistrement — et
      // affiché aux visiteurs dans la modale de détail du configurateur.
      currentAmazonDetails = Array.isArray(data.caracteristiques_amazon) ? data.caracteristiques_amazon : [];
      currentAmazonDescription = data.description || null;

      // Tableau complet "Détails du produit" d'Amazon, pour compléter à la
      // main les champs non déduits (notamment tout ce qui est numérique).
      let caracteristiquesHtml = '';
      if(Array.isArray(data.caracteristiques_amazon) && data.caracteristiques_amazon.length > 0){
        const rows = data.caracteristiques_amazon
          .map(c => `<tr><td style="padding:2px 10px 2px 0; color:var(--text-dim);">${escapeHtml(c.type)}</td><td>${escapeHtml(c.value)}</td></tr>`)
          .join('');
        caracteristiquesHtml = `
          <details style="margin-top:10px;">
            <summary style="cursor:pointer; color:var(--accent2);">📋 Détails produit Amazon (référence, ${data.caracteristiques_amazon.length} champs)</summary>
            <table style="margin-top:6px; font-size:0.85em;">${rows}</table>
          </details>`;
      }

      resultBox.className = missing.length > 0 ? 'result' : 'result ok';
      resultBox.innerHTML = amazonSummary +
        (missing.length > 0 ? `<br>Non trouvé, à compléter à la main : ${escapeHtml(missing.join(', '))}.` : '') +
        ' Vérifie chaque champ avant d\'enregistrer.' +
        caracteristiquesHtml;
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  async function refreshAllPrices(){
    if(!confirm('Rafraîchir les prix Amazon de tous les composants ayant un ASIN renseigné ? Ça consomme des requêtes Bright Data (5000 gratuites/mois).')) return;

    const btn = document.getElementById('refresh-prices-btn');
    const resultBox = document.getElementById('refresh-prices-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Rafraîchissement en cours (peut prendre un moment selon le nombre de composants)...';

    try{
      const res = await fetch(API_BASE + '/api/admin/refresh-prices', {
        method: 'POST',
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Rafraîchissement échoué.';
        return;
      }

      const hasErrors = (data.errors || []).length > 0;
      resultBox.className = hasErrors ? 'result' : 'result ok';
      resultBox.innerHTML = `${data.updated} composant(s) revérifié(s).` +
        (data.remis_en_stock ? `<br>${data.remis_en_stock} remis en stock.` : '') +
        (data.passes_epuises ? `<br>${data.passes_epuises} passé(s) épuisé(s) (masqué(s) du configurateur, pas supprimé(s)).` : '') +
        (data.message ? `<br>${escapeHtml(data.message)}` : '') +
        (hasErrors ? `<br><br>Détails :<br>${data.errors.map(e => escapeHtml(e)).join('<br>')}` : '');

      await loadAllComponentsForEdit();
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  // Action irréversible (tout le catalogue) : double confirmation — un
  // confirm() classique, puis un mot exact à retaper — avant d'envoyer la
  // moindre requête. Bien plus de friction qu'une suppression individuelle.
  async function deleteAllComponents(){
    const count = allComponentsForEdit.length;
    if(!confirm(`Supprimer DÉFINITIVEMENT les ${count} composant(s) du catalogue ? Cette action est irréversible et affecte immédiatement le site public.`)){
      return;
    }
    const saisie = prompt('Pour confirmer, tape exactement SUPPRIMER (en majuscules) :');
    if(saisie !== 'SUPPRIMER'){
      alert('Suppression annulée (texte de confirmation incorrect).');
      return;
    }

    const btn = document.getElementById('delete-all-btn');
    const resultBox = document.getElementById('delete-all-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Suppression en cours...';

    try{
      const res = await fetch(API_BASE + '/api/admin/components', {
        method: 'DELETE',
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json().catch(() => ({}));

      if(!res.ok || data.status !== 'ok'){
        resultBox.className = 'result error';
        resultBox.textContent = data.detail || data.message || 'Suppression échouée.';
        return;
      }

      resultBox.className = 'result ok';
      resultBox.textContent = `${data.deleted} composant(s) supprimé(s).`;
      await loadAllComponentsForEdit();
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  async function findImageWithAI(){
    const nom = document.getElementById('edit-nom-input').value.trim();
    const categorie = document.getElementById('edit-categorie').value;
    if(!nom){
      alert('Renseigne d\'abord le nom du composant.');
      return;
    }

    const btn = document.getElementById('find-image-btn');
    const resultBox = document.getElementById('find-image-result');

    btn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Recherche en cours...';

    try{
      const res = await fetch(API_BASE + '/api/admin/find-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
        body: JSON.stringify({ nom, categorie }),
      });
      const data = await res.json();

      if(data.status === 'ok'){
        resultBox.className = 'result ok';
        resultBox.innerHTML = `Image trouvée (source : ${escapeHtml(data.source || 'non précisée')}).<br>`;
        const useBtn = document.createElement('button');
        useBtn.className = 'btn-secondary-admin';
        useBtn.style.marginTop = '8px';
        useBtn.textContent = 'Utiliser cette image';
        useBtn.onclick = () => {
          document.getElementById('edit-image-url').value = data.image_url;
          updateImagePreview();
        };
        resultBox.appendChild(useBtn);
      }else{
        resultBox.className = 'result error';
        resultBox.textContent = data.message || data.detail || 'Aucune image trouvée.';
      }
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      btn.disabled = false;
    }
  }

  function addPriceRow(existing){
    const rowsContainer = document.getElementById('price-rows');
    const row = document.createElement('div');
    row.className = 'price-row';
    row.innerHTML = `
      <input type="text" placeholder="Revendeur (ex: Amazon)" class="p-vendeur" value="${escapeHtml(existing?.vendeur)}">
      <input type="number" step="0.01" placeholder="Prix" class="p-prix" value="${existing?.prix ?? ''}">
      <input type="text" placeholder="Lien" class="p-lien" value="${escapeHtml(existing?.lien)}">
      <input type="date" class="p-date" value="${escapeHtml(existing?.date_releve)}">
      <button data-onclick="this.parentElement.remove()" title="Supprimer">✕</button>
    `;
    rowsContainer.appendChild(row);
    return row;
  }

  async function saveEdit(){
    const saveBtn = document.getElementById('save-edit-btn');
    const resultBox = document.getElementById('edit-result');

    const categorie = document.getElementById('edit-categorie').value;
    const nom = document.getElementById('edit-nom-input').value.trim();
    const prixIndicatifRaw = document.getElementById('edit-prix-indicatif').value;
    const prix_indicatif = prixIndicatifRaw === '' ? null : Number(prixIndicatifRaw);

    const specs = {};
    [...document.querySelectorAll('#specs-rows .spec-row')].forEach(row => {
      const key = row.querySelector('.s-key').value.trim();
      if(!key) return;
      const expectedType = (SPEC_FIELD_TYPES[categorie] || {})[key];
      specs[key] = parseSpecValue(row.querySelector('.s-value').value, expectedType);
    });

    // On préserve lien_mort/dernier_check (posés par la vérification
    // automatique) tant que le lien lui-même n'a pas changé — sinon chaque
    // sauvegarde depuis ce formulaire effacerait silencieusement l'état de
    // la dernière vérification.
    const originalByVendeur = {};
    (currentEditComponent?.prix_marche || []).forEach(p => { originalByVendeur[p.vendeur] = p; });

    const prix_marche = [...document.querySelectorAll('#price-rows .price-row')].map(row => {
      const vendeur = row.querySelector('.p-vendeur').value.trim();
      const lien = row.querySelector('.p-lien').value.trim();
      const entry = {
        vendeur,
        prix: Number(row.querySelector('.p-prix').value),
        lien,
        date_releve: row.querySelector('.p-date').value,
      };
      const original = originalByVendeur[vendeur];
      if(original && original.lien === lien){
        if('lien_mort' in original) entry.lien_mort = original.lien_mort;
        if('dernier_check' in original) entry.dernier_check = original.dernier_check;
      }
      return entry;
    }).filter(p => p.vendeur && p.lien);

    const image_url = document.getElementById('edit-image-url').value.trim() || null;
    const asin = document.getElementById('edit-asin-input').value.trim() || null;

    const payload = { categorie, nom, prix_indicatif, specs, prix_marche, image_url, asin, caracteristiques_amazon: currentAmazonDetails, description: currentAmazonDescription };

    saveBtn.disabled = true;
    resultBox.className = 'result';
    resultBox.classList.remove('hidden');
    resultBox.textContent = 'Enregistrement...';

    try{
      // Édition d'un composant existant : PUT par ID (permet de renommer ou
      // changer de catégorie sans créer de doublon). Nouveau composant :
      // POST classique, qui le crée puisqu'aucun ID n'existe encore.
      const res = currentEditComponent
        ? await fetch(API_BASE + `/api/admin/components/${currentEditComponent.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
            body: JSON.stringify(payload),
          })
        : await fetch(API_BASE + '/api/admin/components', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
            body: JSON.stringify({ components: [payload] }),
          });
      const data = await res.json();

      if(data.status === 'ok'){
        resultBox.className = 'result ok';
        resultBox.textContent = 'Modifications enregistrées.';
        await loadAllComponentsForEdit();
        if(!currentEditComponent){
          // Le composant vient d'être créé : on retrouve son ID pour
          // basculer en mode édition (et faire apparaître "Supprimer").
          const created = allComponentsForEdit.find(c => c.categorie === categorie && c.nom === nom);
          if(created) selectComponentToEdit(created.id);
        }
      }else{
        resultBox.className = 'result error';
        const errList = (data.errors || []).map(e => '- ' + e).join('\n');
        resultBox.textContent = (data.message || 'Erreur') + (errList ? '\n\n' + errList : '');
      }
    }catch(e){
      resultBox.className = 'result error';
      resultBox.textContent = 'Erreur réseau : ' + e.message;
    }finally{
      saveBtn.disabled = false;
    }
  }

  document.getElementById('browse-search').addEventListener('input', renderBrowseList);

  // --- Bandeau des liens morts (vérifiés automatiquement une fois par jour) ---

  async function loadBrokenLinksBanner(){
    const banner = document.getElementById('broken-links-banner');
    try{
      const res = await fetch(API_BASE + '/api/admin/broken-links', {
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json();
      if(data.check_status) lastKnownCheckTimestamp = data.check_status.dernier_lancement;
      renderBrokenLinksBanner(data.broken_links || [], data.check_status);
    }catch(e){
      banner.classList.add('hidden');
    }
  }

  // Échappe une valeur pour l'insérer comme texte affiché OU comme valeur
  // d'attribut HTML (value="...", href="...") — jamais faire confiance à un
  // vendeur/lien/e-mail/nom saisi par un utilisateur ou proposé par une
  // recherche IA avant de l'insérer via innerHTML.
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Échappe une valeur pour l'insérer à la fois comme littéral JS
  // (apostrophes) et comme attribut HTML (guillemets doubles) dans un même
  // data-onclick="..." généré par innerHTML.
  function escapeForJsString(str){
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  }

  // checkStatus vient de LAST_LINK_CHECK_STATUS côté serveur : on l'affiche
  // toujours (même sans lien mort) pour être honnête sur ce qui a vraiment
  // pu être vérifié — un lien absent de la liste "morts" n'est pas forcément
  // confirmé vivant, il peut juste avoir été bloqué par l'anti-bot Amazon.
  function renderBrokenLinksBanner(brokenLinks, checkStatus){
    const banner = document.getElementById('broken-links-banner');
    if(!checkStatus || !checkStatus.dernier_lancement){
      banner.classList.add('hidden');
      banner.innerHTML = '';
      return;
    }

    banner.classList.remove('hidden');
    banner.classList.toggle('banner-danger', brokenLinks.length > 0);

    const statusLine = `Dernière vérification le ${new Date(checkStatus.dernier_lancement).toLocaleString('fr-FR')} — ` +
      `${checkStatus.liens_testes} lien(s) testé(s), dont ${checkStatus.liens_non_verifiables} non ` +
      `vérifiable(s) (bloqué(s) par la protection anti-bot d'Amazon — ni confirmés morts, ni vivants)` +
      (checkStatus.liens_corriges_auto > 0 ? `, ${checkStatus.liens_corriges_auto} lien(s) Amazon corrigé(s) automatiquement` : '') + '.';

    if(brokenLinks.length === 0){
      banner.innerHTML = `
        <h3 style="color:var(--text-dim);">✓ Aucun lien confirmé mort</h3>
        <p style="font-size:0.85rem; color:var(--text-dim); margin-top:6px;">${statusLine}</p>
        <button class="btn-secondary-admin" style="margin-top:12px;" data-onclick="checkLinksNow()">Revérifier maintenant</button>
      `;
      return;
    }

    const itemsHtml = brokenLinks.map(b => `
      <div class="broken-item">
        [${escapeHtml(b.categorie)}] <strong>${escapeHtml(b.nom)}</strong> — ${escapeHtml(b.vendeur)} :
        <a href="${escapeHtml(b.lien)}" target="_blank" rel="noopener noreferrer">${escapeHtml(b.lien)}</a>
        <button class="btn-secondary-admin" style="margin:6px 0 0; padding:6px 12px;"
          data-onclick="fixBrokenLink(${b.component_id}, '${escapeForJsString(b.vendeur)}', '${escapeForJsString(b.lien)}')">
          ✏ Éditer ce lien
        </button>
      </div>
    `).join('');

    banner.innerHTML = `
      <h3>⚠ ${brokenLinks.length} lien(s) mort(s) détecté(s)</h3>
      <p style="font-size:0.85rem; color:var(--text-dim); margin-bottom:12px;">${statusLine}</p>
      ${itemsHtml}
      <button class="btn-secondary-admin" style="margin-top:12px;" data-onclick="checkLinksNow()">Revérifier maintenant</button>
    `;
  }

  // Le lancement démarre la vérification en arrière-plan côté serveur (voir
  // /api/admin/check-links) puis on sonde régulièrement jusqu'à ce que le
  // timestamp de dernière vérification change — plus fiable qu'attendre une
  // seule requête qui pourrait dépasser le timeout HTTP sur un gros catalogue.
  async function checkLinksNow(){
    const banner = document.getElementById('broken-links-banner');
    banner.innerHTML = '<h3>Vérification lancée en arrière-plan (peut prendre plusieurs minutes pour tout le catalogue)...</h3>';
    banner.classList.remove('hidden');

    try{
      await fetch(API_BASE + '/api/admin/check-links', {
        method: 'POST',
        headers: { 'X-Admin-Secret': adminSecret },
      });
    }catch(e){
      banner.innerHTML = '<h3>Erreur lors du lancement de la vérification.</h3>';
      return;
    }

    for(let attempt = 0; attempt < 60; attempt++){
      await new Promise(r => setTimeout(r, 5000));
      try{
        const res = await fetch(API_BASE + '/api/admin/broken-links', {
          headers: { 'X-Admin-Secret': adminSecret },
        });
        const data = await res.json();
        if(data.check_status && data.check_status.dernier_lancement !== lastKnownCheckTimestamp){
          lastKnownCheckTimestamp = data.check_status.dernier_lancement;
          renderBrokenLinksBanner(data.broken_links || [], data.check_status);
          return;
        }
      }catch(e){
        // Erreur réseau ponctuelle pendant le sondage : on retente au prochain tour.
      }
    }
    banner.innerHTML = '<h3>La vérification est toujours en cours (catalogue volumineux) — recharge la page dans quelques minutes.</h3>';
  }

  async function fixBrokenLink(componentId, vendeur, ancienLien){
    const nouveauLien = prompt(`Nouveau lien pour "${vendeur}" :`, ancienLien);
    if(!nouveauLien || nouveauLien === ancienLien) return;

    try{
      const res = await fetch(API_BASE + '/api/admin/fix-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
        body: JSON.stringify({ component_id: componentId, vendeur, nouveau_lien: nouveauLien }),
      });
      const data = await res.json().catch(() => ({}));
      if(res.ok){
        await loadBrokenLinksBanner();
        await loadAllComponentsForEdit();
      }else{
        alert(data.detail || data.message || 'Erreur lors de la mise à jour du lien.');
      }
    }catch(e){
      alert('Erreur réseau : ' + e.message);
    }
  }

  // --- Modération des corrections de liens proposées par les utilisateurs ---

  async function loadLinkCorrections(){
    try{
      const res = await fetch(API_BASE + '/api/admin/link-corrections', {
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json();
      renderLinkCorrections(data.corrections || []);
    }catch(e){
      document.getElementById('link-corrections-list').innerHTML = '<p style="color:var(--text-dim); font-size:0.85rem;">Erreur de chargement.</p>';
    }
  }

  function renderLinkCorrections(corrections){
    const listEl = document.getElementById('link-corrections-list');
    if(corrections.length === 0){
      listEl.innerHTML = '<p style="color:var(--text-dim); font-size:0.85rem;">Aucune correction en attente.</p>';
      return;
    }

    listEl.innerHTML = corrections.map(c => `
      <div class="correction-item">
        <div class="meta">[${escapeHtml(c.component_categorie)}] <strong>${escapeHtml(c.component_nom)}</strong> — ${escapeHtml(c.vendeur)} · proposé par ${escapeHtml(c.user_email)} le ${new Date(c.date).toLocaleDateString('fr-FR')}</div>
        <div class="links">
          ${c.ancien_lien ? `<span class="old">${escapeHtml(c.ancien_lien)}</span>` : ''}
          <span class="new">${escapeHtml(c.nouveau_lien)}</span>
        </div>
        <div class="actions">
          <button class="approve" data-onclick="approveCorrection(${c.id})">✓ Approuver</button>
          <button class="reject" data-onclick="rejectCorrection(${c.id})">✕ Rejeter</button>
        </div>
      </div>
    `).join('');
  }

  async function approveCorrection(id){
    await fetch(API_BASE + `/api/admin/link-corrections/${id}/approve`, {
      method: 'POST',
      headers: { 'X-Admin-Secret': adminSecret },
    });
    loadLinkCorrections();
    loadBrokenLinksBanner();
    loadAllComponentsForEdit();
  }

  async function rejectCorrection(id){
    await fetch(API_BASE + `/api/admin/link-corrections/${id}/reject`, {
      method: 'POST',
      headers: { 'X-Admin-Secret': adminSecret },
    });
    loadLinkCorrections();
  }

  // --- Configurations recommandées (mises en avant sur /estimer-fps) ---

  async function loadAdminBuilds(){
    const listEl = document.getElementById('admin-builds-list');
    try{
      const res = await fetch(API_BASE + '/api/admin/builds', {
        headers: { 'X-Admin-Secret': adminSecret },
      });
      const data = await res.json();
      renderAdminBuilds(data.builds || []);
    }catch(e){
      listEl.innerHTML = '<p style="color:var(--text-dim); font-size:0.85rem;">Erreur de chargement.</p>';
    }
  }

  function renderAdminBuilds(builds){
    const listEl = document.getElementById('admin-builds-list');
    if(builds.length === 0){
      listEl.innerHTML = '<p style="color:var(--text-dim); font-size:0.85rem;">Aucune configuration sauvegardée pour l\'instant.</p>';
      return;
    }

    listEl.innerHTML = builds.map(b => `
      <div class="admin-build-row ${b.est_officielle ? 'official' : ''}">
        <div class="meta">
          <span class="nom">${escapeHtml(b.nom)}</span>
          <span class="sub">${escapeHtml(b.user_email)} · ${new Date(b.date).toLocaleDateString('fr-FR')}</span>
        </div>
        <button class="${b.est_officielle ? 'is-official' : ''}" data-onclick="toggleOfficialBuild(${b.id})">
          ${b.est_officielle ? '★ Recommandée' : '☆ Mettre en avant'}
        </button>
      </div>
    `).join('');
  }

  async function toggleOfficialBuild(buildId){
    await fetch(API_BASE + `/api/admin/builds/${buildId}/toggle-officielle`, {
      method: 'POST',
      headers: { 'X-Admin-Secret': adminSecret },
    });
    loadAdminBuilds();
  }
