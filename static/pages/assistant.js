  const API_BASE = window.location.origin;
  let allComponents = [];       // nécessaire pour afficher les noms/prix de la suggestion
  let lastAISuggestion = null;

  // Échappe une valeur pour l'insérer comme texte affiché — le nom d'un
  // composant peut venir d'une recherche IA, et le texte de vérification est
  // généré par l'IA à partir de résultats web réels : jamais fiables tels
  // quels dans du innerHTML.
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  const FIELD_TO_CATEGORY = {
    cpu_id: 'CPU',
    motherboard_id: 'Carte mère',
    ram_id: 'RAM',
    gpu_id: 'GPU',
    psu_id: 'Alimentation',
    storage_id: 'Stockage',
    case_id: 'Boîtier',
  };

  async function loadComponents(){
    try{
      const res = await fetch(API_BASE + '/api/components');
      const data = await res.json();
      allComponents = Object.values(data.components || {}).flat();
    }catch(e){
      console.error('Erreur chargement composants', e);
    }
  }

  // Si on arrive depuis le bouton "Débutant" de l'accueil, on pré-remplit
  // la question pour la personne.
  function checkPrefillParam(){
    const params = new URLSearchParams(window.location.search);
    if(params.get('prefill') === 'debutant'){
      const input = document.getElementById('ai-input');
      input.value = "Je débute, je ne connais rien aux composants PC, aidez-moi à choisir une config adaptée à mon usage.";
      input.focus();
    }
  }

  async function askAI(){
    const input = document.getElementById('ai-input');
    const responseBox = document.getElementById('ai-response');
    const text = input.value.trim();
    if(!text) return;

    responseBox.classList.remove('error');
    responseBox.classList.add('show');
    responseBox.innerHTML = 'L\'assistant réfléchit...';
    document.getElementById('chat-refine-row').classList.add('hidden');
    document.getElementById('ai-refine-input').value = '';

    try{
      const res = await fetch(API_BASE + '/suggest-config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_input: text})
      });
      const data = await res.json();

      if(data.status === 'ok' && data.suggestion){
        lastAISuggestion = data.suggestion;
        renderAISuggestion(data.suggestion, data.fps_estimation);
        document.getElementById('chat-refine-row').classList.remove('hidden');
      }else{
        lastAISuggestion = null;
        document.getElementById('chat-refine-row').classList.add('hidden');
        responseBox.classList.add('error');
        responseBox.textContent = data.message || data.detail || 'L\'assistant n\'a pas pu proposer de configuration.';
      }
    }catch(e){
      lastAISuggestion = null;
      document.getElementById('chat-refine-row').classList.add('hidden');
      responseBox.classList.add('error');
      responseBox.textContent = 'Erreur lors de la requête à l\'assistant IA.';
    }
  }

  // Fait évoluer la configuration déjà suggérée (conseil ou modification),
  // sans repartir de zéro — voir /api/refine-config. Les notes de conseil
  // s'accumulent au-dessus de la config courante, qui elle est mise à jour
  // en place à chaque modification acceptée.
  async function refineAI(){
    const input = document.getElementById('ai-refine-input');
    const text = input.value.trim();
    if(!text || !lastAISuggestion) return;

    const refineBtn = document.querySelector('#chat-refine-row button');
    input.disabled = true;
    refineBtn.disabled = true;
    refineBtn.textContent = 'L\'assistant réfléchit...';

    try{
      const res = await fetch(API_BASE + '/api/refine-config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({current_suggestion: lastAISuggestion, user_input: text})
      });
      const data = await res.json();

      if(data.status === 'ok' && data.suggestion){
        lastAISuggestion = data.suggestion;
        renderAISuggestion(data.suggestion, data.fps_estimation);
      }else if(data.status === 'advice'){
        addAdviceNote(data.message);
      }else{
        addAdviceNote(data.message || data.detail || 'L\'assistant n\'a pas pu traiter cette demande.', true);
      }
      input.value = '';
    }catch(e){
      addAdviceNote('Erreur lors de la requête à l\'assistant IA.', true);
    }finally{
      input.disabled = false;
      refineBtn.disabled = false;
      refineBtn.textContent = 'Demander';
      input.focus();
    }
  }

  function addAdviceNote(message, isError){
    const responseBox = document.getElementById('ai-response');
    const note = document.createElement('div');
    note.className = 'ai-advice-note' + (isError ? ' error' : '');
    note.textContent = message;
    responseBox.appendChild(note);
    note.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  function renderAISuggestion(suggestion, fpsEstimation){
    const responseBox = document.getElementById('ai-response');
    let total = 0;
    let rowsHtml = '';

    Object.entries(FIELD_TO_CATEGORY).forEach(([field, category]) => {
      const id = suggestion[field];
      const item = allComponents.find(c => c.id === id);
      // null id = aucun composant compatible trouvé dans cette catégorie
      // pour cette demande précise — à distinguer d'un vrai id cassé.
      const label = item ? item.nom : (id == null ? 'Pas encore disponible sur le site' : 'Composant introuvable');
      if(item) total += Number(item.prix_indicatif) || 0;
      rowsHtml += `<li><span class="cat">${escapeHtml(category)}</span><span class="val">${escapeHtml(label)}</span></li>`;
    });

    // Rempli uniquement quand la demande citait un ou plusieurs jeux — voir
    // le champ "jeux" extrait par l'IA dans /suggest-config.
    let fpsHtml = '';
    if(fpsEstimation && fpsEstimation.estimation){
      const suggestionHtml = fpsEstimation.suggestion ? `
        <p style="margin-top:8px;">
          Remplacer ton ${escapeHtml(fpsEstimation.suggestion.categorie)} par
          <strong>${escapeHtml(fpsEstimation.suggestion.nom)}</strong>
          ${fpsEstimation.suggestion.prix_indicatif != null ? `(${fpsEstimation.suggestion.prix_indicatif}€)` : ''}
          réduirait ce goulot d'étranglement.
        </p>
      ` : '';
      fpsHtml = `
        <div class="ai-verification">
          <span class="ai-verification-label"><i class="ph ph-game-controller" aria-hidden="true"></i> Estimation FPS</span>
          <p>${escapeHtml(fpsEstimation.estimation).trim().replace(/\n/g, '<br>')}</p>
          ${suggestionHtml}
        </div>
      `;
    }

    responseBox.innerHTML = `
      <ul class="suggestion-list">${rowsHtml}</ul>
      <div class="suggestion-total"><span>Total estimé</span><span>${total.toFixed(2)}€</span></div>
      ${fpsHtml}
      <button class="btn btn-primary use-config-btn" data-onclick="useAISuggestion()">Utiliser cette configuration</button>
    `;
  }

  // On dépose la suggestion en sessionStorage puis on redirige vers la page
  // du configurateur, qui l'appliquera automatiquement à son chargement.
  function useAISuggestion(){
    if(!lastAISuggestion) return;
    sessionStorage.setItem('aiSuggestion', JSON.stringify(lastAISuggestion));
    window.location.href = '/configurateur';
  }

  checkPrefillParam();
  loadComponents();
