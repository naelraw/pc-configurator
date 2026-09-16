// Effet de révélation du quadrillage au passage de la souris : la couche
// .grid-bg-glow est masquée par un cercle qui suit le curseur (variables
// CSS --mx/--my), donc pas de calcul lourd, juste 2 variables mises à jour.
(function(){
  const root = document.documentElement;
  window.addEventListener('mousemove', (e) => {
    root.style.setProperty('--mx', e.clientX + 'px');
    root.style.setProperty('--my', e.clientY + 'px');
  }, { passive: true });

  // Sur mobile / tactile (pas de curseur) : centre le cercle sur la position
  // de la dernière interaction tactile pour un léger effet au toucher.
  window.addEventListener('touchmove', (e) => {
    if(e.touches && e.touches[0]){
      root.style.setProperty('--mx', e.touches[0].clientX + 'px');
      root.style.setProperty('--my', e.touches[0].clientY + 'px');
    }
  }, { passive: true });
})();
