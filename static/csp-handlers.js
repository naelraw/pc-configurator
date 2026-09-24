/*
 * Remplace les attributs onclick="..." & co, interdits par la Content-Security-
 * Policy du site (script-src 'self', sans 'unsafe-inline').
 *
 * Le HTML écrit data-onclick="maFonction(12, 'texte', this)" : ce script,
 * branché une seule fois sur le document, retrouve l'élément concerné et
 * appelle la fonction globale. Aucune évaluation de code (pas d'eval) : seules
 * des instructions de la forme ci-dessous sont comprises.
 *   fn(args)                       appel d'une fonction globale (window.fn)
 *   return fn(args)                false renvoyé -> preventDefault()
 *   event.stopPropagation()        / event.preventDefault()
 *   this.parentElement.remove()
 *   if(event.key==='Enter') fn()   n'exécute la suite que pour cette touche
 * Arguments acceptés : nombres, chaînes '...' ou "...", this, event, null,
 * true, false, undefined.
 */
(function () {
  'use strict';

  var EVENTS = ['click', 'input', 'change', 'submit', 'keydown'];

  function splitStatements(code) {
    var parts = [], cur = '', quote = null;
    for (var i = 0; i < code.length; i++) {
      var ch = code[i];
      if (quote) {
        cur += ch;
        if (ch === '\\' && i + 1 < code.length) { cur += code[++i]; continue; }
        if (ch === quote) quote = null;
      } else if (ch === '"' || ch === "'") {
        quote = ch; cur += ch;
      } else if (ch === ';') {
        parts.push(cur); cur = '';
      } else {
        cur += ch;
      }
    }
    parts.push(cur);
    return parts.map(function (p) { return p.trim(); }).filter(Boolean);
  }

  function parseArgs(src, el, ev) {
    var args = [], i = 0, n = src.length;
    function skip() { while (i < n && /\s/.test(src[i])) i++; }
    skip();
    if (i >= n) return args;
    while (i < n) {
      skip();
      var ch = src[i];
      if (ch === '"' || ch === "'") {
        var q = ch, s = '';
        i++;
        while (i < n && src[i] !== q) {
          if (src[i] === '\\' && i + 1 < n) {
            var e = src[++i];
            s += e === 'n' ? '\n' : e === 't' ? '\t' : e;
          } else {
            s += src[i];
          }
          i++;
        }
        if (i >= n) throw new Error('chaîne non terminée');
        i++;
        args.push(s);
      } else {
        var m = /^(-?\d+(?:\.\d+)?|[A-Za-z_$][\w$]*)/.exec(src.slice(i));
        if (!m) throw new Error('argument non reconnu : ' + src.slice(i));
        var tok = m[1];
        i += tok.length;
        if (/^-?\d/.test(tok)) args.push(Number(tok));
        else if (tok === 'this') args.push(el);
        else if (tok === 'event') args.push(ev);
        else if (tok === 'null') args.push(null);
        else if (tok === 'true') args.push(true);
        else if (tok === 'false') args.push(false);
        else if (tok === 'undefined') args.push(undefined);
        else throw new Error('identifiant non autorisé : ' + tok);
      }
      skip();
      if (i < n) {
        if (src[i] !== ',') throw new Error('virgule attendue : ' + src.slice(i));
        i++;
      }
    }
    return args;
  }

  function resolve(path) {
    var obj = window, keys = path.split('.');
    for (var k = 0; k < keys.length; k++) {
      if (obj == null) return undefined;
      obj = obj[keys[k]];
    }
    return obj;
  }

  function runStatement(stmt, el, ev) {
    var m;
    if ((m = /^if\s*\(\s*event\.key\s*===?\s*(['"])(\w+)\1\s*\)\s*(.+)$/.exec(stmt))) {
      if (ev.key !== m[2]) return undefined;
      stmt = m[3];
    }
    if (stmt === 'event.stopPropagation()') { ev.stopPropagation(); return undefined; }
    if (stmt === 'event.preventDefault()') { ev.preventDefault(); return undefined; }
    if (stmt === 'this.parentElement.remove()') { el.parentElement.remove(); return undefined; }
    var isReturn = false;
    if (stmt.indexOf('return ') === 0) { isReturn = true; stmt = stmt.slice(7).trim(); }
    m = /^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(([\s\S]*)\)$/.exec(stmt);
    if (!m) throw new Error('instruction non reconnue : ' + stmt);
    var fn = resolve(m[1]);
    if (typeof fn !== 'function') throw new Error('fonction introuvable : ' + m[1]);
    var dot = m[1].lastIndexOf('.');
    var ctx = dot === -1 ? window : resolve(m[1].slice(0, dot));
    var result = fn.apply(ctx, parseArgs(m[2], el, ev));
    return isReturn ? result : undefined;
  }

  function run(code, el, ev) {
    var statements = splitStatements(code), result;
    for (var s = 0; s < statements.length; s++) {
      result = runStatement(statements[s], el, ev);
    }
    return result;
  }

  EVENTS.forEach(function (type) {
    var attr = 'data-on' + type;
    document.addEventListener(type, function (ev) {
      // Reproduit la propagation native : on remonte de la cible vers la
      // racine, et un stopPropagation() appelé par un gestionnaire arrête la
      // remontée vers les éléments parents.
      var stopped = false;
      var nativeStop = ev.stopPropagation;
      ev.stopPropagation = function () { stopped = true; nativeStop.call(ev); };
      for (var el = ev.target; el && el.nodeType === 1 && !stopped; el = el.parentNode) {
        if (!el.hasAttribute(attr)) continue;
        try {
          if (run(el.getAttribute(attr), el, ev) === false) ev.preventDefault();
        } catch (err) {
          console.error('[' + attr + ']', err);
        }
      }
    });
  });
})();
