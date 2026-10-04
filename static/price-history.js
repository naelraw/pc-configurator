/*
 * Historique du prix d'un composant :
 *   PCPriceHistory.mount(emplacement, idDuComposant)                      fenêtres « Détail » (compact)
 *   PCPriceHistory.mount(emplacement, idDuComposant, { complet: true })   fiche complète du produit
 * Courbe SVG (un relevé par jour au plus, voir /api/components/{id}/prix-historique).
 * Interactive : survol à la souris, doigt qui glisse, flèches du clavier.
 * Version complète : choix de la période, axes (prix et dates), points de
 * relevé, ligne du plus bas historique, statistiques de la période.
 */
(function () {
  'use strict';

  var JOUR = 24 * 3600 * 1000;
  var PERIODES = [[7, '7 jours'], [30, '1 mois'], [90, '3 mois'], [365, '1 an']];

  function euros(n) {
    return Number(n).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }
  function eurosCourt(n) {
    return Math.round(n).toLocaleString('fr-FR') + ' €';
  }
  function dateFr(iso) {
    var p = iso.split('-');
    return p[2] + '/' + p[1];
  }
  function dateLongue(iso) {
    var p = iso.split('-');
    return new Date(+p[0], +p[1] - 1, +p[2]).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
  }
  function temps(iso) {
    var p = iso.split('-');
    return Date.UTC(+p[0], +p[1] - 1, +p[2]);
  }
  function aujourdhui() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  // Positions des relevés dans un repère W × H : x selon la vraie date (un
  // jour sans relevé laisse un écart), y selon le prix.
  function positions(points, min, max, g) {
    var span = max - min || 1;
    var t0 = temps(points[0].date), t1 = temps(points[points.length - 1].date);
    var duree = Math.max(t1 - t0, JOUR);
    return points.map(function (p) {
      var x = points.length === 1 ? g.W / 2 : g.gauche + ((temps(p.date) - t0) / duree) * (g.W - g.gauche - g.droite);
      var y = g.haut + (1 - (p.prix - min) / span) * (g.H - g.haut - g.bas);
      return [x, y];
    });
  }

  function trace(xy, g) {
    var line = xy.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var last = xy[xy.length - 1];
    var area = line + ' L' + last[0].toFixed(1) + ' ' + (g.H - g.bas) + ' L' + xy[0][0].toFixed(1) + ' ' + (g.H - g.bas) + ' Z';
    return '<path class="ph-area" d="' + area + '"/><path class="ph-line" d="' + line + '" vector-effect="non-scaling-stroke"/>';
  }

  function lecture(pts, i) {
    var dernier = pts.length - 1;
    var precedent = i > 0 ? pts[i - 1].prix : null;
    var ecart = precedent !== null && pts[i].prix !== precedent
      ? ' <span class="ph-ecart ' + (pts[i].prix < precedent ? 'is-baisse' : 'is-hausse') + '">' +
        (pts[i].prix < precedent ? '−' : '+') + euros(Math.abs(pts[i].prix - precedent)) + '</span>'
      : '';
    // « Aujourd'hui » seulement si le dernier relevé date vraiment d'aujourd'hui.
    var jour = i === dernier
      ? (pts[i].date === aujourdhui() ? "Aujourd'hui" : 'Dernier relevé · ' + dateLongue(pts[i].date))
      : dateLongue(pts[i].date);
    return '<span class="ph-jour">' + jour + '</span><b>' + euros(pts[i].prix) + '</b>' + ecart;
  }

  // Survol, doigt et clavier sur la zone de la courbe.
  function interactif(conteneur, pts, xy, W, H) {
    var plot = conteneur.querySelector('.ph-plot');
    var guide = conteneur.querySelector('.ph-guide');
    var point = conteneur.querySelector('.ph-point');
    var zone = conteneur.querySelector('.ph-lecture');
    var dernier = pts.length - 1;
    var actuel = dernier;

    function montrer(i, survol) {
      actuel = i;
      var gauche = (xy[i][0] / W * 100) + '%';
      guide.style.left = gauche;
      point.style.left = gauche;
      point.style.top = (xy[i][1] / H * 100) + '%';
      plot.classList.toggle('is-survol', !!survol);
      zone.innerHTML = lecture(pts, i);
      plot.setAttribute('aria-valuenow', i);
      plot.setAttribute('aria-valuetext', dateLongue(pts[i].date) + ' : ' + euros(pts[i].prix));
    }
    function plusProche(clientX) {
      var r = plot.getBoundingClientRect();
      var x = (clientX - r.left) / r.width * W;
      var meilleur = 0;
      for (var i = 1; i < xy.length; i++) if (Math.abs(xy[i][0] - x) < Math.abs(xy[meilleur][0] - x)) meilleur = i;
      return meilleur;
    }
    plot.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' && plot.setPointerCapture) plot.setPointerCapture(e.pointerId);
      montrer(plusProche(e.clientX), true);
    });
    plot.addEventListener('pointermove', function (e) { montrer(plusProche(e.clientX), true); });
    plot.addEventListener('pointerleave', function () { montrer(dernier, false); });
    plot.addEventListener('pointerup', function (e) { if (e.pointerType !== 'mouse') montrer(dernier, false); });
    plot.addEventListener('keydown', function (e) {
      var i = actuel;
      if (e.key === 'ArrowLeft') i = Math.max(0, actuel - 1);
      else if (e.key === 'ArrowRight') i = Math.min(dernier, actuel + 1);
      else if (e.key === 'Home') i = 0;
      else if (e.key === 'End') i = dernier;
      else return;
      e.preventDefault();
      montrer(i, i !== dernier);
    });
    plot.addEventListener('blur', function () { montrer(dernier, false); });
    montrer(dernier, false);
  }

  function zonePlot(svg, nb) {
    return '<div class="ph-plot" tabindex="0" role="slider" aria-label="Prix jour par jour : flèches gauche et droite pour changer de jour"' +
      ' aria-valuemin="0" aria-valuemax="' + (nb - 1) + '">' + svg +
      '<span class="ph-guide" aria-hidden="true"></span><span class="ph-point" aria-hidden="true"></span></div>';
  }

  function videHtml(pts) {
    return '<div class="price-history"><div class="ph-head"><span class="ph-title">Évolution du prix</span></div>' +
      '<p class="ph-empty">Le prix est relevé régulièrement : la courbe apparaîtra dès le deuxième relevé' +
      (pts.length ? ' (premier relevé le ' + dateFr(pts[0].date) + ').' : '.') + '</p></div>';
  }

  // ---------------------------------------------------------------- Compact
  function renderCompact(slot, data) {
    var pts = data.points || [];
    if (pts.length < 2) { slot.innerHTML = videHtml(pts); return; }
    var g = { W: 320, H: 84, haut: 8, bas: 8, gauche: 5, droite: 5 };
    var xy = positions(pts, data.min, data.max, g);
    var trend = pts[pts.length - 1].prix <= data.min ? ' <span class="ph-badge">Au plus bas</span>' : '';
    slot.innerHTML =
      '<div class="price-history">' +
        '<div class="ph-head"><span class="ph-title">Évolution du prix' + trend + '</span>' +
        '<span class="ph-range">' + dateFr(pts[0].date) + ' → ' + dateFr(pts[pts.length - 1].date) + '</span></div>' +
        '<div class="ph-lecture" aria-live="polite"></div>' +
        zonePlot('<svg class="ph-chart" viewBox="0 0 ' + g.W + ' ' + g.H + '" preserveAspectRatio="none" aria-hidden="true">' + trace(xy, g) + '</svg>', pts.length) +
        '<div class="ph-stats"><span>Plus bas <b>' + euros(data.min) + '</b></span><span>Plus haut <b>' + euros(data.max) + '</b></span></div>' +
      '</div>';
    interactif(slot, pts, xy, g.W, g.H);
  }

  // ---------------------------------------------------------------- Complet
  function renderComplet(slot, data) {
    var tous = data.points || [];
    if (tous.length < 2) { slot.innerHTML = videHtml(tous); return; }
    var etat = { jours: 90, plusBas: true };
    var duree = (temps(tous[tous.length - 1].date) - temps(tous[0].date)) / JOUR;
    if (duree <= 30) etat.jours = 30;

    function dessiner() {
      var limite = temps(aujourdhui()) - etat.jours * JOUR;
      var pts = tous.filter(function (p) { return temps(p.date) >= limite; });
      if (pts.length < 2) pts = tous.slice(-2);       // toujours au moins deux relevés à relier
      var prix = pts.map(function (p) { return p.prix; });
      var min = Math.min.apply(null, prix), max = Math.max.apply(null, prix);
      var histo = data.plus_bas_historique;
      var basAffiche = etat.plusBas && histo && histo < min ? histo : min;   // la ligne du plus bas reste visible
      var marge = (max - basAffiche) * 0.08 || max * 0.02;
      var g = { W: 640, H: 220, haut: 10, bas: 10, gauche: 6, droite: 6 };
      var echMin = basAffiche - marge, echMax = max + marge;
      var xy = positions(pts, echMin, echMax, g);
      var yPrix = function (p) { return g.haut + (1 - (p - echMin) / (echMax - echMin)) * (g.H - g.haut - g.bas); };

      // Axe des prix : 3 repères (haut, milieu, bas).
      var reperes = [echMax - marge, (echMax + echMin) / 2, echMin + marge];
      var grille = reperes.map(function (p) {
        return '<line class="ph-grille" x1="0" x2="' + g.W + '" y1="' + yPrix(p).toFixed(1) + '" y2="' + yPrix(p).toFixed(1) + '" vector-effect="non-scaling-stroke"/>';
      }).join('');
      var etiquettesY = reperes.map(function (p) {
        return '<span style="top:' + (yPrix(p) / g.H * 100) + '%">' + eurosCourt(p) + '</span>';
      }).join('');
      var ligneBas = etat.plusBas && histo
        ? '<line class="ph-plus-bas" x1="0" x2="' + g.W + '" y1="' + yPrix(histo).toFixed(1) + '" y2="' + yPrix(histo).toFixed(1) + '" vector-effect="non-scaling-stroke"/>'
        : '';
      var points = xy.map(function (p) {
        return '<span class="ph-releve" style="left:' + (p[0] / g.W * 100) + '%;top:' + (p[1] / g.H * 100) + '%"></span>';
      }).join('');
      var milieu = pts[Math.floor((pts.length - 1) / 2)];
      var etiquettesX = '<span>' + dateFr(pts[0].date) + '</span>' + (pts.length > 2 ? '<span>' + dateFr(milieu.date) + '</span>' : '') +
        '<span>' + dateFr(pts[pts.length - 1].date) + '</span>';

      var moyenne = prix.reduce(function (a, b) { return a + b; }, 0) / prix.length;
      var variation = pts[pts.length - 1].prix - pts[0].prix;
      var pct = variation / pts[0].prix * 100;
      var classeVar = variation < 0 ? 'is-baisse' : variation > 0 ? 'is-hausse' : '';

      slot.innerHTML =
        '<div class="price-history is-complet">' +
          '<div class="ph-head"><span class="ph-title">Évolution du prix' +
            (pts[pts.length - 1].prix <= (histo || min) ? ' <span class="ph-badge">Au plus bas</span>' : '') + '</span>' +
            '<div class="ph-periodes" role="group" aria-label="Période">' +
              PERIODES.map(function (p) {
                return '<button type="button" data-jours="' + p[0] + '" aria-pressed="' + (p[0] === etat.jours) + '"' +
                  (p[0] === etat.jours ? ' class="is-actif"' : '') + '>' + p[1] + '</button>';
              }).join('') +
            '</div></div>' +
          '<div class="ph-lecture" aria-live="polite"></div>' +
          '<div class="ph-cadre">' +
            '<div class="ph-axe-y" aria-hidden="true">' + etiquettesY + '</div>' +
            '<div class="ph-zone">' +
              zonePlot('<svg class="ph-chart" viewBox="0 0 ' + g.W + ' ' + g.H + '" preserveAspectRatio="none" aria-hidden="true">' +
                grille + ligneBas + trace(xy, g) + '</svg>' + points, pts.length) +
              '<div class="ph-axe-x" aria-hidden="true">' + etiquettesX + '</div>' +
            '</div>' +
          '</div>' +
          '<label class="ph-option"><input type="checkbox" data-plus-bas' + (etat.plusBas ? ' checked' : '') + (histo ? '' : ' disabled') + '>' +
            '<span class="ph-legende-bas"></span> Plus bas prix jamais relevé' + (histo ? ' (' + euros(histo) + ')' : '') + '</label>' +
          '<div class="ph-stats-complet">' +
            '<div><span>Plus bas</span><b>' + euros(min) + '</b></div>' +
            '<div><span>Plus haut</span><b>' + euros(max) + '</b></div>' +
            '<div><span>Moyenne</span><b>' + euros(moyenne) + '</b></div>' +
            '<div><span>Variation</span><b class="' + classeVar + '">' + (variation > 0 ? '+' : variation < 0 ? '−' : '') +
              euros(Math.abs(variation)) + ' (' + (pct > 0 ? '+' : pct < 0 ? '−' : '') + Math.abs(pct).toLocaleString('fr-FR', { maximumFractionDigits: 1 }) + ' %)</b></div>' +
          '</div>' +
          '<p class="ph-note">' + pts.length + ' relevé' + (pts.length > 1 ? 's' : '') + ' sur la période · un point = un relevé du prix Amazon.</p>' +
        '</div>';

      slot.querySelectorAll('[data-jours]').forEach(function (b) {
        b.addEventListener('click', function () { etat.jours = +b.getAttribute('data-jours'); dessiner(); });
      });
      slot.querySelector('[data-plus-bas]').addEventListener('change', function (e) { etat.plusBas = e.target.checked; dessiner(); });
      interactif(slot, pts, xy, g.W, g.H);
    }
    dessiner();
  }

  function mount(slot, componentId, options) {
    if (!slot || !componentId) return;
    var complet = options && options.complet;
    slot.innerHTML = '<div class="price-history is-loading"><span class="skel" style="display:block; height:' + (complet ? 300 : 110) + 'px;"></span></div>';
    fetch('/api/components/' + encodeURIComponent(componentId) + '/prix-historique' + (complet ? '?jours=365' : ''))
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) { (complet ? renderComplet : renderCompact)(slot, data); })
      .catch(function () { slot.innerHTML = ''; });
  }

  window.PCPriceHistory = { mount: mount };
})();
