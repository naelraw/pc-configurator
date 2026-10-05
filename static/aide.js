/*
 * Bulle d'aide PC Radar, en bas à droite de toutes les pages (chargée par
 * nav-menu.js). Une petite discussion avec l'IA sur le fonctionnement du
 * site ; quand on décrit un problème, l'IA propose un ticket que la personne
 * relit puis envoie elle-même (visible dans l'admin, onglet « Tickets »).
 * La discussion est gardée le temps de la visite (sessionStorage).
 */
(function(){
  'use strict';
  if(window.PCAide) return;

  var CLE = 'pcr-aide';
  var ACCUEIL = 'Salut ! Je peux t’aider à utiliser PC Radar, ou transmettre un problème à l’équipe. Pose ta question.';
  var SUGGESTIONS = [
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
    try{ sessionStorage.setItem(CLE, JSON.stringify(etat)); }catch(e){}
  }

  var bouton, panneau, fil, champ, envoyer, enCours = false;

  function echapper(t){
    return String(t == null ? '' : t).replace(/[&<>"']/g, function(c){
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  // Texte de l'IA : gras **...**, adresses du site (/configurateur) cliquables, paragraphes.
  function mettreEnForme(t){
    return echapper(t)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[\s(«])(\/[a-z0-9][a-z0-9\-\/]*)/gi, '$1<a href="$2">$2</a>')
      .split(/\n{2,}/).map(function(p){ return '<p>' + p.replace(/\n/g, '<br>') + '</p>'; }).join('');
  }

  function construire(){
    bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'aide-bouton';
    bouton.setAttribute('aria-label', 'Aide PC Radar');
    bouton.setAttribute('aria-expanded', 'false');
    bouton.title = 'Une question ? Un problème ?';
    bouton.innerHTML = '<svg class="aide-ico-ouvrir" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12Z"/><path d="M9.5 9.6a2.5 2.5 0 0 1 4.8.9c0 1.7-2.3 2-2.3 3.3"/><circle cx="12" cy="16.6" r=".6" fill="currentColor"/></svg>'
      + '<svg class="aide-ico-fermer" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    bouton.addEventListener('click', function(){ basculer(); });

    panneau = document.createElement('div');
    panneau.className = 'aide-panneau';
    panneau.hidden = true;
    panneau.setAttribute('role', 'dialog');
    panneau.setAttribute('aria-label', 'Aide PC Radar');
    panneau.innerHTML =
      '<div class="aide-tete">'
      + '<div><strong>Aide PC Radar</strong><span>Questions sur le site ou problème à signaler</span></div>'
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
      if(e.key === 'Escape' && !panneau.hidden){ basculer(false); bouton.focus(); }
    });
    fil.addEventListener('click', function(e){
      var s = e.target.closest('[data-suggestion]');
      if(s){ poser(s.getAttribute('data-suggestion')); return; }
      if(e.target.closest('.aide-ticket-envoyer')) envoyerTicket();
      if(e.target.closest('.aide-ticket-annuler')){ etat.ticket = null; sauver(); afficher(); }
    });
  }

  function ajusterChamp(){
    champ.style.height = 'auto';
    champ.style.height = Math.min(champ.scrollHeight, 120) + 'px';
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
    }
  }

  function afficher(){
    var html = '<div class="aide-msg aide-ia"><div class="aide-texte">' + mettreEnForme(ACCUEIL) + '</div></div>';
    if(!etat.messages.length){
      html += '<div class="aide-suggestions">' + SUGGESTIONS.map(function(s){
        return '<button type="button" data-suggestion="' + echapper(s) + '">' + echapper(s) + '</button>';
      }).join('') + '</div>';
    }
    etat.messages.forEach(function(m){
      html += '<div class="aide-msg ' + (m.role === 'user' ? 'aide-moi' : 'aide-ia') + (m.erreur ? ' aide-erreur' : '') + '">'
        + '<div class="aide-texte">' + (m.role === 'user' ? '<p>' + echapper(m.content).replace(/\n/g, '<br>') + '</p>' : mettreEnForme(m.content)) + '</div></div>';
    });
    if(enCours) html += '<div class="aide-msg aide-ia"><div class="aide-texte aide-attente"><span></span><span></span><span></span></div></div>';
    if(etat.ticket && !enCours) html += carteTicket(etat.ticket);
    if(etat.ticketEnvoye) html += '<div class="aide-ticket aide-ticket-ok"><strong>Signalement n° ' + echapper(etat.ticketEnvoye) + ' envoyé.</strong> Merci, l’équipe va le regarder.</div>';
    fil.innerHTML = html;
    fil.scrollTop = fil.scrollHeight;
    champ.disabled = envoyer.disabled = enCours;
  }

  function carteTicket(t){
    return '<div class="aide-ticket">'
      + '<div class="aide-ticket-titre">Envoyer ce signalement à l’équipe ?</div>'
      + '<label><span>Résumé</span><input type="text" class="aide-t-titre" maxlength="120" value="' + echapper(t.titre) + '"></label>'
      + '<label><span>Détails</span><textarea class="aide-t-desc" rows="4" maxlength="3000">' + echapper(t.description) + '</textarea></label>'
      + '<label><span>Ton e-mail (facultatif, pour qu’on te réponde)</span><input type="email" class="aide-t-email" maxlength="200" autocomplete="email" placeholder="toi@exemple.fr"></label>'
      + '<p class="aide-ticket-erreur" hidden></p>'
      + '<div class="aide-ticket-actions"><button type="button" class="aide-ticket-annuler">Pas maintenant</button>'
      + '<button type="button" class="aide-ticket-envoyer">Envoyer à l’équipe</button></div>'
      + '</div>';
  }

  function messageErreur(res, data){
    if(res.status === 429 && data && data.detail) return data.detail;
    if(data && typeof data.detail === 'string') return data.detail;
    return 'Petit souci de connexion. Réessaie dans un instant.';
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
    var historique = etat.messages.filter(function(m){ return !m.erreur; })
      .map(function(m){ return { role: m.role, content: m.content.slice(0, 1500) }; }).slice(-12);
    fetch('/api/aide/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: historique, page: location.pathname }),
    }).then(function(res){
      return res.json().catch(function(){ return {}; }).then(function(data){
        if(!res.ok || data.status !== 'ok') throw new Error(messageErreur(res, data));
        etat.messages.push({ role: 'assistant', content: data.message });
        etat.ticket = data.ticket || null;
      });
    }).catch(function(err){
      etat.messages.push({ role: 'assistant', content: err.message, erreur: true });
    }).then(function(){
      enCours = false;
      sauver();
      afficher();
      champ.focus();
    });
  }

  function envoyerTicket(){
    var carte = fil.querySelector('.aide-ticket');
    if(!carte || !etat.ticket) return;
    var erreur = carte.querySelector('.aide-ticket-erreur');
    var titre = carte.querySelector('.aide-t-titre').value.trim();
    var description = carte.querySelector('.aide-t-desc').value.trim();
    var email = carte.querySelector('.aide-t-email').value.trim();
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
