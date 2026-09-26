  const API_BASE = window.location.origin;
  let allComponents = [];
  let selectedConfig = null; // { nom, composants_json }

  const REQUIRED_BUILD_CATEGORIES = ["CPU", "GPU"];

  async function loadComponents(){
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      allComponents = Object.values(data.components || {}).flat();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  // Les builds sont gardées ici et sélectionnées par index (jamais par nom
  // interpolé dans un attribut onclick) : un nom de config est saisi
  // librement par un utilisateur (prompt() lors de la sauvegarde), donc pas
  // fiable tel quel dans du HTML/JS généré par innerHTML.
  const buildListsBySource = {};

  function escapeHtml(str){
    const div = document.createElement('div');
    div.textContent = str ?? '';
    return div.innerHTML;
  }

  function renderBuildList(containerId, builds, emptyMessage){
    const container = document.getElementById(containerId);
    buildListsBySource[containerId] = builds || [];

    if(!builds || builds.length === 0){
      container.innerHTML = `<p class="no-price">${emptyMessage}</p>`;
      return;
    }
    container.innerHTML = builds.map((b, i) => `
      <div class="fps-build-row" data-onclick="selectConfigByIndex('${containerId}', ${i})">
        <span class="nom">${escapeHtml(b.nom)}</span>
        <span class="date">${new Date(b.date).toLocaleDateString('fr-FR')}</span>
      </div>
    `).join('');
  }

  function selectConfigByIndex(containerId, index){
    const build = buildListsBySource[containerId]?.[index];
    if(!build) return;
    selectConfigFromData(build.nom, build.composants_json);
  }

  async function loadMyBuilds(){
    try{
      const meRes = await fetch(API_BASE + '/api/auth/me', { credentials: 'include' });
      const me = await meRes.json();
      if(!me.logged_in){
        document.getElementById('my-builds-list').innerHTML =
          '<p class="no-price">Connecte-toi pour voir tes configurations sauvegardées.</p>';
        return;
      }
      const res = await fetch(API_BASE + '/api/builds', { credentials: 'include' });
      const data = await res.json();
      renderBuildList('my-builds-list', data.builds, 'Aucune configuration sauvegardée pour l\'instant.');
    }catch(e){
      document.getElementById('my-builds-list').innerHTML = '<p class="no-price">Erreur de chargement.</p>';
    }
  }

  async function loadRecommendedBuilds(){
    try{
      const res = await fetch(API_BASE + '/api/builds/recommandees');
      const data = await res.json();
      renderBuildList('recommended-builds-list', data.builds, 'Aucune configuration recommandée pour l\'instant.');
    }catch(e){
      document.getElementById('recommended-builds-list').innerHTML = '<p class="no-price">Erreur de chargement.</p>';
    }
  }

  function selectConfigFromData(nom, composants_json){
    selectedConfig = { nom, composants_json };

    document.getElementById('selected-config-box').classList.remove('hidden');
    document.getElementById('selected-config-name').textContent = nom;

    const entries = Object.entries(composants_json);
    document.getElementById('selected-config-detail').innerHTML = entries.map(([cat, id]) => {
      const item = allComponents.find(c => c.id === id);
      return `<div class="build-detail-row"><span class="cat">${escapeHtml(cat)}</span><span class="nom">${escapeHtml(item ? item.nom : 'Composant introuvable')}</span></div>`;
    }).join('');

    document.getElementById('fps-result').innerHTML = '';
    document.getElementById('selected-config-box').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // --- Sélecteur de jeu (identique au configurateur / à la page de partage) ---

  const POPULAR_GAMES = [
    "Fortnite", "Valorant", "Counter-Strike 2", "League of Legends", "Apex Legends",
    "Call of Duty: Warzone", "Call of Duty: Modern Warfare III", "Call of Duty: Black Ops 6",
    "Overwatch 2", "Rainbow Six Siege", "PUBG: Battlegrounds", "Minecraft",
    "Grand Theft Auto V", "Grand Theft Auto VI", "Cyberpunk 2077", "Red Dead Redemption 2",
    "The Witcher 3", "Elden Ring", "Baldur's Gate 3", "Starfield", "Diablo IV",
    "Rocket League", "Dota 2", "World of Warcraft", "Destiny 2", "Escape from Tarkov",
    "Hogwarts Legacy", "Assassin's Creed Mirage", "Assassin's Creed Valhalla",
    "Assassin's Creed Shadows", "Forza Horizon 5", "F1 24", "EA Sports FC 25",
    "NBA 2K25", "Resident Evil 4", "Resident Evil Village", "Street Fighter 6",
    "Tekken 8", "Black Myth: Wukong", "Helldivers 2", "Palworld", "Sea of Thieves",
    "Fallout 4", "Fallout 76", "The Elder Scrolls V: Skyrim", "Terraria",
    "Stardew Valley", "Among Us", "Fall Guys", "Genshin Impact", "Warframe",
    "Path of Exile 2", "Final Fantasy XIV", "Monster Hunter Wilds",
    "Dead by Daylight", "Left 4 Dead 2", "Team Fortress 2", "Battlefield 2042",
    "Halo Infinite", "Doom Eternal", "Far Cry 6", "It Takes Two",
    "Cities: Skylines II", "Total War: Warhammer III", "Marvel Rivals",
    "Silent Hill 2", "Dragon's Dogma 2", "Star Wars Jedi: Survivor",
    "God of War Ragnarök", "Horizon Forbidden West",
    "Alan Wake 2", "Avowed", "Dragon Age: The Veilguard", "Ghost of Tsushima", "Kingdom Come: Deliverance II", "Marvel's Spider-Man 2",
    "Stalker 2", "Star Wars Outlaws", "The Last of Us Part I", "Battlefield 6", "Doom: The Dark Ages", "Clair Obscur: Expedition 33",
    "Hunt: Showdown 1896", "Naraka: Bladepoint", "War Thunder", "Rust", "ARK: Survival Ascended", "Delta Force", "Forza Horizon 6", "The Elder Scrolls IV: Oblivion Remastered",
  ];

  const MAX_FPS_GAMES = 5;
  let selectedFpsGames = [];

  function renderFpsGameResults(matches){
    const resultsBox = document.getElementById('fps-game-results');
    if(matches.length === 0){
      resultsBox.innerHTML = '<div class="search-result-item">Aucun jeu trouvé</div>';
      resultsBox.classList.add('show');
      return;
    }
    resultsBox.innerHTML = matches.map(g => `
      <div class="search-result-item" data-onclick="selectFpsGame('${g.replace(/'/g, "\\'")}')">${g}</div>
    `).join('');
    resultsBox.classList.add('show');
  }

  function handleFpsGameSearch(){
    const query = document.getElementById('fps-game-search').value.trim();
    const resultsBox = document.getElementById('fps-game-results');
    if(!query){
      resultsBox.classList.remove('show');
      resultsBox.innerHTML = '';
      return;
    }
    const normalizedQuery = query.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const matches = POPULAR_GAMES
      .filter(g => !selectedFpsGames.includes(g))
      .filter(g => g.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').includes(normalizedQuery))
      .slice(0, 10);
    renderFpsGameResults(matches);
  }

  function renderSelectedFpsGames(){
    const selectedBox = document.getElementById('fps-selected-game');
    if(selectedFpsGames.length === 0){
      selectedBox.classList.add('hidden');
      selectedBox.innerHTML = '';
      return;
    }
    selectedBox.classList.remove('hidden');
    selectedBox.innerHTML = selectedFpsGames.map(name => `
      <span class="fps-game-chip"><i class="ph ph-game-controller" aria-hidden="true"></i> ${name} <button type="button" data-onclick="removeFpsGame('${name.replace(/'/g, "\\'")}')">✕</button></span>
    `).join('');
  }

  function selectFpsGame(name){
    if(selectedFpsGames.includes(name)) return;
    if(selectedFpsGames.length >= MAX_FPS_GAMES){
      uiAlert(`Retire un jeu pour en ajouter un autre.`, { title: `${MAX_FPS_GAMES} jeux maximum` });
      return;
    }
    selectedFpsGames.push(name);
    document.getElementById('fps-game-search').value = '';
    document.getElementById('fps-game-results').classList.remove('show');
    renderSelectedFpsGames();
    document.getElementById('fps-estimate-btn').disabled = false;
  }

  function removeFpsGame(name){
    selectedFpsGames = selectedFpsGames.filter(g => g !== name);
    renderSelectedFpsGames();
    document.getElementById('fps-estimate-btn').disabled = selectedFpsGames.length === 0;
  }

  document.getElementById('fps-game-search').addEventListener('input', handleFpsGameSearch);
  document.addEventListener('click', (e) => {
    if(!e.target.closest('#fps-search-box')){
      document.getElementById('fps-game-results').classList.remove('show');
    }
  });

  async function estimateFps(){
    const fpsBox = document.getElementById('fps-result');
    if(!selectedConfig) return;

    if(selectedFpsGames.length === 0){
      fpsBox.innerHTML = `<div class="compat-result compat-fail">Choisis d'abord au moins un jeu dans la liste.</div>`;
      return;
    }

    const presentCategories = new Set(Object.keys(selectedConfig.composants_json));
    const missing = REQUIRED_BUILD_CATEGORIES.filter(cat => !presentCategories.has(cat));
    if(missing.length > 0){
      fpsBox.innerHTML = `<div class="compat-result compat-fail">Cette configuration est incomplète pour estimer les FPS (il manque : ${missing.join(', ')}).</div>`;
      return;
    }

    fpsBox.innerHTML = `<div class="compat-result">Recherche en cours pour ${selectedFpsGames.join(', ')} (peut prendre quelques secondes)...</div>`;

    try{
      const res = await fetch(API_BASE + '/api/estimate-fps', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ composants_json: selectedConfig.composants_json, jeux: selectedFpsGames, qualite: document.getElementById('fps-quality').value }),
      });
      const data = await res.json();
      if(data.status === 'ok'){
        const suggestionHtml = data.suggestion ? `
          <div class="ai-verification" style="margin-top:12px;">
            <span class="ai-verification-label"><i class="ph ph-lightbulb" aria-hidden="true"></i> Composant plus adapté</span>
            <p>
              Remplacer ton ${escapeHtml(data.suggestion.categorie)} actuel par
              <strong>${escapeHtml(data.suggestion.nom)}</strong>
              ${data.suggestion.prix_indicatif != null ? `(${data.suggestion.prix_indicatif}€)` : ''}
              devrait réduire ce goulot d'étranglement.
            </p>
            <button class="btn btn-secondary" data-onclick="applySuggestedComponent(${data.suggestion.component_id}, '${escapeHtml(data.suggestion.categorie)}')">
              Remplacer dans ma configuration
            </button>
          </div>
        ` : '';
        fpsBox.innerHTML = PCFps.render(data) + suggestionHtml;
      }else{
        fpsBox.innerHTML = `<div class="compat-result compat-fail">${data.message || data.detail || "Estimation indisponible."}</div>`;
      }
    }catch(e){
      fpsBox.innerHTML = `<div class="compat-result compat-fail">Erreur réseau lors de l'estimation.</div>`;
    }
  }

  // Dépose le remplacement dans sessionStorage puis renvoie au configurateur,
  // qui l'applique par-dessus la configuration existante (garde tous les
  // autres composants déjà choisis, ne touche qu'à la catégorie concernée).
  function applySuggestedComponent(componentId, categorie){
    try{
      sessionStorage.setItem('componentSwap', JSON.stringify({ categorie, id: componentId }));
    }catch(e){}
    window.location.href = '/configurateur';
  }

  // Si on arrive depuis "Mon compte" (bouton "Estimer FPS" sur une
  // configuration sauvegardée), la config a été déposée dans sessionStorage
  // avant la navigation — on la pré-sélectionne directement plutôt que de
  // forcer à la rechercher dans "Mes configurations" sur cette page.
  function applyIncomingFpsBuild(){
    let raw;
    try{ raw = sessionStorage.getItem('fpsBuild'); }catch(e){ raw = null; }
    if(!raw) return;
    sessionStorage.removeItem('fpsBuild');
    let build;
    try{ build = JSON.parse(raw); }catch(e){ return; }
    if(!build?.composants_json) return;
    selectConfigFromData(build.nom, build.composants_json);
  }

  (async function init(){
    await loadComponents();
    await Promise.all([loadMyBuilds(), loadRecommendedBuilds()]);
    applyIncomingFpsBuild();
  })();
