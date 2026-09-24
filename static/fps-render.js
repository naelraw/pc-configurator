// Affichage de l'estimation FPS (page Estimer FPS et build partagé) :
// un tableau jeu x résolution, avec ce qui limite les FPS dans chaque cas.
(function(){
  const LIMIT_LABELS = {
    'GPU': 'carte graphique',
    'CPU': 'processeur',
    'jeu': 'plafond du jeu',
    'équilibré': 'équilibré',
  };
  const RESOLUTIONS = [['1080p', '1080p'], ['1440p', '1440p'], ['4k', '4K']];

  function esc(str){
    return String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function tier(fps){
    if(fps >= 60) return 'good';
    if(fps >= 30) return 'ok';
    return 'low';
  }

  // Origine des chiffres : mesure publiée pour cette carte, déduction depuis
  // les cartes testées dans ce même jeu, ou estimation sans test publié.
  const SOURCES = {
    'mesuré': ['mesuré', '', 'Cette carte a été testée dans ce jeu'],
    'déduit': ['déduit du test', ' is-derived', 'Déduit des cartes de puissance proche testées dans ce jeu'],
    'estimé': ['estimé', ' is-estimate', 'Pas de test publié pour ce jeu : estimé par recoupement sur du matériel équivalent'],
  };
  function sourceTag(r){
    const [label, cls, title] = SOURCES[r.source] || SOURCES['estimé'];
    const detail = r.test ? `${title} (test ${r.test.editeur}, réglages ${r.test.reglages}).` : title;
    return r.test && r.test.url
      ? `<a class="fps-source${cls}" href="${esc(r.test.url)}" target="_blank" rel="noopener" title="${esc(detail)}">${label}</a>`
      : `<span class="fps-source${cls}" title="${esc(detail)}">${label}</span>`;
  }

  function render(data){
    // Réponse d'une ancienne version du serveur : texte brut.
    if(!Array.isArray(data.resultats)){
      return `<div class="ai-verification"><p>${esc(data.estimation).replace(/\n/g, '<br>')}</p></div>`;
    }
    const qualite = data.qualite ? data.qualite.label : 'Ultra';
    const rows = data.resultats.map(r => {
      if(!r.couvert){
        return `<tr class="fps-row is-missing"><th scope="row">${esc(r.jeu)}</th><td colspan="3">Non estimé : ${esc(r.raison)}</td></tr>`;
      }
      const cells = RESOLUTIONS.map(([key]) => {
        const cell = r.resolutions[key];
        return `<td><span class="fps-value fps-${tier(cell.fps)}">${cell.fps}</span><span class="fps-limit">${esc(LIMIT_LABELS[cell.limite] || cell.limite)}</span></td>`;
      }).join('');
      const tag = sourceTag(r);
      return `<tr class="fps-row"><th scope="row">${esc(r.jeu)} ${tag}</th>${cells}</tr>`;
    }).join('');

    return `
      <div class="fps-table-wrap">
        <table class="fps-table">
          <thead><tr><th scope="col">Jeu</th>${RESOLUTIONS.map(([, label]) => `<th scope="col">${label}</th>`).join('')}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="fps-note">FPS moyens en réglages <strong>${esc(qualite)}</strong>, résolution native, sans DLSS/FSR ni génération d'images, d'après les tests publiés par TechPowerUp et TechSpot. Les creux ponctuels sont plus bas que la moyenne. Sous chaque chiffre : ce qui limite les FPS. « Mesuré » : ta carte a été testée dans ce jeu ; « déduit du test » : calculé à partir des cartes de puissance proche testées dans ce jeu ; « estimé » : pas de test publié pour ce jeu.</p>`;
  }

  window.PCFps = { render };
})();
