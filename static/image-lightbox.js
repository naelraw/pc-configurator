// Agrandit l'image produit au clic — uniquement dans la modale de détail et
// le comparateur (PAS sur les vignettes du catalogue/de la page de compte,
// où cliquer sert à sélectionner le composant, pas à voir l'image). Un seul
// script partagé, via délégation d'événement en phase de capture pour
// intercepter le clic AVANT le onclick du conteneur parent.
(function () {
  const THUMB_CONTAINERS = '.detail-image, .compare-heading-thumb';

  let overlay, imgEl, lastFocused;

  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.id = 'image-lightbox-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Image agrandie');
    overlay.innerHTML = `
      <button type="button" id="image-lightbox-close" aria-label="Fermer l'image agrandie">✕</button>
      <img id="image-lightbox-img" alt="">
    `;
    document.body.appendChild(overlay);
    imgEl = overlay.querySelector('#image-lightbox-img');

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
    overlay.querySelector('#image-lightbox-close').addEventListener('click', close);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && overlay.classList.contains('show')) close();
    });
  }

  function open(src, alt) {
    ensureOverlay();
    imgEl.src = src;
    imgEl.alt = alt || '';
    overlay.classList.add('show');
    lastFocused = document.activeElement;
    overlay.querySelector('#image-lightbox-close').focus();
  }

  function close() {
    if (!overlay) return;
    overlay.classList.remove('show');
    if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
  }

  document.addEventListener('click', (e) => {
    // closest() sur le CONTENEUR (pas sur l'<img> lui-même) : un clic
    // n'importe où dans le cadre — y compris la marge blanche autour d'une
    // photo produit détourée — ouvre l'agrandissement, pas seulement les
    // pixels exacts de l'image.
    const container = e.target.closest(THUMB_CONTAINERS);
    if (!container) return;
    const img = container.querySelector('img');
    if (!img || !img.src) return;
    e.preventDefault();
    e.stopPropagation();
    // Les vignettes demandent une version réduite (?w=...) : l'agrandissement
    // retire ce paramètre pour charger l'image pleine taille.
    const url = new URL(img.src, window.location.href);
    url.searchParams.delete('w');
    open(url.href, img.alt);
  }, true);
})();
