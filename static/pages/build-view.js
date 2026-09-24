  const API_BASE = window.location.origin;
  let allComponents = [];
  let currentComposantsJson = null;

  // Échappe une valeur pour l'insérer comme texte affiché OU comme valeur
  // d'attribut HTML (href="...", src="...") — cette page est PUBLIQUE (pas
  // besoin de compte pour l'ouvrir), et composants_json est envoyé tel quel
  // par l'utilisateur qui a sauvegardé la build (aucune validation de forme
  // côté serveur) : jamais fiable tel quel dans du innerHTML.
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function getBuildIdFromPath(){
    const match = window.location.pathname.match(/\/build\/(\d+)/);
    return match ? match[1] : null;
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

  function renderBuildComponents(composantsJson){
    const entries = Object.entries(composantsJson || {});
    if(entries.length === 0) return '<p style="color:var(--text-dim);">Aucun composant enregistré.</p>';

    const rows = entries.map(([categorie, id]) => {
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
        <div class="build-detail-row">
          <div class="item-info">
            ${thumbHtml}
            <div>
              <span class="cat">${escapeHtml(categorie)}</span>
              <span class="nom">${escapeHtml(item.nom)}</span>
            </div>
          </div>
          ${buyBtn}
        </div>
      `;
    }).join('');

    return `<div class="build-card chip-card"><div class="build-detail show" style="border-top:none;">${rows}</div></div>`;
  }

  async function load(){
    const buildId = getBuildIdFromPath();
    if(!buildId){
      document.getElementById('build-name').textContent = 'Lien invalide';
      return;
    }

    await loadComponents();

    try{
      const res = await fetch(API_BASE + '/api/builds/' + buildId);
      if(res.status === 404){
        document.getElementById('build-name').textContent = 'Configuration introuvable';
        document.getElementById('build-date').textContent = "Ce lien ne correspond à aucune configuration (peut-être supprimée).";
        return;
      }
      const data = await res.json();

      document.getElementById('build-name').textContent = data.nom;
      document.getElementById('build-date').textContent = 'Partagée le ' + new Date(data.date).toLocaleDateString('fr-FR');
      document.getElementById('build-content').innerHTML = renderBuildComponents(data.composants_json);

      currentComposantsJson = data.composants_json;
      document.getElementById('reuse-btn').style.display = 'inline-block';
      document.getElementById('fps-picker-box').classList.remove('hidden');
    }catch(e){
      document.getElementById('build-name').textContent = 'Erreur de chargement';
    }
  }

  // Liste volontairement large (plusieurs dizaines) pour couvrir la plupart
  // des demandes — recherche tolérante par-dessus, comme dans le comparateur.
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
  const REQUIRED_BUILD_CATEGORIES = ["CPU", "GPU"];

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
      alert(`Maximum ${MAX_FPS_GAMES} jeux à la fois.`);
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
    if(!currentComposantsJson) return;

    if(selectedFpsGames.length === 0){
      fpsBox.innerHTML = `<div class="no-price">Choisis d'abord au moins un jeu dans la liste.</div>`;
      return;
    }

    const presentCategories = new Set(Object.keys(currentComposantsJson));
    const missing = REQUIRED_BUILD_CATEGORIES.filter(cat => !presentCategories.has(cat));
    if(missing.length > 0){
      fpsBox.innerHTML = `<div class="no-price">Cette configuration est incomplète pour estimer les FPS (il manque : ${missing.join(', ')}).</div>`;
      return;
    }

    fpsBox.innerHTML = `<div class="build-card chip-card" style="padding:16px;">Recherche en cours pour ${selectedFpsGames.join(', ')} (peut prendre quelques secondes)...</div>`;

    try{
      const res = await fetch(API_BASE + '/api/estimate-fps', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ composants_json: currentComposantsJson, jeux: selectedFpsGames, qualite: document.getElementById('fps-quality').value }),
      });
      const data = await res.json();
      if(data.status === 'ok'){
        fpsBox.innerHTML = PCFps.render(data);
      }else{
        fpsBox.innerHTML = `<div class="no-price">${data.message || data.detail || "Estimation indisponible."}</div>`;
      }
    }catch(e){
      fpsBox.innerHTML = `<div class="no-price">Erreur réseau lors de l'estimation.</div>`;
    }
  }

  // Dépose la config dans sessionStorage puis redirige vers le configurateur,
  // qui l'appliquera automatiquement à son chargement (même mécanisme que
  // pour les suggestions de l'assistant IA).
  function reuseBuild(){
    if(!currentComposantsJson) return;
    sessionStorage.setItem('sharedBuild', JSON.stringify(currentComposantsJson));
    window.location.href = '/configurateur';
  }

  loadAffiliateConfig();
  load();
