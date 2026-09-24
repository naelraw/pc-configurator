  const API_BASE = window.location.origin;
  let selectedComponents = {};
  let allComponents = [];
  let budgetMax = null;
  let editingBuildId = null;   // non-null = "Sauvegarder" met à jour cette config au lieu d'en créer une nouvelle
  let editingBuildNom = null;

  const FIELD_TO_CATEGORY = {
    cpu_id: 'CPU',
    motherboard_id: 'Carte mère',
    ram_id: 'RAM',
    gpu_id: 'GPU',
    psu_id: 'Alimentation',
    storage_id: 'Stockage',
    case_id: 'Boîtier',
  };

  // Bouton "Plus de filtres", visible seulement sur mobile (voir CSS) :
  // replie/déplie les filtres secondaires pour ne pas repousser les
  // produits loin sous la ligne de flottaison sur petit écran.
  function toggleMobileFilters(){
    const panel = document.getElementById('toolbar-extra-filters');
    const toggle = document.getElementById('toolbar-filters-toggle');
    const isExpanded = panel.classList.toggle('expanded');
    toggle.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    toggle.firstChild.textContent = isExpanded ? 'Moins de filtres ' : 'Plus de filtres ';
  }

  function onBudgetChange(){
    const raw = document.getElementById('budget-input').value;
    budgetMax = raw === '' ? null : Number(raw);
    renderComponents(allComponents);
    updateBuildPreview();
  }

  // "Meilleur d'abord" : trie sur perf_index (indice de performance réel,
  // voir GPU/CPU_PERFORMANCE_INDEX côté serveur — plus il est haut, meilleur
  // est le composant) quand disponible ; sinon repli sur le prix décroissant,
  // seul signal de qualité qu'on ait pour les catégories sans indice connu
  // (Boîtier, Carte mère, Refroidissement...).
  function sortItems(items){
    const mode = document.getElementById('sort-select').value;
    const sorted = items.slice();
    if(mode === 'price-asc') sorted.sort((a, b) => a.prix_indicatif - b.prix_indicatif);
    else if(mode === 'price-desc') sorted.sort((a, b) => b.prix_indicatif - a.prix_indicatif);
    else if(mode === 'best-first'){
      sorted.sort((a, b) => {
        const aHasIndex = a.perf_index !== null && a.perf_index !== undefined;
        const bHasIndex = b.perf_index !== null && b.perf_index !== undefined;
        if(aHasIndex && bHasIndex) return b.perf_index - a.perf_index;
        if(aHasIndex !== bHasIndex) return aHasIndex ? -1 : 1;
        return b.prix_indicatif - a.prix_indicatif;
      });
    }
    else sorted.sort((a, b) => a.nom.localeCompare(b.nom));
    // Les produits épuisés (visibles seulement si la case est cochée) passent
    // toujours en fin de liste, quel que soit le tri choisi.
    return sorted.filter(i => i.en_stock !== false).concat(sorted.filter(i => i.en_stock === false));
  }

  // La "marque" n'est pas un champ à part dans la base — on la déduit du
  // premier mot du nom (ex: "AMD Ryzen 5 5600" -> "AMD"). Évite d'ajouter
  // un champ obligatoire de plus au schéma juste pour filtrer.
  function getBrand(nom){
    return (nom || '').trim().split(' ')[0];
  }

  // Échappe une valeur pour l'insérer comme texte affiché OU comme valeur
  // d'attribut HTML (src="...") — les specs/image/prix de marché d'un
  // composant peuvent venir d'une recherche web IA (find-component-info,
  // find-image) ou d'une correction de lien proposée par un utilisateur,
  // jamais fiables telles quelles dans du innerHTML.
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function appendOption(select, value){
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }

  // category vide/absente = toutes les marques du catalogue ; sinon,
  // seulement celles présentes dans cette catégorie (évite de proposer
  // "Kingston" quand on filtre sur les GPU, par exemple). La marque déjà
  // sélectionnée est conservée si elle existe encore dans la nouvelle
  // liste, sinon on revient à "Toutes les marques" plutôt que de garder un
  // filtre qui ne correspond plus à rien.
  function populateBrandOptions(category){
    const select = document.getElementById('brand-select');
    const previousValue = select.value;
    select.innerHTML = '<option value="">Toutes les marques</option>';
    const source = category ? allComponents.filter(c => c.categorie === category) : allComponents;
    const brands = [...new Set(source.map(c => getBrand(c.nom)))].sort();
    brands.forEach(brand => appendOption(select, brand));
    select.value = brands.includes(previousValue) ? previousValue : '';
  }

  // Filtres spécialisés par catégorie : n'apparaissent qu'une fois la
  // catégorie choisie dans le filtre principal, jamais tous en même temps —
  // chaque champ ne regarde que les specs qui existent vraiment pour cette
  // catégorie (ex: le socket n'a aucun sens pour de la RAM).
  //   kind "select"      -> menu déroulant sur une valeur texte exacte
  //   kind "select-list" -> menu déroulant sur une valeur dans une liste
  //   kind "max"/"min"   -> borne numérique
  const CATEGORY_FILTER_FIELDS = {
    'CPU': [
      { key: 'socket', label: 'Socket', kind: 'select' },
      { key: 'tdp', label: 'TDP maximum (W)', kind: 'max' },
    ],
    'Carte mère': [
      { key: 'socket', label: 'Socket', kind: 'select' },
      { key: 'format', label: 'Format', kind: 'select' },
      { key: 'ram_type', label: 'Type de RAM', kind: 'select' },
      { key: 'm2_slots', label: 'Slots M.2 minimum', kind: 'min' },
      { key: 'sata_ports', label: 'Ports SATA minimum', kind: 'min' },
    ],
    'RAM': [
      { key: 'type', label: 'Type', kind: 'select' },
      { key: 'couleur', label: 'Couleur', kind: 'select' },
    ],
    'Boîtier': [
      { key: 'formats_supportes', label: 'Format supporté', kind: 'select-list' },
      { key: 'gpu_max_length_mm', label: 'Accepte un GPU d\'au moins (mm)', kind: 'min' },
      { key: 'cpu_cooler_max_height_mm', label: 'Accepte un ventirad d\'au moins (mm)', kind: 'min' },
      { key: 'couleur', label: 'Couleur', kind: 'select' },
    ],
    'Alimentation': [
      { key: 'wattage', label: 'Wattage minimum', kind: 'min' },
      { key: 'certification', label: 'Certification 80 PLUS', kind: 'select' },
      { key: 'modularite', label: 'Modularité', kind: 'select' },
      { key: 'format', label: 'Format', kind: 'select' },
    ],
    'GPU': [
      { key: 'vram', label: 'Mémoire vidéo (VRAM)', kind: 'select' },
      { key: 'tdp', label: 'TDP maximum (W)', kind: 'max' },
      { key: 'longueur_mm', label: 'Longueur maximum (mm)', kind: 'max' },
      { key: 'couleur', label: 'Couleur', kind: 'select' },
    ],
    'Stockage': [
      { key: 'type', label: 'Type', kind: 'select' },
      { key: 'capacite_go', label: 'Capacité minimum (Go)', kind: 'min' },
      { key: 'couleur', label: 'Couleur', kind: 'select' },
    ],
    'Refroidissement': [
      { key: 'sockets_supportes', label: 'Socket supporté', kind: 'select-list' },
      { key: 'hauteur_mm', label: 'Hauteur maximum (mm)', kind: 'max' },
    ],
  };

  function specFilterInputId(key){
    return `spec-filter-${key}`;
  }

  // Reconstruit la barre de filtres spécialisés pour la catégorie choisie
  // (ou la vide si "Toutes les catégories" est sélectionné).
  function onCategoryFilterChange(){
    visibleCounts = {};
    const category = document.getElementById('category-filter-select').value;
    populateBrandOptions(category);
    const toolbar = document.getElementById('specialized-filters-toolbar');
    const fields = CATEGORY_FILTER_FIELDS[category] || [];

    if(fields.length === 0){
      toolbar.classList.add('hidden');
      toolbar.innerHTML = '';
      renderComponents(allComponents);
      return;
    }

    const itemsInCategory = allComponents.filter(c => c.categorie === category);

    toolbar.innerHTML = fields.map(field => {
      const inputId = specFilterInputId(field.key);
      if(field.kind === 'min' || field.kind === 'max'){
        return `
          <div class="field">
            <label for="${inputId}">${field.label}</label>
            <input type="number" id="${inputId}" data-oninput="onFilterChange()">
          </div>
        `;
      }

      const values = new Set();
      itemsInCategory.forEach(item => {
        const value = (item.specs || {})[field.key];
        if(field.kind === 'select-list' && Array.isArray(value)){
          value.forEach(v => values.add(v));
        }else if(value){
          values.add(value);
        }
      });

      const optionsHtml = [...values].sort().map(v => `<option value="${v}">${v}</option>`).join('');
      return `
        <div class="field">
          <label for="${inputId}">${field.label}</label>
          <select id="${inputId}" data-onchange="onFilterChange()">
            <option value="">Tous</option>
            ${optionsHtml}
          </select>
        </div>
      `;
    }).join('');

    toolbar.classList.remove('hidden');
    renderComponents(allComponents);
  }

  function filterItems(items){
    const categoryFilter = document.getElementById('category-filter-select').value;
    const brand = document.getElementById('brand-select').value;
    const priceMinRaw = document.getElementById('price-min-input').value;
    const priceMin = priceMinRaw === '' ? null : Number(priceMinRaw);
    const priceMaxRaw = document.getElementById('price-max-input').value;
    const priceMax = priceMaxRaw === '' ? null : Number(priceMaxRaw);
    const search = document.getElementById('search-input').value.trim().toLowerCase();
    const showOutOfStock = document.getElementById('show-out-of-stock-checkbox').checked;
    const fields = CATEGORY_FILTER_FIELDS[categoryFilter] || [];

    return items.filter(item => {
      if(item.en_stock === false && !showOutOfStock) return false;
      if(categoryFilter && item.categorie !== categoryFilter) return false;
      if(brand && getBrand(item.nom) !== brand) return false;
      if(priceMin !== null && item.prix_indicatif < priceMin) return false;
      if(priceMax !== null && item.prix_indicatif > priceMax) return false;
      if(search && !item.nom.toLowerCase().includes(search)) return false;

      if(categoryFilter && item.categorie === categoryFilter){
        const specs = item.specs || {};
        for(const field of fields){
          const inputEl = document.getElementById(specFilterInputId(field.key));
          if(!inputEl || inputEl.value === '') continue;

          if(field.kind === 'select'){
            if(specs[field.key] !== inputEl.value) return false;
          }else if(field.kind === 'select-list'){
            if(!(specs[field.key] || []).includes(inputEl.value)) return false;
          }else if(field.kind === 'min'){
            if(!(Number(specs[field.key]) >= Number(inputEl.value))) return false;
          }else if(field.kind === 'max'){
            if(!(Number(specs[field.key]) <= Number(inputEl.value))) return false;
          }
        }
      }

      return true;
    });
  }

  async function loadComponents(){
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      // data.components est un objet groupé par catégorie ({CPU:[...], RAM:[...]}) :
      // on l'aplatit en tableau, c'est ce que renderComponents() attend.
      allComponents = Object.values(data.components || {}).flat();
      populateBrandOptions();
      if(browseCategory){
        document.getElementById('category-filter-select').value = browseCategory;
        onCategoryFilterChange();
        const hint = document.getElementById('config-hint');
        hint.innerHTML = `Tous les composants "${escapeHtml(browseCategory)}". Sélectionnes-en un pour revenir au configurateur, ou <a href="/configurateur" style="color:var(--led);">annule</a> pour revenir sans choisir.`;
        hint.classList.add('show');
      }else{
        renderComponents(allComponents);
      }
      applyIncomingAISuggestion();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  // Catégories repliées par l'utilisateur — persiste tant que la page n'est
  // pas rechargée, pour ne pas avoir à tout réouvrir à chaque sélection.
  let collapsedCategories = new Set();

  function toggleCategory(category){
    if(collapsedCategories.has(category)) collapsedCategories.delete(category);
    else collapsedCategories.add(category);
    renderComponents(allComponents);
  }

  // Avec des centaines de composants dans une catégorie, tout afficher d'un
  // coup rendrait la page interminable à parcourir. On n'affiche qu'un lot à
  // la fois par catégorie, avec un bouton "Voir plus" pour en révéler
  // davantage — combiné à la recherche/aux filtres pour retrouver un
  // composant précis sans scroller.
  const PAGE_SIZE = 8;
  let visibleCounts = {};

  // "Voir plus" ouvre une page dédiée à cette seule catégorie (?voir_categorie=...)
  // qui affiche TOUS ses composants (pas de pagination là-bas — c'est
  // justement la vue "voir tout") plutôt que de révéler quelques cartes de
  // plus sur place. Sélectionner un composant sur cette page ramène
  // directement au configurateur (voir selectComponent).
  const urlParams = new URLSearchParams(window.location.search);
  const browseCategory = urlParams.get('voir_categorie');

  // Un changement de filtre peut faire apparaître des résultats qui étaient
  // au-delà du lot actuellement affiché : on repart du premier lot pour
  // chaque catégorie plutôt que de les cacher sans le dire.
  function onFilterChange(){
    visibleCounts = {};
    renderComponents(allComponents);
  }

  function showMore(category){
    window.location.href = `/configurateur?voir_categorie=${encodeURIComponent(category)}`;
  }

  // Appelé par le menu de tri (data-onchange, sans accès aux variables let).
  function rerenderComponents(){ renderComponents(allComponents); }

  // Badge de prix (historique relevé chaque jour) : seulement avec assez de
  // relevés pour ne jamais afficher une "baisse" ou un "plus bas" trompeur.
  function priceTrendBadge(item){
    const t = item.tendance_prix, prix = Number(item.prix_indicatif);
    if(!t || !prix) return '';
    if(t.precedent && prix < t.precedent * 0.97){
      return `<span class="price-badge">En baisse −${Math.round((1 - prix / t.precedent) * 100)} %</span>`;
    }
    if(t.releves_30j >= 7 && t.min_30j && prix <= t.min_30j * 1.005){
      return `<span class="price-badge">Plus bas depuis 30 j</span>`;
    }
    return '';
  }

  function renderComponents(components){
    const container = document.getElementById('components-container');
    container.innerHTML = '';
    const byCategory = {};
    components.forEach(c => {
      if(!byCategory[c.categorie]) byCategory[c.categorie] = [];
      byCategory[c.categorie].push(c);
    });

    // Total déjà engagé sur les AUTRES catégories, pour calculer combien il
    // reste de budget disponible pour la catégorie qu'on est en train d'afficher.
    const totalSelected = Object.values(selectedComponents).reduce((sum, c) => sum + Number(c.prix_indicatif || 0), 0);

    const categoryFilter = document.getElementById('category-filter-select').value;

    Object.entries(byCategory).forEach(([category, items]) => {
      // Une catégorie est choisie dans le filtre : on n'affiche qu'elle,
      // pas des sections vides pour toutes les autres.
      if(categoryFilter && category !== categoryFilter) return;

      const section = document.createElement('div');
      section.className = 'category-section';

      // Calculé AVANT le titre (et même si la catégorie est repliée) : le
      // nombre affiché entre parenthèses doit refléter les filtres actifs
      // (recherche, marque, prix...), pas juste le total brut de la catégorie.
      const visibleItems = filterItems(items);

      const isCollapsed = collapsedCategories.has(category);
      const title = document.createElement('h3');
      title.className = 'category-toggle';
      title.innerHTML = `<span>${category} (${visibleItems.length})</span><span class="toggle-arrow"><i class="ph ph-caret-${isCollapsed ? 'right' : 'down'}" aria-hidden="true"></i></span>`;
      title.onclick = () => toggleCategory(category);
      section.appendChild(title);

      if(isCollapsed){
        container.appendChild(section);
        return;
      }

      const isBrowseTarget = browseCategory === category;

      const grid = document.createElement('div');
      grid.className = `components-grid${isBrowseTarget ? ' browse-mode' : ''}`;

      const alreadySpentElsewhere = totalSelected - Number(selectedComponents[category]?.prix_indicatif || 0);
      const remainingForCategory = budgetMax !== null ? budgetMax - alreadySpentElsewhere : null;

      // Catégorie sans aucun résultat pour les filtres actifs (recherche,
      // marque, prix...) : on ne l'affiche plus du tout, plutôt qu'une
      // section vide avec juste un message — inutile de garder une
      // catégorie visible si rien à y montrer.
      if(visibleItems.length === 0){
        return;
      }

      // Un composant déjà choisi dans cette catégorie : on n'affiche QUE lui
      // (les filtres deviennent sans objet une fois le choix fait), pour que
      // la sélection soit immédiatement lisible sans être noyée parmi les
      // autres options. Un clic dessus (voir selectComponent) désélectionne
      // et réaffiche tout — c'est la seule porte de sortie de ce mode.
      const selectedInCategory = selectedComponents[category];
      const sortedItems = sortItems(visibleItems);
      const shownCount = isBrowseTarget ? Infinity : (visibleCounts[category] || PAGE_SIZE);
      const itemsToShow = selectedInCategory ? [selectedInCategory] : sortedItems.slice(0, shownCount);

      itemsToShow.forEach(item => {
        const specs = item.specs || {};
        const specsText = Object.entries(specs).map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(Array.isArray(v) ? v.join(', ') : v)}`).join(' · ');

        const isOverBudget = remainingForCategory !== null && item.prix_indicatif > remainingForCategory;
        const isSelected = selectedComponents[category]?.id === item.id;
        const isOutOfStock = item.en_stock === false;

        // Un <div> (pas <button>) car le bouton "Détail" imbriqué à
        // l'intérieur ne serait pas valide dans un <button>.
        const btn = document.createElement('div');
        btn.className = `component-btn ${isSelected ? 'selected' : ''} ${isOverBudget ? 'over-budget' : ''} ${isOutOfStock ? 'out-of-stock' : ''}`;
        btn.tabIndex = 0;
        const imageHtml = item.image_url ? `<div class="component-thumb${item.image_processed ? ' is-transparent' : ''}"><img src="${escapeHtml(item.image_url)}?w=320" alt="${escapeHtml(item.nom)}" loading="lazy" decoding="async"></div>` : '';
        const outOfStockBadge = isOutOfStock ? `<span class="out-of-stock-badge">Épuisé</span>` : '';
        btn.innerHTML = `
          ${outOfStockBadge}
          ${isOutOfStock ? '' : priceTrendBadge(item)}
          ${imageHtml}
          <span class="name">${escapeHtml(item.nom)}</span>
          <span class="specs">${specsText}</span>
          <span class="price">${item.prix_indicatif}€</span>
          <button type="button" class="detail-btn">Détail</button>
        `;
        btn.onclick = () => selectComponent(category, item);
        btn.querySelector('.detail-btn').onclick = (event) => {
          event.stopPropagation();
          showComponentDetail(item.id);
        };
        grid.appendChild(btn);
      });

      if(!selectedInCategory && sortedItems.length > shownCount){
        const showMoreBtn = document.createElement('button');
        showMoreBtn.type = 'button';
        showMoreBtn.className = 'show-more-btn';
        showMoreBtn.textContent = `Voir plus (${sortedItems.length - shownCount})`;
        showMoreBtn.onclick = () => showMore(category);
        grid.appendChild(showMoreBtn);
      }

      section.appendChild(grid);
      container.appendChild(section);
    });
  }

  // Cliquer sur un composant déjà sélectionné le désélectionne plutôt que
  // de le re-sélectionner sans effet visible.
  function selectComponent(category, item){
    if(selectedComponents[category]?.id === item.id){
      delete selectedComponents[category];
    }else{
      selectedComponents[category] = item;
    }
    saveDraftToLocalStorage();

    // Sur la page dédiée "voir toute la catégorie", choisir un composant
    // ramène directement au configurateur — le brouillon localStorage qu'on
    // vient de sauvegarder juste au-dessus est relu automatiquement au
    // chargement (restoreDraftIfAny), la sélection n'est donc pas perdue.
    if(browseCategory === category){
      window.location.href = '/configurateur';
      return;
    }

    renderComponents(allComponents);
    updateBuildPreview();
    checkCompatibilityLive();
  }

  // Brouillon auto-sauvegardé dans ce navigateur : si la page est rechargée
  // en plein milieu de la sélection (par accident, ou pour revenir plus
  // tard), la config en cours n'est pas perdue. Purement local — jamais
  // envoyé au serveur tant que "Sauvegarder" n'est pas cliqué explicitement.
  const DRAFT_STORAGE_KEY = 'pc_configurator_draft';

  function saveDraftToLocalStorage(){
    try{
      const composants_json = {};
      Object.entries(selectedComponents).forEach(([cat, item]) => { composants_json[cat] = item.id; });
      if(Object.keys(composants_json).length === 0){
        localStorage.removeItem(DRAFT_STORAGE_KEY);
      }else{
        localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(composants_json));
      }
    }catch(e){}
  }

  // N'est appelé qu'au chargement, et seulement si aucune suggestion IA,
  // config partagée ou config à modifier n'a déjà été appliquée — sinon on
  // écraserait ça avec un vieux brouillon local.
  function restoreDraftIfAny(){
    let raw;
    try{ raw = localStorage.getItem(DRAFT_STORAGE_KEY); }catch(e){ raw = null; }
    if(!raw) return;

    let draft;
    try{ draft = JSON.parse(raw); }catch(e){ return; }

    let appliedCount = 0;
    Object.entries(draft).forEach(([categorie, id]) => {
      const item = allComponents.find(c => c.id === id);
      if(item){ selectedComponents[categorie] = item; appliedCount++; }
    });
    if(appliedCount === 0) return;

    renderComponents(allComponents);
    updateBuildPreview();
    const hint = document.getElementById('config-hint');
    hint.textContent = "Ta sélection précédente a été restaurée automatiquement.";
    hint.classList.add('show');
    checkCompatibilityLive();
  }

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

    // Détails complets Amazon (mémoire, dimensions, poids...) — informatif,
    // en plus des specs de compatibilité ci-dessus. Replié par défaut (peut
    // faire plusieurs dizaines de lignes).
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
      <h3>${escapeHtml(item.nom)}</h3>
      ${item.page ? `<a class="detail-page-link" href="${escapeHtml(item.page)}">Fiche complète : prix, FPS, compatibilité <i class="ph ph-arrow-right" aria-hidden="true"></i></a>` : ''}
      ${imageHtml}
      <p class="detail-price-ref">Prix de référence : ${item.prix_indicatif}€</p>
      <div class="follow-slot"></div>
      <div class="price-history-slot"></div>
      ${descriptionHtml}
      <div class="detail-specs">${specsHtml}</div>
      <h4 style="margin-top:18px; margin-bottom:8px;">Prix relevés</h4>
      <div class="detail-prices">${pricesHtml}</div>
      ${amazonDetailsHtml}
    `;
    document.getElementById('detail-modal-overlay').classList.add('show');
    PCAccount.mountFollow(document.querySelector('#detail-modal-content .follow-slot'), item);
    if(window.PCPriceHistory) PCPriceHistory.mount(document.querySelector('#detail-modal-content .price-history-slot'), item.id);
  }

  function closeDetailModal(){
    document.getElementById('detail-modal-overlay').classList.remove('show');
  }

  // Vérifie la compatibilité de la sélection en cours, dès qu'au moins 2
  // composants sont choisis. Une sélection encore partielle n'est jamais
  // signalée comme "incompatible" à tort — seules les paires réellement
  // sélectionnées sont vérifiées.
  async function checkCompatibilityLive(){
    const compatBox = document.getElementById('compat-result');
    const components = Object.values(selectedComponents);

    if(components.length < 2){
      compatBox.innerHTML = '';
      return;
    }

    try{
      const res = await fetch(API_BASE + '/api/check-compatibility', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ components }),
      });
      const data = await res.json();

      if(data.compatible){
        compatBox.innerHTML = `<div class="compat-result compat-ok"><i class="ph ph-check-circle" aria-hidden="true"></i> Compatible avec les composants sélectionnés.</div>`;
      }else{
        const list = (data.erreurs || []).map(e => `<li>${e}</li>`).join('');
        compatBox.innerHTML = `<div class="compat-result compat-fail"><i class="ph ph-warning-circle" aria-hidden="true"></i> Incompatibilité détectée :<ul>${list}</ul></div>`;
      }
    }catch(e){
      compatBox.innerHTML = '';
    }
  }

  function updateBuildPreview(){
    const content = document.getElementById('preview-content');
    const entries = Object.entries(selectedComponents);
    content.innerHTML = entries
      .map(([cat, item]) => `<p><strong>${escapeHtml(cat)}:</strong> ${escapeHtml(item.nom)}, ${item.prix_indicatif}€</p>`)
      .join('') || '<p>Aucun composant sélectionné</p>';

    const total = entries.reduce((sum, [, item]) => sum + Number(item.prix_indicatif || 0), 0);
    const summary = document.getElementById('budget-summary');

    if(budgetMax === null){
      summary.innerHTML = `<div class="total">Total : ${total.toFixed(2)}€</div>`;
    }else{
      const remaining = budgetMax - total;
      const cls = remaining < 0 ? 'over' : 'ok';
      const label = remaining < 0
        ? `Dépassement : ${Math.abs(remaining).toFixed(2)}€`
        : `Budget restant : ${remaining.toFixed(2)}€`;
      summary.innerHTML = `<div class="total">Total : ${total.toFixed(2)}€</div><div class="remaining ${cls}">${label}</div>`;
    }
  }

  // Affiche le bandeau d'aide si on arrive depuis le bouton "Intermédiaire" de l'accueil.
  function checkHintParam(){
    const params = new URLSearchParams(window.location.search);
    if(params.get('hint') === 'intermediaire'){
      const hint = document.getElementById('config-hint');
      hint.textContent = "Personnalisez chaque composant, on vérifie la compatibilité pour vous automatiquement.";
      hint.classList.add('show');
    }
  }

  // Si on arrive depuis "Mon compte" pour modifier une config déjà
  // sauvegardée (bouton "Modifier"), elle a été déposée dans sessionStorage
  // avant la navigation. On l'applique et on bascule en mode édition :
  // "Sauvegarder" mettra à jour cette configuration au lieu d'en créer une
  // nouvelle (voir saveBuild()).
  function applyIncomingEditBuild(){
    const raw = sessionStorage.getItem('editBuild');
    if(!raw) return false;
    sessionStorage.removeItem('editBuild');

    let edit;
    try{ edit = JSON.parse(raw); }catch(e){ return false; }
    if(!edit) return false;

    editingBuildId = edit.id;
    editingBuildNom = edit.nom;

    let appliedCount = 0;
    Object.entries(edit.composants_json || {}).forEach(([categorie, id]) => {
      const item = allComponents.find(c => c.id === id);
      if(item){
        selectedComponents[categorie] = item;
        appliedCount++;
      }
    });

    renderComponents(allComponents);
    updateBuildPreview();
    saveDraftToLocalStorage();

    const hint = document.getElementById('config-hint');
    hint.textContent = `Modification de "${edit.nom}" : cliquer sur "Sauvegarder" mettra à jour cette configuration existante.`;
    hint.classList.add('show');
    checkCompatibilityLive();
    return true;
  }

  // Si on arrive depuis l'estimateur FPS (bouton "Remplacer dans ma
  // configuration" sur une suggestion de composant plus adapté), le
  // remplacement a été déposé dans sessionStorage avant la navigation. À la
  // différence d'une suggestion IA complète, celui-ci s'applique PAR-DESSUS
  // le brouillon existant (restauré ici en premier) : on ne touche qu'à la
  // catégorie concernée, tout le reste de la config est conservé.
  function applyIncomingComponentSwap(){
    let raw;
    try{ raw = sessionStorage.getItem('componentSwap'); }catch(e){ raw = null; }
    if(!raw) return false;
    sessionStorage.removeItem('componentSwap');

    let swap;
    try{ swap = JSON.parse(raw); }catch(e){ return false; }

    restoreDraftIfAny();

    const item = allComponents.find(c => c.id === swap.id);
    if(!item) return false;

    selectedComponents[swap.categorie] = item;
    saveDraftToLocalStorage();
    renderComponents(allComponents);
    updateBuildPreview();

    const hint = document.getElementById('config-hint');
    hint.textContent = `"${item.nom}" a remplacé ton ancien composant ${swap.categorie} suite à la suggestion de l'estimateur FPS.`;
    hint.classList.add('show');
    checkCompatibilityLive();
    return true;
  }

  // Si on arrive depuis l'assistant IA (bouton "Utiliser cette configuration"),
  // la suggestion a été déposée dans sessionStorage avant la navigation.
  // On l'applique ici, une seule fois, puis on nettoie.
  function applyIncomingAISuggestion(){
    if(applyIncomingEditBuild()) return;
    if(applyIncomingComponentSwap()) return;

    const raw = sessionStorage.getItem('aiSuggestion');
    if(raw){
      sessionStorage.removeItem('aiSuggestion');
      let suggestion;
      try{ suggestion = JSON.parse(raw); }catch(e){ return; }

      let appliedCount = 0;
      Object.entries(FIELD_TO_CATEGORY).forEach(([field, category]) => {
        const id = suggestion[field];
        const item = allComponents.find(c => c.id === id);
        if(item){
          selectedComponents[category] = item;
          appliedCount++;
        }
      });

      renderComponents(allComponents);
      updateBuildPreview();
      saveDraftToLocalStorage();

      const hint = document.getElementById('config-hint');
      hint.textContent = appliedCount === Object.keys(FIELD_TO_CATEGORY).length
        ? "Configuration proposée par l'assistant IA appliquée ci-dessous."
        : `Configuration IA appliquée partiellement (${appliedCount}/${Object.keys(FIELD_TO_CATEGORY).length} composants trouvés).`;
      hint.classList.add('show');
      checkCompatibilityLive();
      return;
    }

    // Sinon, une configuration partagée par lien a peut-être été déposée
    // (depuis /build/{id}, bouton "Reprendre cette configuration").
    const sharedRaw = sessionStorage.getItem('sharedBuild');
    if(sharedRaw){
      sessionStorage.removeItem('sharedBuild');
      let shared;
      try{ shared = JSON.parse(sharedRaw); }catch(e){ return; }

      let appliedCount = 0;
      Object.entries(shared).forEach(([categorie, id]) => {
        const item = allComponents.find(c => c.id === id);
        if(item){
          selectedComponents[categorie] = item;
          appliedCount++;
        }
      });

      renderComponents(allComponents);
      updateBuildPreview();
      saveDraftToLocalStorage();

      const hint = document.getElementById('config-hint');
      hint.textContent = appliedCount > 0
        ? "Configuration partagée appliquée ci-dessous, modifie-la comme tu veux."
        : "Impossible de retrouver les composants de cette configuration partagée.";
      hint.classList.add('show');
      checkCompatibilityLive();
      return;
    }

    // Aucune suggestion IA, config partagée, ni config à modifier : on
    // restaure un éventuel brouillon local laissé par une visite précédente.
    restoreDraftIfAny();
  }

  checkHintParam();
  loadComponents();
  updateBuildPreview();
  loadAffiliateConfig();

  // Sauvegarde la sélection en cours. Redirige vers /compte si personne
  // n'est connecté — la sauvegarde côté serveur nécessite un compte.
  async function saveBuild(){
    if(Object.keys(selectedComponents).length === 0){
      alert('Sélectionnez au moins un composant avant de sauvegarder.');
      return;
    }

    const meRes = await fetch(API_BASE + '/api/auth/me', { credentials: 'include' });
    const me = await meRes.json();

    if(!me.logged_in){
      sessionStorage.setItem('pendingBuild', JSON.stringify(selectedComponents));
      window.location.href = '/compte';
      return;
    }

    const nom = prompt('Nom de cette configuration :', editingBuildId ? editingBuildNom : 'Ma config');
    if(!nom) return;

    const composants_json = {};
    Object.entries(selectedComponents).forEach(([cat, item]) => { composants_json[cat] = item.id; });

    const isEditing = !!editingBuildId;
    const confirmBox = document.getElementById('save-confirmation');
    try{
      const res = isEditing
        ? await fetch(API_BASE + `/api/builds/${editingBuildId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ nom, composants_json }),
          })
        : await fetch(API_BASE + '/api/builds', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({ nom, composants_json }),
          });
      if(res.ok){
        const data = await res.json();
        // Config enregistrée : on repart d'une sélection vide (brouillon local
        // compris) pour pouvoir en composer une nouvelle. La prochaine
        // sauvegarde crée donc une nouvelle config au lieu de modifier celle-ci.
        selectedComponents = {};
        editingBuildId = null;
        editingBuildNom = null;
        renderComponents(allComponents);
        updateBuildPreview();
        saveDraftToLocalStorage();
        checkCompatibilityLive();
        document.getElementById('config-hint').classList.remove('show');
        // Affiche la config sauvegardée directement ici, sans forcer à
        // aller sur /compte pour la retrouver.
        confirmBox.innerHTML = `
          <div class="compat-result compat-ok">
            ✓ Configuration "${escapeHtml(nom)}" ${isEditing ? 'mise à jour' : 'sauvegardée'}.
            <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
              <a href="/build/${data.id}" target="_blank" class="btn btn-primary">Voir la fiche partageable</a>
              <a href="/compte" class="btn btn-secondary" style="padding:8px 16px; font-size:0.8rem;">Voir mes configurations</a>
            </div>
          </div>
        `;
      }else{
        confirmBox.innerHTML = `<div class="compat-result compat-fail">Erreur lors de la sauvegarde.</div>`;
      }
    }catch(e){
      confirmBox.innerHTML = `<div class="compat-result compat-fail">Erreur réseau lors de la sauvegarde.</div>`;
    }
  }

  // Ajoute tous les composants sélectionnés (qui ont un ASIN Amazon connu)
  // au panier Amazon de la personne qui clique, en un seul aller — via
  // l'endpoint historique /gp/aws/cart/add.html d'Amazon, qui accepte
  // plusieurs ASIN/quantité par requête. Aucune API ni connexion nécessaire
  // de notre côté : la commande utilise directement la session Amazon déjà
  // ouverte dans le navigateur de la personne (ou lui demande de se
  // connecter si besoin), exactement comme suivre un lien produit normal.
  function addAllToAmazonCart(){
    const withAsin = Object.values(selectedComponents).filter(item => item.asin);
    if(withAsin.length === 0){
      alert('Aucun des composants sélectionnés n\'a de lien Amazon connu.');
      return;
    }

    const params = new URLSearchParams();
    if(amazonTag) params.set('AssociateTag', amazonTag);
    withAsin.forEach((item, i) => {
      params.set(`ASIN.${i + 1}`, item.asin);
      params.set(`Quantity.${i + 1}`, '1');
    });

    const skipped = Object.keys(selectedComponents).length - withAsin.length;
    if(skipped > 0){
      alert(`${skipped} composant(s) sans lien Amazon connu ne seront pas ajoutés au panier.`);
    }

    window.open(`https://www.amazon.fr/gp/aws/cart/add.html?${params.toString()}`, '_blank', 'noopener');
  }
