(function(){
  // Loupe de l'en-tête : recherche d'un composant et sa fiche sur place
  // (static/recherche-globale.js, chargé seulement au premier usage).
  function ouvrirRecherche(){
    if(window.PCRechercheGlobale){ window.PCRechercheGlobale.ouvrir(); return; }
    var s = document.createElement('script');
    s.src = '/static/recherche-globale.js';
    s.onload = function(){ if(window.PCRechercheGlobale) window.PCRechercheGlobale.ouvrir(); };
    document.head.appendChild(s);
  }

  document.addEventListener('keydown', function(e){
    if((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')){
      e.preventDefault();
      ouvrirRecherche();
    }
  });

  document.addEventListener('DOMContentLoaded', function(){
    var wrap = document.querySelector('header .nav-wrap');
    if(wrap && !wrap.querySelector('.nav-search')){
      var loupe = document.createElement('button');
      loupe.type = 'button';
      loupe.className = 'nav-search';
      loupe.setAttribute('aria-label', 'Rechercher un composant');
      loupe.title = 'Rechercher un composant (Ctrl+K)';
      loupe.innerHTML = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4.2-4.2"/></svg>';
      loupe.addEventListener('click', ouvrirRecherche);
      wrap.appendChild(loupe);   // placée à droite par CSS (order), avant le bouton du menu mobile
    }

    var toggle = document.getElementById('nav-toggle');
    var nav = document.querySelector('header nav');
    if(!toggle || !nav) return;

    toggle.addEventListener('click', function(){
      var isOpen = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

    nav.querySelectorAll('a').forEach(function(link){
      link.addEventListener('click', function(){
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });

    document.addEventListener('click', function(e){
      if(!nav.contains(e.target) && !toggle.contains(e.target)){
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });

    // Met en évidence le lien de la page actuellement affichée
    var currentPath = window.location.pathname.replace(/\/$/, '') || '/';
    nav.querySelectorAll('a[href^="/"]').forEach(function(link){
      var href = link.getAttribute('href').replace(/\/$/, '') || '/';
      if(href === currentPath){
        link.classList.add('active');
      }
    });
  });
})();
