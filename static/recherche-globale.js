/*
 * Loupe de l'en-tête (toutes les pages) : recherche d'un composant et sa fiche
 * directement dans une fenêtre (photo, prix, caractéristiques, courbe des
 * prix, offres), sans quitter la page. Chargé par nav-menu.js au premier
 * clic sur la loupe (ou Ctrl+K) ; charge lui-même ce qui lui manque
 * (recherche tolérante, libellés, courbe, affiliation) selon la page.
 */
(function () {
  'use strict';
  if (window.PCRechercheGlobale) return;

  var DRAFT_KEY = 'pc_configurator_draft';   // même brouillon que le configurateur
  var catalogue = null, chargement = null;
  var resultats = [], selection = 0;
  var overlay, champ, liste, fiche;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function euros(n) {
    return Number(n || 0).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }
  function script(src, present) {
    if (present()) return Promise.resolve();
    return new Promise(function (ok) {
      var s = document.createElement('script');
      s.src = src; s.onload = ok; s.onerror = ok;
      document.head.appendChild(s);
    });
  }

  function dependances() {
    return Promise.all([
      script('/static/recherche.js', function () { return window.pcrRecherche; }),
      script('/static/specs-libelles.js', function () { return window.PCSpecs; }),
      script('/static/price-history.js', function () { return window.PCPriceHistory; }),
      script('/static/affiliate-tag.js', function () { return typeof window.withAffiliateTag === 'function'; })
        .then(function () { if (typeof window.loadAffiliateConfig === 'function' && !window.__pcrAffiliationChargee) { window.__pcrAffiliationChargee = true; window.loadAffiliateConfig(); } }),
    ]);
  }

  function chargerCatalogue() {
    if (catalogue) return Promise.resolve(catalogue);
    if (!chargement) {
      chargement = fetch('/api/components').then(function (r) { return r.json(); }).then(function (d) {
        catalogue = [].concat.apply([], Object.keys(d.components || {}).map(function (k) { return d.components[k]; }));
        return catalogue;
      });
    }
    return chargement;
  }

  // ---------------------------------------------------------------- Fenêtre
  function construire() {
    overlay = document.createElement('div');
    overlay.className = 'gs-overlay';
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="gs-panneau" role="dialog" aria-modal="true" aria-label="Rechercher un composant">' +
        '<div class="gs-barre">' +
          '<i class="ph ph-magnifying-glass" aria-hidden="true"></i>' +
          '<input type="search" class="gs-champ" placeholder="Rechercher un composant (ex : rtx 5070, ryzen 7 9800x3d)" autocomplete="off" aria-label="Rechercher un composant">' +
          '<button type="button" class="gs-fermer" aria-label="Fermer">Échap</button>' +
        '</div>' +
        '<div class="gs-liste" role="listbox"></div>' +
        '<div class="gs-fiche" hidden></div>' +
      '</div>';
    document.body.appendChild(overlay);
    champ = overlay.querySelector('.gs-champ');
    liste = overlay.querySelector('.gs-liste');
    fiche = overlay.querySelector('.gs-fiche');

    overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) fermer(); });
    overlay.querySelector('.gs-fermer').addEventListener('click', fermer);
    champ.addEventListener('input', chercher);
    champ.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); surligner(selection + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); surligner(selection - 1); }
      else if (e.key === 'Enter' && resultats[selection]) { e.preventDefault(); ouvrirFiche(resultats[selection]); }
    });
    liste.addEventListener('click', function (e) {
      var ligne = e.target.closest('[data-i]');
      if (ligne) ouvrirFiche(resultats[+ligne.getAttribute('data-i')]);
    });
    fiche.addEventListener('click', function (e) {
      var b = e.target.closest('[data-action]');
      if (!b) return;
      if (b.getAttribute('data-action') === 'retour') retourListe();
      if (b.getAttribute('data-action') === 'ajouter') ajouterAConfig(+b.getAttribute('data-id'), b);
    });
  }

  function ouvrir() {
    if (!overlay) construire();
    overlay.hidden = false;
    document.documentElement.classList.add('gs-ouvert');
    retourListe();
    champ.focus();
    champ.select();
    if (!catalogue) liste.innerHTML = '<p class="gs-vide">Chargement du catalogue…</p>';
    Promise.all([dependances(), chargerCatalogue()]).then(chercher).catch(function () {
      liste.innerHTML = '<p class="gs-vide">Catalogue indisponible, réessaie dans un instant.</p>';
    });
  }

  function fermer() {
    if (!overlay) return;
    overlay.hidden = true;
    document.documentElement.classList.remove('gs-ouvert');
  }

  // ---------------------------------------------------------------- Liste
  function chercher() {
    if (!catalogue || !window.pcrRecherche) return;
    var q = champ.value.trim();
    if (!q) {
      resultats = [];
      liste.innerHTML = '<p class="gs-vide">Tape le nom d’un composant, une puce (« rtx 5070 »), un socket (« am5 »)…</p>';
      return;
    }
    // Un seul résultat par produit (ses variantes sont dans la fiche complète), en stock d'abord.
    var vus = {};
    resultats = window.pcrRecherche.filtrer(q, catalogue).filter(function (c) {
      var cle = c.groupe_id || c.id;
      if (vus[cle]) return false;
      vus[cle] = true;
      return true;
    }).slice(0, 12);
    selection = 0;
    if (!resultats.length) {
      liste.innerHTML = '<p class="gs-vide">Aucun composant trouvé pour « ' + esc(q) + ' ».</p>';
      return;
    }
    liste.innerHTML = resultats.map(function (c, i) {
      var resume = window.PCSpecs ? window.PCSpecs.resume(c, 3) : '';
      return '<button type="button" class="gs-ligne" role="option" data-i="' + i + '">' +
        '<span class="gs-image' + (c.image_processed ? ' is-transparent' : '') + '">' +
          (c.image_url ? '<img src="' + esc(c.image_url) + '?w=96" alt="" loading="lazy">' : '<i class="ph ph-cpu" aria-hidden="true"></i>') + '</span>' +
        '<span class="gs-texte"><span class="gs-nom">' + esc(c.nom) + '</span>' +
          '<span class="gs-detail">' + esc(c.categorie) + (resume ? ' · ' + esc(resume) : '') + (c.en_stock === false ? ' · épuisé' : '') + '</span></span>' +
        '<span class="gs-prix">' + (c.prix_indicatif ? euros(c.prix_indicatif) : '') + '</span>' +
      '</button>';
    }).join('');
    surligner(0);
  }

  function surligner(i) {
    var lignes = liste.querySelectorAll('.gs-ligne');
    if (!lignes.length) return;
    selection = (i + lignes.length) % lignes.length;
    lignes.forEach(function (l, k) { l.classList.toggle('is-actif', k === selection); l.setAttribute('aria-selected', k === selection); });
    lignes[selection].scrollIntoView({ block: 'nearest' });
  }

  function retourListe() {
    fiche.hidden = true;
    liste.hidden = false;
    overlay.querySelector('.gs-barre').hidden = false;
    if (champ) champ.focus();
  }

  // ---------------------------------------------------------------- Fiche
  function boutonAjout(c) {
    var config = {};
    try { config = JSON.parse(localStorage.getItem(DRAFT_KEY)) || {}; } catch (e) {}
    if (config[c.categorie] === c.id) return '<a class="btn btn-secondary" href="/configurateur"><i class="ph ph-check" aria-hidden="true"></i> Dans ma config · voir</a>';
    return '<button type="button" class="btn btn-primary" data-action="ajouter" data-id="' + c.id + '">' +
      (config[c.categorie] ? 'Remplacer dans ma config' : 'Mettre dans ma config') + '</button>';
  }

  function ouvrirFiche(c) {
    if (!c) return;
    var specs = c.specs || {};
    var lignesSpecs = Object.keys(specs).filter(function (k) { return specs[k] !== null && specs[k] !== '' && k !== 'couleur'; }).map(function (k) {
      return '<div class="gs-spec"><span>' + esc(window.PCSpecs ? window.PCSpecs.libelle(k) : k) + '</span><b>' +
        esc(window.PCSpecs ? window.PCSpecs.valeur(k, specs[k]) : specs[k]) + '</b></div>';
    }).join('');
    var offres = (c.prix_marche || []).slice().sort(function (a, b) { return a.prix - b.prix; }).map(function (p) {
      var lien = p.lien && typeof window.withAffiliateTag === 'function' ? window.withAffiliateTag(p.lien, p.vendeur) : p.lien;
      return '<div class="gs-offre"><span>' + esc(p.vendeur) + '</span><b>' + euros(p.prix) + '</b>' +
        (lien ? '<a href="' + esc(lien) + '" target="_blank" rel="noopener noreferrer sponsored">Voir l’offre ↗</a>' : '') + '</div>';
    }).join('');

    overlay.querySelector('.gs-barre').hidden = true;
    liste.hidden = true;
    fiche.hidden = false;
    fiche.innerHTML =
      '<button type="button" class="gs-retour" data-action="retour"><i class="ph ph-arrow-left" aria-hidden="true"></i> Résultats</button>' +
      '<div class="gs-entete">' +
        (c.image_url ? '<span class="gs-grande-image' + (c.image_processed ? ' is-transparent' : '') + '"><img src="' + esc(c.image_url) + '?w=320" alt="' + esc(c.nom) + '"></span>' : '') +
        '<div><span class="gs-cat">' + esc(c.categorie) + (c.en_stock === false ? ' · épuisé' : '') + '</span>' +
          '<h2 class="gs-titre">' + esc(c.nom) + '</h2>' +
          '<div class="gs-prix-grand">' + (c.prix_indicatif ? euros(c.prix_indicatif) : '—') + '<span>prix relevé chaque jour</span></div>' +
          '<div class="gs-actions">' + boutonAjout(c) +
            (c.page ? '<a class="btn btn-secondary" href="' + esc(c.page) + '">Fiche complète</a>' : '') + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="gs-courbe"></div>' +
      (lignesSpecs ? '<h3 class="gs-sous-titre">Caractéristiques</h3><div class="gs-specs">' + lignesSpecs + '</div>' : '') +
      (offres ? '<h3 class="gs-sous-titre">Prix chez les marchands</h3><div class="gs-offres">' + offres + '</div>' : '');
    if (window.PCPriceHistory) window.PCPriceHistory.mount(fiche.querySelector('.gs-courbe'), c.id);
    fiche.scrollTop = 0;
    var retour = fiche.querySelector('.gs-retour');
    if (retour) retour.focus();
  }

  function ajouterAConfig(id, bouton) {
    var c = (catalogue || []).find(function (x) { return x.id === id; });
    if (!c) return;
    var config = {};
    try { config = JSON.parse(localStorage.getItem(DRAFT_KEY)) || {}; } catch (e) {}
    config[c.categorie] = c.id;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(config)); } catch (e) {}
    bouton.outerHTML = '<a class="btn btn-secondary" href="/configurateur"><i class="ph ph-check" aria-hidden="true"></i> Ajouté · voir ma config</a>';
  }

  document.addEventListener('keydown', function (e) {
    if (overlay && !overlay.hidden && e.key === 'Escape') {
      e.preventDefault();
      if (!fiche.hidden) retourListe(); else fermer();
    }
  });

  window.PCRechercheGlobale = { ouvrir: ouvrir, fermer: fermer };
})();
