(function(){
  // Apparition au scroll (IntersectionObserver, pas d'écouteur scroll)
  var els = document.querySelectorAll('.reveal, .flow');
  if('IntersectionObserver' in window){
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('is-in'); io.unobserve(e.target); } });
    }, { rootMargin:'0px 0px -8% 0px', threshold:0.12 });
    els.forEach(function(el){ io.observe(el); });
  } else {
    els.forEach(function(el){ el.classList.add('is-in'); });
  }

  // Configs du moment : calculées par le serveur (/api/configs-vedette) à
  // partir du catalogue en stock et des prix actuels.
  var configs = [];
  var current = 0;
  var tabsEl = document.getElementById('demo-tabs');
  var usageEl = document.getElementById('demo-usage');
  var listEl = document.getElementById('demo-list');
  var fpsEl = document.getElementById('demo-fps');
  var statusEl = document.getElementById('demo-status');
  var totalEl = document.getElementById('demo-total');
  var openBtn = document.getElementById('demo-open');

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fmt(n){ return Number(n).toLocaleString('fr-FR', { minimumFractionDigits:2, maximumFractionDigits:2 }) + ' €'; }
  function fmtRound(n){ return Math.round(Number(n)).toLocaleString('fr-FR') + ' €'; }

  function renderTabs(){
    tabsEl.innerHTML = configs.map(function(c, i){
      return '<button type="button" class="demo-tab" role="tab" id="demo-tab-' + i + '" aria-selected="' + (i === current) + '" data-index="' + i + '">' +
        '<span>' + esc(c.onglet || c.titre) + '</span><small>' + fmtRound(c.total) + '</small></button>';
    }).join('');
  }

  function render(){
    var c = configs[current];
    if(!c){ showError(); return; }
    renderTabs();
    usageEl.innerHTML = (c.guide ? '<a class="demo-guide-link" href="' + esc(c.guide) + '"><strong>' + esc(c.titre) + '</strong></a>' : '<strong>' + esc(c.titre) + '</strong>') + ' · ' + esc(c.usage) + ' · FPS estimés en qualité ' + esc(c.qualite);
    listEl.innerHTML = c.composants.map(function(p){
      var thumb = p.image_url
        ? '<span class="build-demo-thumb' + (p.image_processed ? '' : ' is-raw') + '"><img src="' + esc(p.image_url) + '?w=120" alt="" decoding="async"></span>'
        : '<span class="build-demo-thumb"></span>';
      return '<li class="build-demo-item">' + thumb +
        '<span class="build-demo-cat">' + esc(p.categorie) + '</span>' +
        '<span class="build-demo-name" title="' + esc(p.nom) + '">' + esc(p.nom) + '</span>' +
        '<span class="build-demo-price">' + fmt(p.prix) + '</span></li>';
    }).join('');
    fpsEl.innerHTML = (c.fps || []).map(function(f){
      return '<span class="demo-fps-chip">' + esc(f.jeu) + ' <b>' + esc(f.fps) + ' FPS</b></span>';
    }).join('');
    totalEl.textContent = fmt(c.total);
    if(c.compatible){
      statusEl.className = 'build-demo-status';
      statusEl.innerHTML = '<i class="ph ph-check-circle" aria-hidden="true"></i> Compatible';
    } else {
      statusEl.className = 'build-demo-status is-fail';
      statusEl.innerHTML = '<i class="ph ph-warning-circle" aria-hidden="true"></i> À vérifier';
    }
    openBtn.disabled = false;
  }

  function showError(){
    tabsEl.innerHTML = '';
    usageEl.textContent = '';
    fpsEl.innerHTML = '';
    listEl.innerHTML = '<li class="build-demo-item" style="grid-template-columns:1fr; color:var(--text-2); font-size:0.88rem; padding:28px 16px; text-align:center;">Les configurations n\'ont pas pu être chargées. Réessayez dans un instant.</li>';
    statusEl.className = 'build-demo-status is-pending';
    statusEl.textContent = '';
    openBtn.disabled = true;
  }

  tabsEl.addEventListener('click', function(e){
    var btn = e.target.closest('.demo-tab');
    if(!btn) return;
    current = Number(btn.getAttribute('data-index'));
    render();
    var again = document.getElementById('demo-tab-' + current);
    if(again) again.focus();
  });
  tabsEl.addEventListener('keydown', function(e){
    if(e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    current = (current + (e.key === 'ArrowRight' ? 1 : configs.length - 1)) % configs.length;
    render();
    document.getElementById('demo-tab-' + current).focus();
  });

  // Ouvre la config dans le configurateur, où elle reste modifiable
  // (même mécanisme que "Reprendre cette configuration" d'un lien partagé).
  openBtn.addEventListener('click', function(){
    var c = configs[current];
    if(!c) return;
    try{ sessionStorage.setItem('sharedBuild', JSON.stringify(c.composants_json)); }catch(e){}
    window.location.href = '/configurateur';
  });

  fetch('/api/configs-vedette').then(function(r){ return r.json(); }).then(function(data){
    configs = data.configs || [];
    if(data.nb_composants) document.getElementById('catalog-count').innerHTML = data.nb_composants.toLocaleString('fr-FR') + '<small>composants suivis</small>';
    // Le « bon compromis » par défaut : c'est le profil le plus demandé.
    current = Math.min(1, Math.max(0, configs.length - 1));
    if(configs.length) render(); else showError();
  }).catch(showError);
})();
