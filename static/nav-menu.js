(function(){
  document.addEventListener('DOMContentLoaded', function(){
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
