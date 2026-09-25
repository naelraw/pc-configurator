  const API_BASE = window.location.origin;
  let allComponents = [];
  let selectedA = null;
  let selectedB = null;

  async function loadComponents(){
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      allComponents = Object.values(data.components || {}).flat();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  function normalize(str){
    return (str || '')
      .toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function matchesQuery(nom, query){
    const normalizedNom = normalize(nom);
    const tokens = normalize(query).split(/\s+/).filter(Boolean);
    return tokens.every(token => normalizedNom.includes(token));
  }

  function wordMatchScore(haystack, token){
    const idx = haystack.indexOf(token);
    if(idx === -1) return 0;
    const precededByBoundary = idx === 0 || haystack[idx - 1] === ' ' || haystack[idx - 1] === '-';
    const endIdx = idx + token.length;
    const followedByBoundary = endIdx === haystack.length || haystack[endIdx] === ' ' || haystack[endIdx] === '-';
    if(precededByBoundary && followedByBoundary) return 15;
    if(precededByBoundary) return 8;
    return 1;
  }

  function scoreRelevance(nom, query){
    const normalizedNom = normalize(nom);
    const normalizedQuery = normalize(query);
    if(normalizedNom === normalizedQuery) return 1000;
    if(normalizedNom.startsWith(normalizedQuery)) return 500;
    const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
    return tokens.reduce((score, token) => score + wordMatchScore(normalizedNom, token), 0);
  }

  // Une fois le composant A choisi, la recherche B se limite à la MÊME
  // catégorie — comparer un CPU à un GPU n'a pas de sens, autant l'empêcher
  // dès la recherche plutôt que de laisser choisir puis afficher un
  // avertissement après coup.
  function handleSearchInput(slot){
    const input = document.getElementById(`search-${slot}`);
    const resultsBox = document.getElementById(`results-${slot}`);
    const query = input.value.trim();

    if(!query){
      resultsBox.classList.remove('show');
      resultsBox.innerHTML = '';
      return;
    }

    const restrictCategory = slot === 'b' && selectedA ? selectedA.categorie : null;
    // Le composant déjà choisi de l'autre côté (ou une autre fiche du même
    // modèle) n'est jamais proposé : le comparer à lui-même n'a pas de sens.
    const other = slot === 'a' ? selectedB : selectedA;

    const matches = allComponents
      .filter(c => (!restrictCategory || c.categorie === restrictCategory) && matchesQuery(c.nom, query)
        && !(other && isSameComponent(c, other)))
      .sort((a, b) => scoreRelevance(b.nom, query) - scoreRelevance(a.nom, query))
      .slice(0, 12);

    if(matches.length === 0){
      resultsBox.innerHTML = `<div class="search-result-item">Aucun composant trouvé${restrictCategory ? ` en ${escapeHtml(restrictCategory)}` : ''}</div>`;
      resultsBox.classList.add('show');
      return;
    }

    resultsBox.innerHTML = matches.map(c => `
      <div class="search-result-item" data-onclick="selectComponent('${slot}', ${c.id})">
        ${escapeHtml(c.nom)}<br><span class="cat">${escapeHtml(c.categorie)}</span>
      </div>
    `).join('');
    resultsBox.classList.add('show');
  }

  function isSameComponent(x, y){
    return x.id === y.id || normalize(x.nom) === normalize(y.nom);
  }

  function selectComponent(slot, id){
    const component = allComponents.find(c => c.id === id);
    if(!component) return;
    const other = slot === 'a' ? selectedB : selectedA;
    if(other && isSameComponent(component, other)){
      const box = document.getElementById(`results-${slot}`);
      box.innerHTML = "<div class='search-result-item'>Choisis un composant différent de celui d’en face.</div>";
      box.classList.add('show');
      return;
    }

    document.getElementById(`search-${slot}`).value = component.nom;
    document.getElementById(`results-${slot}`).classList.remove('show');

    if(slot === 'a'){
      selectedA = component;
      // Changer A après avoir choisi B, dans une catégorie différente,
      // invaliderait la restriction de B — plus simple de réinitialiser B.
      if(selectedB && selectedB.categorie !== component.categorie){
        selectedB = null;
        document.getElementById('search-b').value = '';
      }
    }else{
      selectedB = component;
    }

    if(selectedA && selectedB) runComparison();
  }

  async function runComparison(){
    const container = document.getElementById('compare-result');
    container.innerHTML = '<p style="color:var(--text-dim); padding:20px 0;">Comparaison...</p>';

    try{
      const res = await fetch(`${API_BASE}/api/compare-performance?id_a=${selectedA.id}&id_b=${selectedB.id}`);
      const data = await res.json();
      if(!res.ok){
        container.innerHTML = `<p style="color:var(--danger);">${escapeHtml(data.detail || 'Erreur lors de la comparaison.')}</p>`;
        return;
      }
      renderComparison(data);
    }catch(e){
      container.innerHTML = '<p style="color:var(--danger);">Erreur réseau lors de la comparaison.</p>';
    }
  }

  // Image, anneau de score, nom, prix : tout dans UNE seule carte par côté
  // plutôt que l'image d'un côté et l'anneau plus bas dans une section à
  // part — pour que chaque composant reste un bloc visuel cohérent (retour
  // utilisateur : le score doit rester "avec" l'image, pas détaché plus bas).
  function sideCardHtml(side, isWinner){
    const thumbHtml = side.image_url
      ? `<div class="compare-heading-thumb${side.image_processed ? ' is-transparent' : ''}"><img src="${escapeHtml(side.image_url)}?w=240" alt="${escapeHtml(side.nom)}"></div>`
      : '';
    const ringHtml = side.score !== undefined ? `
      <div class="vs-score-ring${isWinner ? ' leader' : ''}" style="--score:${side.score}">
        <div class="vs-score-ring-inner">
          <span class="vs-score-value">${side.score}</span>
          <span class="vs-score-max">/100</span>
        </div>
      </div>
    ` : '';
    const amazonBtnHtml = side.asin
      ? `<a href="${escapeHtml(withAffiliateTag('https://www.amazon.fr/dp/' + side.asin, 'Amazon'))}" target="_blank" rel="noopener noreferrer sponsored" class="btn btn-secondary vs-amazon-btn" data-onclick="event.stopPropagation()">Voir sur Amazon ↗</a>`
      : '';

    // Seul le NOM ouvre la fiche détail (pas toute la carte) — pour ne pas
    // gêner le clic sur le bouton Amazon ou simplement regarder l'image/le
    // score sans déclencher la modale par accident.
    return `
      <div class="vs-heading">
        ${thumbHtml}
        ${ringHtml}
        <div class="vs-heading-nom vs-heading-nom-link" data-onclick="showComponentDetail(${side.id})" title="Voir la fiche détaillée">${escapeHtml(side.nom)}</div>
        ${side.prix_indicatif ? `<div class="vs-heading-prix">${side.prix_indicatif}€</div>` : ''}
        ${amazonBtnHtml}
      </div>
    `;
  }

  function renderComparison(data){
    const container = document.getElementById('compare-result');
    const { a, b, mode, avertissement } = data;
    const winner = mode === 'performance' && a.score >= b.score ? a : (mode === 'performance' ? b : null);

    let html = `<div class="vs-columns">${sideCardHtml(a, a === winner)}${sideCardHtml(b, b === winner)}</div>`;

    if(avertissement){
      html += `<p style="color:var(--text-dim); font-size:0.85rem; text-align:center; margin-top:10px;">${escapeHtml(avertissement)}</p>`;
    }

    if(mode === 'performance'){
      html += `<p class="vs-perf-summary"><strong>${escapeHtml(winner.nom)}</strong> obtient le meilleur score de performance des deux.</p>`;

      if(a.prix_indicatif && b.prix_indicatif){
        const ratioA = a.score / a.prix_indicatif;
        const ratioB = b.score / b.prix_indicatif;
        const meilleurRapport = ratioA >= ratioB ? a : b;
        html += `<p class="vs-value-note">💰 <strong>${escapeHtml(meilleurRapport.nom)}</strong> offre le meilleur rapport performance/prix.</p>`;
      }

      // Le score résume tout en un chiffre, mais certains veulent voir le
      // détail derrière — specs brutes en complément, jamais à la place.
      html += renderSpecsTable(a, b, 'Caractéristiques');
    }else if(mode === 'ram'){
      const bestCap = a.capacite_go && b.capacite_go && a.capacite_go !== b.capacite_go ? (a.capacite_go > b.capacite_go ? 'a' : 'b') : null;
      const bestFreq = a.frequence_mhz && b.frequence_mhz && a.frequence_mhz !== b.frequence_mhz ? (a.frequence_mhz > b.frequence_mhz ? 'a' : 'b') : null;
      html += `
        <div class="vs-specs-block">
          <div class="vs-spec-row vs-spec-header">
            <span class="vs-spec-label"></span>
            <span class="vs-spec-val">${escapeHtml(a.nom)}</span>
            <span class="vs-spec-val">${escapeHtml(b.nom)}</span>
          </div>
          <div class="vs-spec-row">
            <span class="vs-spec-label">Capacité</span>
            <span class="vs-spec-val${bestCap === 'a' ? ' is-best' : ''}">${a.capacite_go ? a.capacite_go + ' Go' : '?'}</span>
            <span class="vs-spec-val${bestCap === 'b' ? ' is-best' : ''}">${b.capacite_go ? b.capacite_go + ' Go' : '?'}</span>
          </div>
          <div class="vs-spec-row">
            <span class="vs-spec-label">Fréquence</span>
            <span class="vs-spec-val${bestFreq === 'a' ? ' is-best' : ''}">${a.frequence_mhz ? a.frequence_mhz + ' MHz' : '?'}</span>
            <span class="vs-spec-val${bestFreq === 'b' ? ' is-best' : ''}">${b.frequence_mhz ? b.frequence_mhz + ' MHz' : '?'}</span>
          </div>
        </div>
        <p style="color:var(--text-dim); font-size:0.82rem; text-align:center; margin-top:10px;">Plus de capacité aide le multitâche, une fréquence plus élevée améliore le débit mémoire (surtout notable sur CPU AMD Ryzen).</p>
      `;
    }else{
      html += renderSpecsTable(a, b, null);
    }

    container.innerHTML = html;
  }

  // Libellés lisibles et unités des caractéristiques (clés brutes en base).
  const SPEC_LABELS = {
    socket: 'Socket', tdp: 'Consommation (TDP)', wattage: 'Puissance', format: 'Format',
    ram_type: 'Type de mémoire', type: 'Type', m2_slots: 'Emplacements M.2', sata_ports: 'Ports SATA',
    formats_supportes: 'Formats de carte mère', gpu_max_length_mm: 'Carte graphique max.',
    cpu_cooler_max_height_mm: 'Ventirad max.', longueur_mm: 'Longueur', hauteur_mm: 'Hauteur',
    sockets_supportes: 'Sockets supportés', couleur: 'Couleur',
    coeurs: 'Cœurs', threads: 'Threads', frequence_base_ghz: 'Fréquence de base',
    frequence_boost_ghz: 'Fréquence boost', cache_l3_mo: 'Cache L3', memoire: 'Mémoire supportée',
    igpu: 'Graphique intégré', puce: 'Puce graphique', vram_go: 'Mémoire vidéo',
    type_memoire: 'Type de mémoire vidéo', bus_memoire_bits: 'Bus mémoire', chipset: 'Chipset',
    capacite_go: 'Capacité', frequence_mt_s: 'Fréquence', barrettes: 'Barrettes', latence_cl: 'Latence (CL)',
    interface: 'Interface', lecture_mo_s: 'Lecture séquentielle', ecriture_mo_s: 'Écriture séquentielle',
  };
  const SPEC_UNITS = { tdp: ' W', wattage: ' W', gpu_max_length_mm: ' mm', cpu_cooler_max_height_mm: ' mm', longueur_mm: ' mm', hauteur_mm: ' mm', frequence_base_ghz: ' GHz', frequence_boost_ghz: ' GHz', cache_l3_mo: ' Mo', vram_go: ' Go', bus_memoire_bits: ' bits', capacite_go: ' Go', frequence_mt_s: ' MT/s', lecture_mo_s: ' Mo/s', ecriture_mo_s: ' Mo/s' };
  const TYPE_RANK = { DDR3: 1, DDR4: 2, DDR5: 3, SATA: 1, NVMe: 2 };

  // Meilleure valeur d'une caractéristique : 'a', 'b' ou null (égalité,
  // valeur manquante, ou caractéristique où "mieux" dépend de l'usage :
  // longueur d'une carte graphique, hauteur d'un ventirad, format, socket...).
  function bestSide(key, va, vb, categorie){
    if(va === undefined || vb === undefined || va === null || vb === null) return null;
    let score;
    if(['wattage', 'm2_slots', 'sata_ports', 'gpu_max_length_mm', 'cpu_cooler_max_height_mm',
        'coeurs', 'threads', 'frequence_base_ghz', 'frequence_boost_ghz', 'cache_l3_mo', 'vram_go', 'bus_memoire_bits', 'capacite_go', 'frequence_mt_s', 'lecture_mo_s', 'ecriture_mo_s'].includes(key)){
      score = v => Number(v);                                    // plus = mieux
    }else if(key === 'formats_supportes' || key === 'sockets_supportes'){
      score = v => Array.isArray(v) ? v.length : 0;              // plus compatible = mieux
    }else if(key === 'type' || key === 'ram_type'){
      score = v => TYPE_RANK[v] || 0;                            // DDR5 > DDR4, NVMe > SATA
    }else if(key === 'latence_cl'){
      score = v => -Number(v);                                   // latence : moins = mieux
    }else if(key === 'tdp'){
      // Ventirad : capacité de refroidissement (plus = mieux) ;
      // processeur / carte graphique : consommation (moins = mieux).
      score = categorie === 'Refroidissement' ? (v => Number(v)) : (v => -Number(v));
    }else{
      return null;
    }
    const sa = score(va), sb = score(vb);
    if(!Number.isFinite(sa) || !Number.isFinite(sb) || sa === sb || (sa === 0 && sb === 0)) return null;
    return sa > sb ? 'a' : 'b';
  }

  function renderSpecsTable(a, b, titre){
    const specsA = a.specs || {};
    const specsB = b.specs || {};
    const keys = [...new Set([...Object.keys(specsA), ...Object.keys(specsB)])];
    if(keys.length === 0){
      return titre ? '' : '<p style="color:var(--text-dim); padding:16px 0; text-align:center;">Aucune caractéristique enregistrée pour comparer ces composants.</p>';
    }
    const categorie = a.categorie || (selectedA && selectedA.categorie);
    const fmt = (k, v) => v === undefined || v === null ? '-' : (Array.isArray(v) ? v.join(', ') : String(v).replace(/^(\d+)\.(\d+)$/, '$1,$2') + (SPEC_UNITS[k] || ''));
    let anyBest = false;
    const rows = keys.map(k => {
      const best = bestSide(k, specsA[k], specsB[k], categorie);
      if(best) anyBest = true;
      return `
      <div class="vs-spec-row">
        <span class="vs-spec-label">${escapeHtml(SPEC_LABELS[k] || k)}</span>
        <span class="vs-spec-val${best === 'a' ? ' is-best' : ''}">${escapeHtml(fmt(k, specsA[k]))}</span>
        <span class="vs-spec-val${best === 'b' ? ' is-best' : ''}">${escapeHtml(fmt(k, specsB[k]))}</span>
      </div>
    `;
    }).join('');
    return `
      <div class="vs-specs-block">
        ${titre ? `<h3 class="vs-specs-title">${escapeHtml(titre)}</h3>` : ''}
        ${anyBest ? '<p class="vs-specs-legend">En gras : la meilleure valeur des deux.</p>' : ''}
        <div class="vs-spec-row vs-spec-header">
          <span class="vs-spec-label"></span>
          <span class="vs-spec-val">${escapeHtml(a.nom)}</span>
          <span class="vs-spec-val">${escapeHtml(b.nom)}</span>
        </div>
        ${rows}
      </div>
    `;
  }

  // Même modale de détail (specs, description, prix relevés, tous les
  // détails Amazon) que le configurateur / compte / fiche partageable —
  // ouverte en cliquant sur la carte d'un des deux composants comparés.
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
      : '<p style="color:var(--text-dim); font-size:0.85rem;">Aucun prix de marché relevé.</p>';

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
  }

  document.getElementById('search-a').addEventListener('input', () => handleSearchInput('a'));
  document.getElementById('search-b').addEventListener('input', () => handleSearchInput('b'));

  document.addEventListener('click', (e) => {
    if(!e.target.closest('.vs-slot')){
      document.getElementById('results-a').classList.remove('show');
      document.getElementById('results-b').classList.remove('show');
    }
  });

  loadAffiliateConfig();
  loadComponents();
