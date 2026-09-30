  // Assistant IA en mode discussion (/api/assistant/chat) : questions sur
  // les composants, les jeux ou la config en cours, et configs complètes dont
  // chaque composant peut être ajouté à la config du configurateur (brouillon
  // localStorage, le même que celui du configurateur) sans quitter la page.
  // La discussion est gardée pour la visite (sessionStorage) : on peut aller
  // voir sa config ou une fiche produit et revenir la reprendre.
  const API_BASE = window.location.origin;
  const DISCUSSION_KEY = 'assistantDiscussion';
  const DRAFT_STORAGE_KEY = 'pc_configurator_draft';   // voir configurateur.js
  const FIELD_TO_CATEGORY = {
    cpu_id: 'CPU',
    motherboard_id: 'Carte mère',
    ram_id: 'RAM',
    gpu_id: 'GPU',
    psu_id: 'Alimentation',
    storage_id: 'Stockage',
    case_id: 'Boîtier',
  };
  const EXEMPLES = [
    'Une config gaming à 1000 €',
    'Quelle carte graphique pour jouer en 1440p ?',
    'Combien de FPS sur Fortnite avec ma config ?',
    'DDR4 ou DDR5, je prends quoi ?',
  ];

  let allComponents = [];
  let composantsParId = new Map();
  let discussion = [];     // [{role, content, suggestion?, fps?}]
  let enCours = false;

  const $ = id => document.getElementById(id);

  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Texte de l'IA -> HTML sûr : échappé d'abord, puis **gras** et listes à tirets.
  function formater(texte){
    const lignes = escapeHtml(String(texte || '').trim()).split('\n');
    let html = '', liste = false;
    lignes.forEach(l => {
      const puce = l.match(/^\s*[-•*]\s+(.*)/);
      if(puce){
        if(!liste){ html += '<ul>'; liste = true; }
        html += `<li>${puce[1]}</li>`;
        return;
      }
      if(liste){ html += '</ul>'; liste = false; }
      if(l.trim()) html += `<p>${l}</p>`;
    });
    if(liste) html += '</ul>';
    return html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }

  const prix = n => `${Number(n || 0).toFixed(2).replace('.', ',')} €`;

  // ------------------------------------------------------------------
  // Config du configurateur (brouillon partagé)
  // ------------------------------------------------------------------
  function lireMaConfig(){
    try{ return JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY)) || {}; }catch(e){ return {}; }
  }

  function ecrireMaConfig(config){
    try{ localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(config)); }catch(e){}
  }

  // ------------------------------------------------------------------
  // Affichage
  // ------------------------------------------------------------------
  function bulleAssistant(contenu, classe = ''){
    return `<div class="msg msg-ia ${classe}">
      <span class="msg-avatar" aria-hidden="true"><img src="/static/favicon.svg" alt="" width="16" height="16"></span>
      <div class="msg-corps">${contenu}</div>
    </div>`;
  }

  function carteConfig(suggestion, index){
    const maConfig = lireMaConfig();
    let total = 0, toutDedans = true;
    const lignes = Object.entries(FIELD_TO_CATEGORY).map(([champ, cat]) => {
      const item = composantsParId.get(suggestion[champ]);
      if(!item){
        return `<li class="cfg-ligne"><span class="cfg-cat">${escapeHtml(cat)}</span>
          <span class="cfg-nom cfg-vide">Pas disponible sur le site</span></li>`;
      }
      total += Number(item.prix_indicatif) || 0;
      const dedans = maConfig[cat] === item.id;
      if(!dedans) toutDedans = false;
      const bouton = dedans
        ? `<span class="cfg-ok"><i class="ph ph-check" aria-hidden="true"></i> Dans ta config</span>`
        : `<button type="button" class="cfg-btn cfg-ajouter" data-action="ajouter" data-msg="${index}" data-champ="${champ}">${maConfig[cat] ? 'Remplacer' : 'Ajouter'}</button>`;
      return `<li class="cfg-ligne">
        <span class="cfg-cat">${escapeHtml(cat)}</span>
        <button type="button" class="cfg-nom" data-action="detail" data-id="${item.id}">${escapeHtml(item.nom)}</button>
        <span class="cfg-prix">${prix(item.prix_indicatif)}</span>
        <span class="cfg-actions">
          ${bouton}
          <button type="button" class="cfg-btn cfg-changer" data-action="changer" data-msg="${index}" data-champ="${champ}" title="Demander un autre ${escapeHtml(cat)}"><i class="ph ph-arrows-clockwise" aria-hidden="true"></i><span>Changer</span></button>
        </span>
      </li>`;
    }).join('');
    const budget = Number(suggestion.budget_max) > 0 ? `<span class="cfg-budget">Budget ${prix(suggestion.budget_max)}</span>` : '';
    return `<div class="cfg-carte">
      <ul class="cfg-liste">${lignes}</ul>
      <div class="cfg-pied">
        <div class="cfg-total"><span>Total</span><strong>${prix(total)}</strong>${budget}</div>
        <div class="cfg-boutons">
          ${toutDedans
            ? '<a class="btn btn-primary" href="/configurateur">Voir ma config</a>'
            : `<button type="button" class="btn btn-primary" data-action="tout" data-msg="${index}"><i class="ph ph-plus" aria-hidden="true"></i> Tout ajouter à ma config</button>
               <a class="btn btn-secondary" href="/configurateur">Voir ma config</a>`}
        </div>
      </div>
    </div>`;
  }

  // Bouton d'ajout d'un composant à la config (même logique partout).
  function boutonAjout(item, maConfig){
    if(maConfig[item.categorie] === item.id){
      return `<span class="cfg-ok"><i class="ph ph-check" aria-hidden="true"></i> Dans ta config</span>`;
    }
    return `<button type="button" class="cfg-btn cfg-ajouter" data-action="ajouter-id" data-id="${item.id}">${maConfig[item.categorie] ? 'Remplacer' : 'Ajouter'}</button>`;
  }

  // Les 3 caractéristiques qui comptent le plus, par catégorie.
  const SPECS_RESUME = {
    'CPU': [['coeurs', ' cœurs'], ['frequence_boost_ghz', ' GHz'], ['socket', '']],
    'GPU': [['vram_go', ' Go'], ['type_memoire', ''], ['tdp', ' W']],
    'Carte mère': [['socket', ''], ['ram_type', ''], ['format', '']],
    'RAM': [['capacite_go', ' Go'], ['type', ''], ['frequence_mt_s', ' MT/s']],
    'Stockage': [['capacite_go', ' Go'], ['type', ''], ['interface', '']],
    'Alimentation': [['wattage', ' W'], ['certification', ''], ['modularite', '']],
    'Boîtier': [['format', ''], ['formats_supportes', '']],
    'Refroidissement': [['type_refroidissement', ''], ['hauteur_mm', ' mm']],
  };
  function resumeSpecs(item){
    const specs = item.specs || {};
    return (SPECS_RESUME[item.categorie] || [])
      .map(([k, unite]) => specs[k] == null || specs[k] === '' ? null : (Array.isArray(specs[k]) ? specs[k].join(', ') : specs[k]) + unite)
      .filter(Boolean).join(' · ');
  }

  // Composants dont parle une réponse (question, comparaison...) : chacun
  // s'ouvre dans la fenêtre de détail et peut être ajouté à la config.
  function panneauComposants(ids){
    const items = (ids || []).map(id => composantsParId.get(id)).filter(Boolean);
    if(!items.length) return '';
    const maConfig = lireMaConfig();
    return `<div class="cfg-carte cite-carte"><ul class="cfg-liste">${items.map(item => `
      <li class="cite-ligne">
        <button type="button" class="cite-image${item.image_processed ? ' is-transparent' : ''}" data-action="detail" data-id="${item.id}" aria-label="Voir ${escapeHtml(item.nom)}">
          ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy">` : '<i class="ph ph-cpu" aria-hidden="true"></i>'}
        </button>
        <div class="cite-infos">
          <span class="cfg-cat">${escapeHtml(item.categorie)}${item.en_stock === false ? ' · épuisé' : ''}</span>
          <button type="button" class="cfg-nom" data-action="detail" data-id="${item.id}">${escapeHtml(item.nom)}</button>
          <span class="cite-specs">${escapeHtml(resumeSpecs(item))}</span>
        </div>
        <span class="cfg-prix">${prix(item.prix_indicatif)}</span>
        <span class="cfg-actions">
          ${boutonAjout(item, maConfig)}
          <button type="button" class="cfg-btn" data-action="detail" data-id="${item.id}"><i class="ph ph-info" aria-hidden="true"></i><span>Détails</span></button>
        </span>
      </li>`).join('')}</ul></div>`;
  }

  // Même fenêtre de détail que le configurateur et le comparateur, pour
  // rester dans la discussion.
  function showComponentDetail(id){
    const item = composantsParId.get(id);
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
              ${p.lien ? `<a href="${escapeHtml(withAffiliateTag(p.lien, p.vendeur))}" target="_blank" rel="noopener noreferrer sponsored" style="margin-left:8px; color:var(--led);">Voir l’offre ↗</a>` : ''}
            </span>
          </div>`).join('')
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
          ${amazonDetails.map(d => `<div class="detail-row"><span class="k">${escapeHtml(d.type)}</span><span class="v">${escapeHtml(d.value)}</span></div>`).join('')}
        </div>
      </details>` : '';

    const contenu = $('detail-modal-content');
    contenu.innerHTML = `
      <span class="cat-badge">${escapeHtml(item.categorie)}</span>
      <h2>${escapeHtml(item.nom)}</h2>
      ${imageHtml}
      <p class="detail-price-ref">Prix de référence : ${item.prix_indicatif}€</p>
      <div class="detail-ajout">${boutonAjout(item, lireMaConfig())}
        ${item.page ? `<a class="detail-page-link" href="${escapeHtml(item.page)}" target="_blank" rel="noopener">Fiche complète <i class="ph ph-arrow-square-out" aria-hidden="true"></i></a>` : ''}</div>
      <div class="follow-slot"></div>
      <div class="price-history-slot"></div>
      ${descriptionHtml}
      <div class="detail-specs">${specsHtml}</div>
      <h3 style="margin-top:18px; margin-bottom:8px;">Prix relevés</h3>
      <div class="detail-prices">${pricesHtml}</div>
      ${amazonDetailsHtml}`;
    contenu.dataset.id = item.id;
    $('detail-modal-overlay').classList.add('show');
    if(window.PCAccount) PCAccount.mountFollow(contenu.querySelector('.follow-slot'), item);
    if(window.PCPriceHistory) PCPriceHistory.mount(contenu.querySelector('.price-history-slot'), item.id);
  }

  function closeDetailModal(){
    $('detail-modal-overlay').classList.remove('show');
  }

  function blocFps(fps){
    if(!fps || !fps.estimation) return '';
    const conseil = fps.suggestion ? `<p>Remplacer ton ${escapeHtml(fps.suggestion.categorie)} par
      <strong>${escapeHtml(fps.suggestion.nom)}</strong>${fps.suggestion.prix_indicatif != null ? ` (${prix(fps.suggestion.prix_indicatif)})` : ''}
      réduirait ce goulot d'étranglement.</p>` : '';
    return `<div class="ai-verification">
      <span class="ai-verification-label"><i class="ph ph-game-controller" aria-hidden="true"></i> Estimation FPS</span>
      <p>${escapeHtml(fps.estimation).trim().replace(/\n/g, '<br>')}</p>${conseil}
    </div>`;
  }

  function accueil(){
    const maConfig = Object.keys(lireMaConfig()).length;
    return bulleAssistant(`<p>Salut ! Je peux te conseiller sur les composants, la compatibilité et les performances en jeu,
      ou te proposer une config complète selon ton budget.${maConfig ? ' Je vois aussi ta config en cours dans le configurateur : demande-moi ce que tu en penses.' : ''}</p>
      <div class="chat-exemples">${EXEMPLES.map((e, i) => `<button type="button" class="chat-exemple" data-action="exemple" data-i="${i}">${escapeHtml(e)}</button>`).join('')}</div>`);
  }

  function afficher(defiler = true){
    const fil = $('chat-fil');
    let html = accueil();
    discussion.forEach((m, i) => {
      if(m.role === 'user'){
        html += `<div class="msg msg-moi"><div class="msg-corps">${escapeHtml(m.content).replace(/\n/g, '<br>')}</div></div>`;
      }else{
        html += bulleAssistant(formater(m.content) + (m.suggestion ? carteConfig(m.suggestion, i) : '') + panneauComposants(m.composants) + blocFps(m.fps), m.erreur ? 'msg-erreur' : '');
      }
    });
    if(enCours) html += bulleAssistant('<span class="chat-ecrit" aria-label="L’assistant écrit"><i></i><i></i><i></i></span>');
    fil.innerHTML = html;
    $('chat-nouvelle').hidden = discussion.length === 0;
    if(defiler){
      const dernier = fil.lastElementChild;
      if(dernier) dernier.scrollIntoView({ behavior: 'smooth', block: discussion.length ? 'start' : 'nearest' });
    }
  }

  function sauvegarder(){
    try{ sessionStorage.setItem(DISCUSSION_KEY, JSON.stringify(discussion.filter(m => !m.erreur).slice(-40))); }catch(e){}
  }

  // ------------------------------------------------------------------
  // Envoi
  // ------------------------------------------------------------------
  function resumeConfig(s){
    return Object.entries(FIELD_TO_CATEGORY)
      .map(([champ, cat]) => composantsParId.get(s[champ]) ? `${cat} ${composantsParId.get(s[champ]).nom}` : null)
      .filter(Boolean).join(', ');
  }

  async function envoyer(texte){
    texte = (texte || '').trim();
    if(!texte || enCours) return;
    discussion = discussion.filter(m => !m.erreur);
    discussion.push({ role: 'user', content: texte });
    enCours = true;
    $('ai-input').value = '';
    ajusterHauteur();
    afficher();

    const derniere = [...discussion].reverse().find(m => m.suggestion);
    const messages = discussion.map(m => ({
      role: m.role,
      content: m.content
        + (m.suggestion ? `\n(Config proposée : ${resumeConfig(m.suggestion)})` : '')
        + ((m.composants || []).length ? `\n(Composants montrés : ${m.composants.map(id => composantsParId.get(id)).filter(Boolean).map(c => `${c.nom} [id ${c.id}]`).join(', ')})` : ''),
    }));

    let reponse;
    try{
      const res = await fetch(API_BASE + '/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, derniere_config: derniere ? derniere.suggestion : null, ma_config: lireMaConfig() }),
      });
      const data = await res.json().catch(() => ({}));
      if(res.ok && data.status === 'ok'){
        reponse = { role: 'assistant', content: data.message || '', suggestion: data.suggestion || null,
          composants: Array.isArray(data.composants) ? data.composants : [], fps: data.fps_estimation || null };
      }else{
        reponse = { role: 'assistant', content: data.message || data.detail || 'L’assistant n’a pas pu répondre, réessaie.', erreur: true };
      }
    }catch(e){
      reponse = { role: 'assistant', content: 'Connexion impossible avec l’assistant. Vérifie ta connexion et réessaie.', erreur: true };
    }
    enCours = false;
    if(reponse.erreur){
      // Le message non traité revient dans la zone de saisie pour être renvoyé.
      discussion.pop();
      $('ai-input').value = texte;
      ajusterHauteur();
    }
    discussion.push(reponse);
    sauvegarder();
    afficher();
    $('ai-input').focus();
  }

  // ------------------------------------------------------------------
  // Actions sur les cartes de config
  // ------------------------------------------------------------------
  function ajouter(suggestion, champs){
    const config = lireMaConfig();
    champs.forEach(champ => {
      const item = composantsParId.get(suggestion[champ]);
      if(item) config[FIELD_TO_CATEGORY[champ]] = item.id;
    });
    ecrireMaConfig(config);
    afficher(false);
  }

  function ajouterId(id){
    const item = composantsParId.get(id);
    if(!item) return;
    const config = lireMaConfig();
    config[item.categorie] = item.id;
    ecrireMaConfig(config);
    afficher(false);
    if($('detail-modal-overlay').classList.contains('show')) showComponentDetail(Number($('detail-modal-content').dataset.id));
  }

  $('detail-modal-content').addEventListener('click', e => {
    const b = e.target.closest('[data-action="ajouter-id"]');
    if(b) ajouterId(Number(b.dataset.id));
  });
  document.addEventListener('keydown', e => { if(e.key === 'Escape') closeDetailModal(); });

  $('chat-fil').addEventListener('click', e => {
    const b = e.target.closest('[data-action]');
    if(!b) return;
    const action = b.dataset.action;
    if(action === 'exemple'){ envoyer(EXEMPLES[Number(b.dataset.i)]); return; }
    if(action === 'detail'){ showComponentDetail(Number(b.dataset.id)); return; }
    if(action === 'ajouter-id'){ ajouterId(Number(b.dataset.id)); return; }
    const m = discussion[Number(b.dataset.msg)];
    if(!m || !m.suggestion) return;
    if(action === 'ajouter') ajouter(m.suggestion, [b.dataset.champ]);
    else if(action === 'tout') ajouter(m.suggestion, Object.keys(FIELD_TO_CATEGORY));
    else if(action === 'changer'){
      const item = composantsParId.get(m.suggestion[b.dataset.champ]);
      const cat = FIELD_TO_CATEGORY[b.dataset.champ];
      envoyer(item ? `Propose-moi un autre ${cat} à la place de ${item.nom} dans cette config.` : `Ajoute un ${cat} à cette config.`);
    }
  });

  // ------------------------------------------------------------------
  // Saisie
  // ------------------------------------------------------------------
  function ajusterHauteur(){
    const t = $('ai-input');
    t.style.height = 'auto';
    t.style.height = Math.min(t.scrollHeight, 180) + 'px';
  }

  $('chat-form').addEventListener('submit', e => { e.preventDefault(); envoyer($('ai-input').value); });
  $('ai-input').addEventListener('input', ajusterHauteur);
  $('ai-input').addEventListener('keydown', e => {
    // Entrée envoie, Maj+Entrée va à la ligne (sauf sur mobile : le clavier n'a pas Maj pratique).
    if(e.key === 'Enter' && !e.shiftKey && !e.isComposing && !matchMedia('(pointer: coarse)').matches){
      e.preventDefault();
      envoyer($('ai-input').value);
    }
  });
  $('chat-nouvelle').addEventListener('click', () => {
    if(enCours) return;
    discussion = [];
    sauvegarder();
    afficher();
    $('ai-input').focus();
  });

  // Mis à jour si la config change dans un autre onglet (configurateur ouvert à côté).
  window.addEventListener('storage', e => { if(e.key === DRAFT_STORAGE_KEY) afficher(false); });

  // ------------------------------------------------------------------
  // Démarrage
  // ------------------------------------------------------------------
  async function demarrer(){
    try{ discussion = JSON.parse(sessionStorage.getItem(DISCUSSION_KEY)) || []; }catch(e){ discussion = []; }
    afficher(false);
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      allComponents = Object.values(data.components || {}).flat();
      composantsParId = new Map(allComponents.map(c => [c.id, c]));
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
    afficher(discussion.length > 0);

    // Arrivée depuis le bouton « Débutant » de l'accueil.
    if(new URLSearchParams(location.search).get('prefill') === 'debutant' && !discussion.length){
      $('ai-input').value = 'Je débute, je ne connais rien aux composants PC. Aide-moi à choisir une config adaptée à mon usage.';
      ajusterHauteur();
      $('ai-input').focus();
    }
  }

  demarrer();
