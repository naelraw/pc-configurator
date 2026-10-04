/*
 * Historique du prix d'un composant dans sa fiche détail :
 *   PCPriceHistory.mount(emplacement, idDuComposant)
 * Courbe SVG sur 90 jours (un relevé par jour, voir /api/components/{id}/prix-historique),
 * avec le plus bas et le plus haut de la période. Interactive : en survolant
 * la courbe (souris), en glissant le doigt (téléphone) ou avec les flèches
 * (clavier), on lit le prix de chaque jour.
 */
(function () {
  'use strict';

  var W = 320, H = 84, PAD_Y = 8, INSET = 5;  // marge : le point final n'est pas rogné
  var JOUR = 24 * 3600 * 1000;

  function euros(n) {
    return Number(n).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
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

  // Position de chaque relevé : x selon sa vraie date (un jour sans relevé
  // laisse un écart), y selon le prix.
  function positions(points, min, max) {
    var span = max - min || 1;
    var t0 = temps(points[0].date), t1 = temps(points[points.length - 1].date);
    var duree = Math.max(t1 - t0, JOUR);
    return points.map(function (p) {
      var x = points.length === 1 ? W / 2 : INSET + ((temps(p.date) - t0) / duree) * (W - 2 * INSET);
      var y = PAD_Y + (1 - (p.prix - min) / span) * (H - 2 * PAD_Y);
      return [x, y];
    });
  }

  function chart(xy) {
    var line = xy.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var last = xy[xy.length - 1];
    var area = line + ' L' + last[0].toFixed(1) + ' ' + H + ' L' + xy[0][0].toFixed(1) + ' ' + H + ' Z';
    return '<svg class="ph-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<path class="ph-area" d="' + area + '"/>' +
      '<path class="ph-line" d="' + line + '" vector-effect="non-scaling-stroke"/>' +
      '</svg>';
  }

  function render(slot, data) {
    var pts = data.points || [];
    if (pts.length < 2) {
      slot.innerHTML = '<div class="price-history"><div class="ph-head"><span class="ph-title">Évolution du prix</span></div>' +
        '<p class="ph-empty">Le prix est relevé chaque jour : la courbe apparaîtra dès le deuxième relevé' +
        (pts.length ? ' (premier relevé le ' + dateFr(pts[0].date) + ').' : '.') + '</p></div>';
      return;
    }
    var current = pts[pts.length - 1].prix;
    var trend = current <= data.min ? ' <span class="ph-badge">Au plus bas</span>' : '';
    var xy = positions(pts, data.min, data.max);
    slot.innerHTML =
      '<div class="price-history">' +
        '<div class="ph-head"><span class="ph-title">Évolution du prix' + trend + '</span>' +
        '<span class="ph-range">' + dateFr(pts[0].date) + ' → ' + dateFr(pts[pts.length - 1].date) + '</span></div>' +
        '<div class="ph-lecture" aria-live="polite"></div>' +
        '<div class="ph-plot" tabindex="0" role="slider" aria-label="Prix jour par jour : flèches gauche et droite pour changer de jour"' +
          ' aria-valuemin="0" aria-valuemax="' + (pts.length - 1) + '">' +
          chart(xy) +
          '<span class="ph-guide" aria-hidden="true"></span><span class="ph-point" aria-hidden="true"></span>' +
        '</div>' +
        '<div class="ph-stats">' +
          '<span>Plus bas <b>' + euros(data.min) + '</b></span>' +
          '<span>Plus haut <b>' + euros(data.max) + '</b></span>' +
        '</div>' +
      '</div>';
    interactif(slot, pts, xy);
  }

  function interactif(slot, pts, xy) {
    var plot = slot.querySelector('.ph-plot');
    var guide = slot.querySelector('.ph-guide');
    var point = slot.querySelector('.ph-point');
    var lecture = slot.querySelector('.ph-lecture');
    var dernier = pts.length - 1;
    var actuel = dernier;

    function montrer(i, survol) {
      actuel = i;
      var gauche = (xy[i][0] / W * 100) + '%';
      guide.style.left = gauche;
      point.style.left = gauche;
      point.style.top = (xy[i][1] / H * 100) + '%';
      plot.classList.toggle('is-survol', !!survol);
      var precedent = i > 0 ? pts[i - 1].prix : null;
      var ecart = precedent !== null && pts[i].prix !== precedent
        ? ' <span class="ph-ecart ' + (pts[i].prix < precedent ? 'is-baisse' : 'is-hausse') + '">' +
          (pts[i].prix < precedent ? '−' : '+') + euros(Math.abs(pts[i].prix - precedent)) + '</span>'
        : '';
      lecture.innerHTML = '<span class="ph-jour">' + (i === dernier ? "Aujourd'hui" : dateLongue(pts[i].date)) + '</span>' +
        '<b>' + euros(pts[i].prix) + '</b>' + ecart;
      plot.setAttribute('aria-valuenow', i);
      plot.setAttribute('aria-valuetext', dateLongue(pts[i].date) + ' : ' + euros(pts[i].prix));
    }

    function plusProche(clientX) {
      var r = plot.getBoundingClientRect();
      var x = (clientX - r.left) / r.width * W;
      var meilleur = 0;
      for (var i = 1; i < xy.length; i++) {
        if (Math.abs(xy[i][0] - x) < Math.abs(xy[meilleur][0] - x)) meilleur = i;
      }
      return meilleur;
    }

    // Souris et doigt : même code (Pointer Events). Le défilement vertical
    // de la page reste possible au doigt (touch-action: pan-y en CSS).
    plot.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' && plot.setPointerCapture) plot.setPointerCapture(e.pointerId);
      montrer(plusProche(e.clientX), true);
    });
    plot.addEventListener('pointermove', function (e) { montrer(plusProche(e.clientX), true); });
    plot.addEventListener('pointerleave', function () { montrer(dernier, false); });
    plot.addEventListener('pointerup', function (e) {
      if (e.pointerType !== 'mouse') montrer(dernier, false);
    });
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

  function mount(slot, componentId) {
    if (!slot || !componentId) return;
    slot.innerHTML = '<div class="price-history is-loading"><span class="skel" style="display:block; height:110px;"></span></div>';
    fetch('/api/components/' + encodeURIComponent(componentId) + '/prix-historique')
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) { render(slot, data); })
      .catch(function () { slot.innerHTML = ''; });
  }

  window.PCPriceHistory = { mount: mount };
})();
