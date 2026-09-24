/*
 * Historique du prix d'un composant dans sa fiche détail :
 *   PCPriceHistory.mount(emplacement, idDuComposant)
 * Courbe SVG sur 90 jours (un relevé par jour, voir /api/components/{id}/prix-historique),
 * avec le plus bas et le plus haut de la période.
 */
(function () {
  'use strict';

  var W = 320, H = 84, PAD_Y = 8, INSET = 5;  // marge : le point final n'est pas rogné

  function euros(n) {
    return Number(n).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }

  function dateFr(iso) {
    var p = iso.split('-');
    return p[2] + '/' + p[1];
  }

  function chart(points, min, max) {
    var span = max - min || 1;
    var n = points.length;
    var xy = points.map(function (p, i) {
      var x = n === 1 ? W / 2 : INSET + (i / (n - 1)) * (W - 2 * INSET);
      var y = PAD_Y + (1 - (p.prix - min) / span) * (H - 2 * PAD_Y);
      return [x, y];
    });
    var line = xy.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var last = xy[xy.length - 1];
    var area = line + ' L' + last[0].toFixed(1) + ' ' + H + ' L' + xy[0][0].toFixed(1) + ' ' + H + ' Z';
    return '<svg class="ph-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="Évolution du prix sur la période">' +
      '<path class="ph-area" d="' + area + '"/>' +
      '<path class="ph-line" d="' + line + '" vector-effect="non-scaling-stroke"/>' +
      '<circle class="ph-dot" cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="3"/>' +
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
    slot.innerHTML =
      '<div class="price-history">' +
        '<div class="ph-head"><span class="ph-title">Évolution du prix' + trend + '</span>' +
        '<span class="ph-range">' + dateFr(pts[0].date) + ' → ' + dateFr(pts[pts.length - 1].date) + '</span></div>' +
        chart(pts, data.min, data.max) +
        '<div class="ph-stats">' +
          '<span>Plus bas <b>' + euros(data.min) + '</b></span>' +
          '<span>Plus haut <b>' + euros(data.max) + '</b></span>' +
        '</div>' +
      '</div>';
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
