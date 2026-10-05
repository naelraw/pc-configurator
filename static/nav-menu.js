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

  // Une page ouverte depuis le menu (ou le logo) commence toujours tout en
  // haut, même si son script fait défiler la page pendant le chargement.
  var HAUT_KEY = 'pcr-ouvrir-en-haut';
  var ouvrirEnHaut = false;
  try{ ouvrirEnHaut = sessionStorage.getItem(HAUT_KEY) === '1'; sessionStorage.removeItem(HAUT_KEY); }catch(e){}
  if(ouvrirEnHaut){
    if('scrollRestoration' in history) history.scrollRestoration = 'manual';
    var remonter = function(){ window.scrollTo(0, 0); };
    document.addEventListener('DOMContentLoaded', remonter);
    window.addEventListener('load', function(){ remonter(); setTimeout(remonter, 400); });
  }

  document.addEventListener('click', function(e){
    var lien = e.target.closest && e.target.closest('header a[href^="/"]');
    if(!lien || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0 || lien.target === '_blank') return;
    var cible = lien.getAttribute('href').split('#')[0].replace(/\/$/, '') || '/';
    var ici = window.location.pathname.replace(/\/$/, '') || '/';
    if(cible === ici && !window.location.search){
      // Lien vers la page déjà ouverte : on remonte en haut sans recharger.
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    try{ sessionStorage.setItem(HAUT_KEY, '1'); }catch(err){}
  });

  document.addEventListener('DOMContentLoaded', function(){
    // Bulle d'aide en bas à droite (static/aide.js), sur toutes les pages du site.
    if(!document.querySelector('script[src="/static/aide.js"]')){
      var aide = document.createElement('script');
      aide.src = '/static/aide.js';
      aide.async = true;
      document.body.appendChild(aide);
    }

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
