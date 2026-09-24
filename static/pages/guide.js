// Guides d'achat : « Personnaliser cette config » ouvre la config dans le
// configurateur (même mécanisme que le lien partagé d'une config).
(function(){
  document.querySelectorAll('.guide-cta[data-build]').forEach(function(btn){
    btn.addEventListener('click', function(){
      try{ sessionStorage.setItem('sharedBuild', btn.getAttribute('data-build')); }catch(e){}
      window.location.href = '/configurateur';
    });
  });
  if(window.PCPriceHistory){
    document.querySelectorAll('[data-price-history]').forEach(function(el){
      PCPriceHistory.mount(el, el.getAttribute('data-price-history'));
    });
  }
})();
