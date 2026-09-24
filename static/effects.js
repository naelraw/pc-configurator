// Effets visuels partagés par toutes les pages.
// Lueur qui suit la souris sur les cartes : position du curseur posée en
// variables CSS (--mx/--my) sur la carte survolée, le rendu est 100% CSS.
// Délégation sur document : couvre aussi les cartes créées plus tard en JS
// (composants du configurateur, favoris...). Souris uniquement, pas au toucher.
(function(){
  const SELECTOR = '.spotlight, .bento-cell, .component-btn, .profile-row, .fav-row, .vs-heading, .price-row, .build-card, .fps-build-row, .home-cta';
  let current = null;

  document.addEventListener('pointermove', (e) => {
    if(e.pointerType && e.pointerType !== 'mouse') return;
    const el = e.target.closest ? e.target.closest(SELECTOR) : null;
    if(current && current !== el) current.classList.remove('is-lit');
    current = el;
    if(!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    el.style.setProperty('--my', (e.clientY - r.top) + 'px');
    el.classList.add('is-lit');
  }, { passive: true });

  document.addEventListener('pointerleave', () => {
    if(current) current.classList.remove('is-lit');
    current = null;
  });
})();
