  // Page /application : explique comment installer PC Radar sur l'écran
  // d'accueil. Ouvre l'onglet du téléphone détecté, et propose un vrai
  // bouton « Installer » quand le navigateur le permet (Chrome, Edge, Samsung).

  let deferredInstallPrompt = null;

  function showInstallTab(name){
    ['android', 'iphone'].forEach(tab => {
      const selected = tab === name;
      document.getElementById('tab-' + tab).setAttribute('aria-selected', String(selected));
      document.getElementById('panel-' + tab).hidden = !selected;
    });
  }

  async function installApp(){
    if(!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    document.getElementById('install-direct').hidden = true;
    if(outcome === 'accepted') document.getElementById('install-done').hidden = false;
  }

  (function(){
    const ua = navigator.userAgent || '';
    const isApple = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    showInstallTab(isApple ? 'iphone' : 'android');

    const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    if(standalone) document.getElementById('install-done').hidden = false;

    window.addEventListener('beforeinstallprompt', e => {
      e.preventDefault();
      deferredInstallPrompt = e;
      document.getElementById('install-direct').hidden = false;
    });
    window.addEventListener('appinstalled', () => {
      document.getElementById('install-direct').hidden = true;
      document.getElementById('install-done').hidden = false;
    });
  })();
