/*
 * Bulle d'aide PC Radar, en bas à droite de toutes les pages (chargée par
 * nav-menu.js).
 * - Avec un compte : c'est l'assistant IA (/api/assistant/chat, mode « aide ») :
 *   questions sur le site ET sur les PC, composants à ajouter en un clic, et
 *   configs ou changements demandés appliqués directement à sa config (même
 *   brouillon que le configurateur), avec « Annuler ».
 * - Sans compte : questions sur le site seulement (/api/aide/chat), l'IA
 *   invite à créer un compte pour les composants et les configs.
 * Dans les deux cas, un problème décrit devient un ticket proposé, que la
 * personne relit puis envoie elle-même (admin, onglet « Tickets »).
 * La discussion est gardée le temps de la visite (sessionStorage).
 */
(function(){
  'use strict';
  if(window.PCAide) return;

  var CLE = 'pcr-aide';
  var BROUILLON = 'pc_configurator_draft';   // même brouillon que le configurateur
  var CHAMPS = {
    cpu_id: 'CPU', motherboard_id: 'Carte mère', ram_id: 'RAM', gpu_id: 'GPU',
    psu_id: 'Alimentation', storage_id: 'Stockage', case_id: 'Boîtier', cooler_id: 'Refroidissement',
  };
  var SUGGESTIONS_COMPTE = [
    'Une config gaming à 1000 €',
    'Quelle carte graphique pour jouer en 1440p ?',
    'Comment suivre le prix d’un composant ?',
    'Je veux signaler un problème',
  ];
  var SUGGESTIONS_VISITEUR = [
    'Comment marche le configurateur ?',
    'Comment suivre le prix d’un composant ?',
    'Je veux signaler un problème',
  ];

  var etat = { messages: [], ticket: null, ticketEnvoye: null };
  try{
    var sauve = JSON.parse(sessionStorage.getItem(CLE) || 'null');
    if(sauve && Array.isArray(sauve.messages)) etat = Object.assign(etat, sauve);
  }catch(e){}
  function sauver(){
    try{
      etat.messages = etat.messages.slice(-40);
      sessionStorage.setItem(CLE, JSON.stringify(etat));
    }catch(e){}
  }

  var connecte = null;          // inconnu tant que /api/auth/me n'a pas répondu
  var bouton, panneau, fil, champ, envoyer, enCours = false;

  function echapper(t){
    return String(t == null ? '' : t).replace(/[&<>"']/g, function(c){
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function euros(n){
    return Number(n || 0).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }
  // Texte de l'IA : gras **...**, listes « - », adresses du site (/configurateur) cliquables.
  function mettreEnForme(t){
    return echapper(t)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[\s(«])(\/[a-z0-9][a-z0-9\-\/]*)/gi, '$1<a href="$2">$2</a>')
      .split(/\n{2,}/).map(function(p){
        var lignes = p.split('\n');
        if(lignes.every(function(l){ return /^\s*[-•]\s/.test(l); })){
          return '<ul>' + lignes.map(function(l){ return '<li>' + l.replace(/^\s*[-•]\s/, '') + '</li>'; }).join('') + '</ul>';
        }
        return '<p>' + lignes.join('<br>') + '</p>';
      }).join('');
  }

  function lireConfig(){
    try{ return JSON.parse(localStorage.getItem(BROUILLON)) || {}; }catch(e){ return {}; }
  }
  function ecrireConfig(config){
    try{ localStorage.setItem(BROUILLON, JSON.stringify(config)); }catch(e){}
    window.dispatchEvent(new Event('pcr-config-modifiee'));   // configurateur ouvert : mis à jour tout de suite
  }
  function suivre(type){
    try{
      fetch('/api/assistant/evenement', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: type }), keepalive: true }).catch(function(){});
    }catch(e){}
  }
  function image(f){
    if(!f.image_url) return '';
    var src = /^\/api\//.test(f.image_url) ? f.image_url + '?w=96' : f.image_url;
    return '<img src="' + echapper(src) + '" alt="" loading="lazy">';
  }

  // ------------------------------------------------------------------ Fenêtre
  function construire(){
    bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'aide-bouton';
    bouton.setAttribute('aria-label', 'Aide PC Radar');
    bouton.setAttribute('aria-expanded', 'false');
    bouton.title = 'Une question ? Un problème ?';
    bouton.innerHTML = '<img class="aide-ico-ouvrir" src="/static/favicon.svg" alt="" width="54" height="54">'
      + '<svg class="aide-ico-fermer" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    bouton.addEventListener('click', function(){ basculer(); });

    panneau = document.createElement('div');
    panneau.className = 'aide-panneau';
    panneau.hidden = true;
    panneau.setAttribute('role', 'dialog');
    panneau.setAttribute('aria-label', 'Aide PC Radar');
    panneau.innerHTML =
      '<div class="aide-tete">'
      + '<div><strong>Aide PC Radar</strong><span class="aide-sous-titre">Questions sur le site ou problème à signaler</span></div>'
      + '<button type="button" class="aide-nouvelle" title="Nouvelle discussion" aria-label="Nouvelle discussion"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg></button>'
      + '<button type="button" class="aide-fermer" aria-label="Fermer l’aide"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>'
      + '</div>'
      + '<div class="aide-fil" aria-live="polite"></div>'
      + '<form class="aide-saisie">'
      + '<textarea rows="1" maxlength="1500" placeholder="Écris ta question…" aria-label="Ta question"></textarea>'
      + '<button type="submit" aria-label="Envoyer"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>'
      + '</form>';
    document.body.appendChild(panneau);
    document.body.appendChild(bouton);

    fil = panneau.querySelector('.aide-fil');
    champ = panneau.querySelector('textarea');
    envoyer = panneau.querySelector('.aide-saisie button');
    panneau.querySelector('.aide-fermer').addEventListener('click', function(){ basculer(false); });
    panneau.querySelector('.aide-nouvelle').addEventListener('click', function(){
      etat = { messages: [], ticket: null, ticketEnvoye: null };
      sauver();
      afficher();
      champ.focus();
    });
    panneau.querySelector('.aide-saisie').addEventListener('submit', function(e){
      e.preventDefault();
      poser(champ.value);
    });
    champ.addEventListener('keydown', function(e){
      if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); poser(champ.value); }
    });
    champ.addEventListener('input', ajusterChamp);
    document.addEventListener('keydown', function(e){
      // La fiche d'un composant (loupe) passe devant : Échap la ferme seule
      // (elle a déjà traité la touche : defaultPrevented).
      var fiche = document.querySelector('.gs-overlay');
      if(e.key === 'Escape' && !e.defaultPrevented && !panneau.hidden && !(fiche && !fiche.hidden)){ basculer(false); bouton.focus(); }
    });
    fil.addEventListener('click', clic);
  }

  function ajusterChamp(){
    champ.style.height = 'auto';
    champ.style.height = Math.min(champ.scrollHeight, 120) + 'px';
  }

  function verifierCompte(){
    return fetch('/api/auth/me', { credentials: 'same-origin' }).then(function(r){ return r.json(); })
      .then(function(d){ connecte = !!d.logged_in; })
      .catch(function(){ connecte = false; });
  }

  function basculer(ouvrir){
    if(!panneau) construire();
    var ouvert = ouvrir === undefined ? panneau.hidden : ouvrir;
    panneau.hidden = !ouvert;
    bouton.classList.toggle('est-ouvert', ouvert);
    bouton.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
    if(ouvert){
      afficher();
      setTimeout(function(){ champ.focus(); }, 30);
      verifierCompte().then(function(){ if(!enCours) afficher(); });
    }
  }

  // ------------------------------------------------------------------ Affichage
  function accueil(){
    return connecte
      ? 'Salut ! Je peux te proposer des composants ou une config complète à mettre dans ta config en un clic, répondre à tes questions sur PC Radar, ou transmettre un problème à l’équipe.'
      : 'Salut ! Je peux t’aider à utiliser PC Radar, ou transmettre un problème à l’équipe. Pose ta question.'
        + (connecte === false ? '\n\nAvec un compte gratuit (/compte), je peux aussi te proposer des composants et des configs complètes.' : '');
  }

  function afficher(){
    var sous = panneau.querySelector('.aide-sous-titre');
    sous.textContent = connecte ? 'Composants, configs, questions sur le site' : 'Questions sur le site ou problème à signaler';
    var html = '<div class="aide-msg aide-ia"><div class="aide-texte">' + mettreEnForme(accueil()) + '</div></div>';
    if(!etat.messages.length){
      html += '<div class="aide-suggestions">' + (connecte ? SUGGESTIONS_COMPTE : SUGGESTIONS_VISITEUR).map(function(s){
        return '<button type="button" data-suggestion="' + echapper(s) + '">' + echapper(s) + '</button>';
      }).join('') + '</div>';
    }
    var config = lireConfig();
    etat.messages.forEach(function(m, i){
      if(m.role === 'user'){
        html += '<div class="aide-msg aide-moi"><div class="aide-texte"><p>' + echapper(m.content).replace(/\n/g, '<br>') + '</p></div></div>';
        return;
      }
      html += '<div class="aide-msg aide-ia' + (m.erreur ? ' aide-erreur' : '') + '"><div class="aide-texte">' + mettreEnForme(m.content) + '</div></div>';
      if(m.suggestion) html += recapitulatif(m, i);
      else if((m.composants || []).length) html += listePieces(m, config);
      html += blocFps(m.fps);
      html += boutonsLiens(m.liens);
    });
    if(enCours) html += '<div class="aide-msg aide-ia"><div class="aide-texte aide-attente"><span></span><span></span><span></span></div></div>';
    if(etat.ticket && !enCours) html += carteTicket(etat.ticket);
    if(etat.ticketEnvoye) html += '<div class="aide-ticket aide-ticket-ok"><strong>Signalement n° ' + echapper(etat.ticketEnvoye) + ' envoyé.</strong> Merci, l’équipe va le regarder.</div>';
    var position = fil.scrollTop;
    fil.innerHTML = html;
    fil.scrollTop = afficher.garderPosition ? position : fil.scrollHeight;
    afficher.garderPosition = false;
    champ.disabled = envoyer.disabled = enCours;
  }

  // Même contenu que sur la page de l'assistant : le texte d'estimation et,
  // s'il y a un goulot d'étranglement, la pièce à changer.
  // Liens fabriqués par le serveur (panier Amazon, partage, fiches, pages du site).
  function boutonsLiens(liens){
    if(!liens || !liens.length) return '';
    return '<div class="aide-liens">' + liens.map(function(l){
      return '<a class="aide-lien' + (l.externe ? ' aide-lien-externe' : '') + '" href="' + echapper(l.url) + '"'
        + (l.externe ? ' target="_blank" rel="noopener noreferrer sponsored"' : '') + '>' + echapper(l.libelle) + (l.externe ? ' ↗' : '') + '</a>';
    }).join('') + '</div>';
  }

  function blocFps(fps){
    if(!fps || !fps.estimation) return '';
    var conseil = fps.suggestion
      ? '<p>Remplacer ton ' + echapper(fps.suggestion.categorie) + ' par <strong>' + echapper(fps.suggestion.nom) + '</strong>'
        + (fps.suggestion.prix_indicatif != null ? ' (' + euros(fps.suggestion.prix_indicatif) + ')' : '') + ' réduirait ce goulot d’étranglement.</p>'
      : '';
    return '<div class="aide-fps"><b>Estimation FPS</b><p>' + echapper(String(fps.estimation)).trim().replace(/\n/g, '<br>') + '</p>' + conseil + '</div>';
  }

  function etatAjout(f, config){
    if(config[f.categorie] === f.id) return '<span class="aide-dedans">✓ Dans ma config</span>';
    return '<button type="button" class="aide-mini" data-ajouter="' + f.id + '">' + (config[f.categorie] ? 'Remplacer' : 'Ajouter') + '</button>';
  }

  function listePieces(m, config){
    var fiches = m.fiches || {};
    var lignes = m.composants.map(function(id){ return fiches[id]; }).filter(Boolean).map(function(f){
      return '<li class="aide-piece">'
        + '<button type="button" class="aide-piece-image' + (f.image_processed ? ' is-transparent' : '') + '" data-detail="' + f.id + '" aria-label="Voir ' + echapper(f.nom) + '">' + image(f) + '</button>'
        + '<div class="aide-piece-infos"><span class="aide-piece-cat">' + echapper(f.categorie) + (f.en_stock === false ? ' · épuisé' : '') + '</span>'
        + '<button type="button" class="aide-piece-nom" data-detail="' + f.id + '">' + echapper(f.nom) + '</button>'
        + '<span class="aide-piece-prix">' + euros(f.prix_indicatif) + '</span></div>'
        + '<div class="aide-piece-actions">' + etatAjout(f, config) + '</div>'
        + '</li>';
    }).join('');
    return lignes ? '<ul class="aide-pieces">' + lignes + '</ul>' : '';
  }

  // Une config proposée est mise directement dans la config de la personne
  // (pas de confirmation) : on montre seulement ce qui a changé, avec
  // « Annuler » pour revenir à la config d'avant.
  function appliquerConfig(m){
    var avant = lireConfig();
    var apres = Object.assign({}, avant);
    var changements = [], total = 0;
    Object.keys(CHAMPS).forEach(function(champ){
      var f = (m.fiches || {})[m.suggestion[champ]];
      if(!f){
        // Processeur vendu avec son ventirad : l'ancien refroidissement n'a plus lieu d'être.
        if(champ === 'cooler_id' && m.suggestion.ventirad_fourni && apres.Refroidissement){
          delete apres.Refroidissement;
          changements.push({ categorie: 'Refroidissement', nom: 'ventirad fourni avec le processeur', prix: null });
        }
        return;
      }
      total += Number(f.prix_indicatif) || 0;
      if(apres[f.categorie] !== f.id){
        apres[f.categorie] = f.id;
        changements.push({ categorie: CHAMPS[champ], nom: f.nom, prix: f.prix_indicatif, id: f.id });
      }
    });
    ecrireConfig(apres);
    m.avant = avant;
    m.changements = changements;
    m.total = total;
    suivre('tout_ajouter');
  }

  function recapitulatif(m, index){
    if(m.annule){
      return '<div class="aide-recap aide-recap-annule">Changement annulé, ta config est revenue comme avant.</div>';
    }
    var lignes = (m.changements || []).map(function(c){
      return '<li><span class="aide-piece-cat">' + echapper(c.categorie) + '</span>'
        + (c.id ? '<button type="button" class="aide-piece-nom" data-detail="' + c.id + '">' + echapper(c.nom) + '</button>' : '<span>' + echapper(c.nom) + '</span>')
        + (c.prix != null ? '<span class="aide-piece-prix">' + euros(c.prix) + '</span>' : '') + '</li>';
    }).join('');
    return '<div class="aide-recap">'
      + '<div class="aide-recap-titre">✓ ' + (lignes ? 'Mis dans ta config' : 'Ta config contenait déjà tout ça') + '</div>'
      + (lignes ? '<ul>' + lignes + '</ul>' : '')
      + '<div class="aide-recap-pied"><span>Total <strong>' + euros(m.total) + '</strong></span>'
      + (location.pathname === '/configurateur' ? '' : '<a href="/configurateur">Voir ma config</a>')
      + (lignes ? '<button type="button" data-annuler="' + index + '">Annuler</button>' : '')
      + '</div></div>';
  }

  function carteTicket(t){
    return '<div class="aide-ticket">'
      + '<div class="aide-ticket-titre">Envoyer ce signalement à l’équipe ?</div>'
      + '<label><span>Résumé</span><input type="text" class="aide-t-titre" maxlength="120" value="' + echapper(t.titre) + '"></label>'
      + '<label><span>Détails</span><textarea class="aide-t-desc" rows="4" maxlength="3000">' + echapper(t.description) + '</textarea></label>'
      + (connecte ? '' : '<label><span>Ton e-mail (facultatif, pour qu’on te réponde)</span><input type="email" class="aide-t-email" maxlength="200" autocomplete="email" placeholder="toi@exemple.fr"></label>')
      + '<p class="aide-ticket-erreur" hidden></p>'
      + '<div class="aide-ticket-actions"><button type="button" class="aide-ticket-annuler">Pas maintenant</button>'
      + '<button type="button" class="aide-ticket-envoyer">Envoyer à l’équipe</button></div>'
      + '</div>';
  }

  // ------------------------------------------------------------------ Actions
  function trouverFiche(id){
    for(var i = etat.messages.length - 1; i >= 0; i--){
      var f = (etat.messages[i].fiches || {})[id];
      if(f) return f;
    }
    return null;
  }

  function ajouterPieces(fiches){
    var config = lireConfig();
    fiches.forEach(function(f){ if(f) config[f.categorie] = f.id; });
    ecrireConfig(config);
    afficher.garderPosition = true;
    afficher();
  }

  function ouvrirDetail(id){
    function go(){ window.PCRechercheGlobale.ouvrirId(id); }
    if(window.PCRechercheGlobale) return go();
    var s = document.createElement('script');
    s.src = '/static/recherche-globale.js';
    s.onload = function(){ if(window.PCRechercheGlobale) go(); };
    document.head.appendChild(s);
  }




  function clic(e){
    var t = e.target.closest('button, a');
    if(!t) return;
    if(t.hasAttribute('data-suggestion')){ poser(t.getAttribute('data-suggestion')); return; }
    if(t.hasAttribute('data-detail')){ ouvrirDetail(Number(t.getAttribute('data-detail'))); return; }
    if(t.hasAttribute('data-ajouter')){ suivre('ajout'); ajouterPieces([trouverFiche(t.getAttribute('data-ajouter'))]); return; }
    if(t.classList.contains('aide-ticket-envoyer')){ envoyerTicket(); return; }
    if(t.classList.contains('aide-ticket-annuler')){ etat.ticket = null; sauver(); afficher(); return; }
    var m;
    if(t.hasAttribute('data-annuler')){
      m = etat.messages[Number(t.getAttribute('data-annuler'))];
      if(m && m.avant){ ecrireConfig(m.avant); m.annule = true; sauver(); afficher.garderPosition = true; afficher(); }
    }
  }

  function messageErreur(res, data){
    if(data && typeof data.detail === 'string') return data.detail;
    if(data && typeof data.message === 'string' && data.message) return data.message;
    return 'Petit souci de connexion. Réessaie dans un instant.';
  }

  // Historique envoyé à l'IA : les configs et composants montrés sont résumés
  // (avec leur id) pour qu'elle sache de quoi on parle.
  function historique(){
    return etat.messages.filter(function(m){ return !m.erreur; }).slice(-12).map(function(m){
      var texte = m.content;
      if(m.suggestion){
        texte += '\n(Config proposée : ' + Object.keys(CHAMPS).map(function(c){
          var f = (m.fiches || {})[m.suggestion[c]];
          return f ? CHAMPS[c] + ' ' + f.nom : null;
        }).filter(Boolean).join(', ') + ')';
      }else if((m.composants || []).length){
        texte += '\n(Composants montrés : ' + m.composants.map(function(id){
          var f = (m.fiches || {})[id];
          return f ? f.nom + ' [id ' + f.id + ']' : null;
        }).filter(Boolean).join(', ') + ')';
      }
      return { role: m.role, content: texte.slice(0, 1800) };
    });
  }

  function demander(avecCompte){
    var derniere = null;
    for(var i = etat.messages.length - 1; i >= 0; i--){ if(etat.messages[i].suggestion){ derniere = etat.messages[i].suggestion; break; } }
    var url = avecCompte ? '/api/assistant/chat' : '/api/aide/chat';
    var corps = avecCompte
      ? { messages: historique(), aide: true, page: location.pathname, derniere_config: derniere, ma_config: lireConfig() }
      : { messages: historique(), page: location.pathname };
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) })
      .then(function(res){
        return res.json().catch(function(){ return {}; }).then(function(data){
          // Session expirée entre-temps : on continue en mode visiteur.
          if(avecCompte && res.status === 401){ connecte = false; return demander(false); }
          if(!res.ok || data.status !== 'ok') throw new Error(messageErreur(res, data));
          return data;
        });
      });
  }

  function poser(texte){
    texte = String(texte || '').trim();
    if(!texte || enCours) return;
    champ.value = '';
    ajusterChamp();
    etat.messages.push({ role: 'user', content: texte });
    etat.ticket = null;
    etat.ticketEnvoye = null;
    enCours = true;
    sauver();
    afficher();
    (connecte === null ? verifierCompte() : Promise.resolve()).then(function(){
      return demander(connecte);
    }).then(function(data){
      var reponse = {
        role: 'assistant', content: data.message || '',
        suggestion: data.suggestion || null,
        composants: Array.isArray(data.composants) ? data.composants : [],
        fiches: data.fiches || null,
        fps: data.fps_estimation || null,
        liens: Array.isArray(data.liens) ? data.liens : [],
      };
      if(reponse.suggestion) appliquerConfig(reponse);
      etat.messages.push(reponse);
      etat.ticket = data.ticket || null;
    }).catch(function(err){
      etat.messages.push({ role: 'assistant', content: err.message, erreur: true });
    }).then(function(){
      enCours = false;
      sauver();
      afficher();
      // Une config ou des composants : on montre le début de la réponse, pas le bas de la liste.
      var bulles = fil.querySelectorAll('.aide-ia');
      var derniere = bulles[bulles.length - 1];
      var suite = derniere && derniere.nextElementSibling;
      if(suite && /aide-pieces/.test(suite.className)) fil.scrollTop = Math.max(0, derniere.offsetTop - 8);
      champ.focus();
    });
  }

  function envoyerTicket(){
    var carte = fil.querySelector('.aide-ticket');
    if(!carte || !etat.ticket) return;
    var erreur = carte.querySelector('.aide-ticket-erreur');
    var titre = carte.querySelector('.aide-t-titre').value.trim();
    var description = carte.querySelector('.aide-t-desc').value.trim();
    var champEmail = carte.querySelector('.aide-t-email');
    var email = champEmail ? champEmail.value.trim() : '';
    if(titre.length < 3 || description.length < 5){
      erreur.textContent = 'Ajoute un petit résumé et quelques détails.';
      erreur.hidden = false;
      return;
    }
    var bout = carte.querySelector('.aide-ticket-envoyer');
    bout.disabled = true;
    bout.textContent = 'Envoi…';
    fetch('/api/aide/ticket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        categorie: etat.ticket.categorie || 'autre', titre: titre, description: description,
        page: location.pathname, email: email || null,
        discussion: etat.messages.filter(function(m){ return !m.erreur; })
          .map(function(m){ return { role: m.role, content: m.content.slice(0, 1500) }; }).slice(-20),
      }),
    }).then(function(res){
      return res.json().catch(function(){ return {}; }).then(function(data){
        if(!res.ok || data.status !== 'ok'){
          var d = data && data.detail;
          throw new Error(Array.isArray(d) ? 'Vérifie les champs (e-mail, longueur du texte).' : messageErreur(res, data));
        }
        etat.ticket = null;
        etat.ticketEnvoye = data.id;
        sauver();
        afficher();
      });
    }).catch(function(err){
      erreur.textContent = err.message;
      erreur.hidden = false;
      bout.disabled = false;
      bout.textContent = 'Envoyer à l’équipe';
    });
  }

  window.PCAide = { ouvrir: function(){ basculer(true); } };
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', construire);
  else construire();
})();
