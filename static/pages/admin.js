  // =====================================================================
  // Administration PC Radar
  //
  // Une page, plusieurs vues (menu de gauche) : tableau de bord, contrôle
  // « à surveiller », catalogue + tiroir d'édition, import, liens,
  // statistiques, configurations recommandées. Tous les gestionnaires
  // d'événements passent par data-on* (voir csp-handlers.js : pas de script
  // inline autorisé), d'où les fonctions globales.
  // =====================================================================

  const API_BASE = window.location.origin;
  const ADMIN_SECRET_STORAGE_KEY = 'pc_configurator_admin_secret';
  const CATEGORIES = ['CPU', 'Carte mère', 'RAM', 'GPU', 'Stockage', 'Alimentation', 'Boîtier', 'Refroidissement', 'Accessoire'];

  // Champs utilisés par le contrôle de compatibilité (miroir de schema.REQUIRED_FIELDS),
  // avec leur type pour convertir la saisie (« 5 x M.2 » -> 5, « AM4, AM5 » -> liste).
  const REQUIRED_FIELDS = {
    'CPU': { socket: 'str', tdp: 'number' },
    'Carte mère': { socket: 'str', ram_type: 'str', format: 'str', m2_slots: 'number', sata_ports: 'number' },
    'RAM': { type: 'str' },
    'Boîtier': { formats_supportes: 'list', gpu_max_length_mm: 'number', cpu_cooler_max_height_mm: 'number' },
    'Alimentation': { wattage: 'number' },
    'GPU': { tdp: 'number', longueur_mm: 'number' },
    'Stockage': { type: 'str' },
    'Refroidissement': { sockets_supportes: 'list', hauteur_mm: 'number' },
  };
  const FIELD_LABELS = {
    prix: 'prix', image: 'image', socket: 'socket', tdp: 'TDP', ram_type: 'type de RAM', format: 'format',
    m2_slots: 'slots M.2', sata_ports: 'ports SATA', type: 'type', formats_supportes: 'formats supportés',
    gpu_max_length_mm: 'longueur GPU max', cpu_cooler_max_height_mm: 'hauteur ventirad max', wattage: 'puissance',
    longueur_mm: 'longueur', sockets_supportes: 'sockets', hauteur_mm: 'hauteur',
  };

  let adminSecret = '';
  let components = [];          // catalogue complet (version admin : vraies URL d'image)
  let watchData = null;         // rapport du contrôle du catalogue
  let watchTab = 'prix';
  let editing = null;           // composant ouvert dans le tiroir (null = création)
  let currentAmazonDetails = [];
  let currentAmazonDescription = null;
  let rowsShown = 150;

  // ---------------------------------------------------------------------
  // Utilitaires
  // ---------------------------------------------------------------------
  function escapeHtml(str){
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
      .replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  // Pour une chaîne placée entre apostrophes dans un data-onclick="...".
  function jsArg(str){
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }
  const euros = v => Number(v || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  const nombre = v => Number(v || 0).toLocaleString('fr-FR');
  const norm = s => (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const $ = id => document.getElementById(id);

  async function api(path, options = {}){
    const res = await fetch(API_BASE + path, {
      ...options,
      headers: { 'X-Admin-Secret': adminSecret, ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    const data = await res.json().catch(() => ({}));
    if(!res.ok || data.status === 'error'){
      const details = (data.errors || []).join('\n');
      throw new Error((data.detail || data.message || ('Erreur ' + res.status)) + (details ? '\n' + details : ''));
    }
    return data;
  }
  const post = (path, body) => api(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

  let toastTimer = null;
  function toast(message, isError){
    const el = $('toast');
    el.textContent = message;
    el.className = 'toast' + (isError ? ' error' : '');
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 6000 : 2800);
  }

  // ---------------------------------------------------------------------
  // Connexion
  // ---------------------------------------------------------------------
  async function login(){
    const val = $('secret-input').value.trim();
    if(!val) return;
    $('login-btn').disabled = true;
    $('login-error').hidden = true;
    try{
      const res = await fetch(API_BASE + '/api/admin/verify', { headers: { 'X-Admin-Secret': val } });
      if(res.status === 200){
        adminSecret = val;
        try{ localStorage.setItem(ADMIN_SECRET_STORAGE_KEY, val); }catch(e){}
        startApp();
      }else{
        $('login-error').textContent = res.status === 429 ? 'Trop de tentatives, réessaie plus tard.' : 'Mot de passe incorrect.';
        $('login-error').hidden = false;
      }
    }catch(e){
      $('login-error').textContent = 'Erreur réseau : ' + e.message;
      $('login-error').hidden = false;
    }finally{
      $('login-btn').disabled = false;
    }
  }

  // Mot de passe déjà enregistré : on masque le formulaire pendant la
  // vérification (plus de « flash » de la page de connexion). Le mot de
  // passe n'est oublié que si le serveur le refuse vraiment (401) : pendant
  // un redémarrage du site (502/503) ou une limite passagère (429), on
  // réessaie quelques secondes au lieu de renvoyer vers la connexion.
  async function tryAutoLogin(){
    let saved = null;
    try{ saved = localStorage.getItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
    if(!saved) return;
    $('login-view').hidden = true;
    let dernierStatut = null;
    for(let essai = 0; essai < 6; essai++){
      try{
        const res = await fetch(API_BASE + '/api/admin/verify', { headers: { 'X-Admin-Secret': saved } });
        dernierStatut = res.status;
        if(res.status === 200){ adminSecret = saved; startApp(); return; }
        if(res.status === 401){ try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){} break; }
      }catch(e){ dernierStatut = 'réseau'; }
      await new Promise(r => setTimeout(r, 1500 + essai * 1000));
    }
    $('login-view').hidden = false;
    if(dernierStatut !== 401){
      $('login-error').textContent = 'Le serveur ne répond pas pour le moment (redémarrage ?). Recharge la page dans quelques secondes.';
      $('login-error').hidden = false;
    }
  }

  function logout(){
    try{ localStorage.removeItem(ADMIN_SECRET_STORAGE_KEY); }catch(e){}
    window.location.reload();
  }

  function openSite(){ window.open('/', '_blank', 'noopener'); }

  // Rapport des revenus du mois dans le compte Amazon Partenaires.
  function openAmazonReports(){
    window.open('https://partenaires.amazon.fr/p/reporting/earnings?ac-ms-src=summaryforthismonth', '_blank', 'noopener');
  }

  async function copyLink(url){
    try{ await navigator.clipboard.writeText(url); toast('Lien copié : ' + url.replace('https://', '')); }
    catch(e){ toast('Copie impossible : ' + url, true); }
  }

  // Le .zip est protégé par le mot de passe admin (en-tête) : un simple lien
  // ne l'enverrait pas, d'où le passage par fetch puis un lien temporaire.
  async function downloadExtension(){
    try{
      const res = await fetch(API_BASE + '/api/admin/extension.zip', { headers: { 'X-Admin-Secret': adminSecret } });
      if(!res.ok) throw new Error('Erreur ' + res.status);
      const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'pc-radar-extension.zip';
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      toast('Extension téléchargée. Dézippe-la, puis chrome://extensions → Mode développeur → « Charger l’extension non empaquetée ».');
    }catch(e){ toast('Téléchargement impossible : ' + e.message, true); }
  }

  function startApp(){
    $('login-view').hidden = true;
    $('app').hidden = false;
    $('dash-date').textContent = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    const catOptions = CATEGORIES.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    $('catalog-category').insertAdjacentHTML('beforeend', catOptions);
    $('f-categorie').innerHTML = catOptions;
    const initial = (location.hash || '').slice(1);
    showView(document.querySelector(`[data-section="${initial}"]`) ? initial : 'dashboard');
    refreshAll();
  }

  // Tout ce qui alimente le tableau de bord, chargé en parallèle.
  async function refreshAll(){
    await Promise.allSettled([loadComponents(), loadWatch(), loadStats(), loadQuotas(), loadBuilds(), loadTickets(), loadReleve()]);
    renderDashboard();
  }

  // ---------------------------------------------------------------------
  // Relevé des prix : échéancier commun (PC, extension, services au quota)
  // ---------------------------------------------------------------------
  const dureeReleve = h => h == null ? '—' : h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} j`;
  const NOMS_POSTES = { PC: 'Programme du PC', Extension: 'Extension du navigateur' };

  async function loadReleve(){
    const zone = $('releve-contenu');
    let r;
    try{ r = await api('/api/admin/releve-prix'); }
    catch(e){ zone.innerHTML = '<p class="empty">Relevé indisponible pour le moment.</p>'; return; }
    const cap = r.capacite || {};
    const lignes = r.categories.map(c => {
      const pct = c.total ? Math.round(c.a_jour / c.total * 100) : 0;
      return `<tr><td>${escapeHtml(c.nom)}</td>
        <td class="releve-pct"><b class="${pct >= 90 ? 'ok' : pct >= 60 ? 'moyen' : 'bas'}">${pct} %</b><span class="faint"> ${nombre(c.a_jour)} / ${nombre(c.total)}</span>
          <div class="meter"><span style="width:${pct}%"></span></div></td>
        <td>toutes les ${dureeReleve(c.intervalle_h)}</td><td class="hide-sm">${dureeReleve(c.age_median_h)}</td></tr>`;
    }).join('');
    const postes = r.postes.length ? r.postes.map(p => `<li><span class="releve-point ${p.actif ? 'on' : 'off'}"></span>
        <b>${escapeHtml(NOMS_POSTES[p.origine] || p.origine)}</b> : ${p.actif ? 'actif' : 'inactif'}${p.derniere_minutes != null ? `, dernière demande il y a ${dureeReleve(p.derniere_minutes / 60)}` : ''}
        · ${nombre(p.lus_24h)} prix lus en 24 h${p.sans_prix_24h ? ` · ${nombre(p.sans_prix_24h)} pages sans prix` : ''}${p.bloques_24h ? ` · <span class="releve-alerte">${nombre(p.bloques_24h)} vérifications Amazon</span>` : ''}</li>`).join('')
      : '<li class="faint">Ni le programme du PC ni l\'extension n\'ont encore demandé de fiche.</li>';
    const sources = r.sources.length ? r.sources.map(s => `<span class="releve-source ${s.gratuit ? 'gratuit' : ''}">${escapeHtml(s.source)} <b>${nombre(s.lus)}</b></span>`).join('')
      : '<span class="faint">Aucune lecture sur les dernières 24 h.</span>';
    zone.innerHTML = `
      <p class="releve-resume"><b>${nombre(r.lus_24h)}</b> prix lus en 24 h, dont <b>${r.part_gratuite} %</b> gratuitement (PC et extension)
        · <b>${nombre(r.en_retard)}</b> fiche(s) en retard${r.laisses_aux_services ? ` · ${nombre(r.laisses_aux_services)} illisible(s) par le PC, laissée(s) aux services` : ''}</p>
      <table class="list releve-table"><thead><tr><th>Fiches</th><th>À jour</th><th>Rythme actuel</th><th class="hide-sm">Âge médian</th></tr></thead><tbody>${lignes}</tbody></table>
      <div class="releve-bas">
        <div><h4>Postes gratuits</h4><ul class="releve-postes">${postes}</ul></div>
        <div><h4>Lectures sur 24 h par source</h4><div class="releve-sources">${sources}</div>
          <p class="faint releve-capacite">Capacité : services ~${nombre(cap.capacite_services)}/jour + PC ${nombre(cap.lectures_pc_24h)} sur 24 h, pour une demande de ~${nombre(cap.demande_par_jour)}/jour au rythme de base
          → rythme des prioritaires ×${String(cap.facteur_prioritaires ?? 1).replace('.', ',')}, des autres ×${String(cap.facteur ?? 1).replace('.', ',')}
          (en dessous de 1 : plus souvent que prévu ; au-dessus : espacé faute de capacité).</p></div>
      </div>`;
  }
  $('releve-actualiser').addEventListener('click', loadReleve);
  setInterval(() => { if(vueActuelle === 'dashboard' && !document.hidden) loadReleve(); }, 60_000);

  // ---------------------------------------------------------------------
  // Navigation entre les vues
  // ---------------------------------------------------------------------
  function showView(name){
    document.querySelectorAll('[data-section]').forEach(s => { s.hidden = s.dataset.section !== name; });
    document.querySelectorAll('.nav [data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    if(location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    window.scrollTo(0, 0);
    if(name === 'catalog' && !matchMedia('(max-width:980px)').matches) setTimeout(() => $('catalog-search').focus(), 0);
    // Mobile : titre de la section dans la barre du haut, menu refermé.
    const bouton = document.querySelector(`.nav [data-view="${name}"]`);
    if(bouton) $('mobile-titre').textContent = bouton.querySelector('.lbl').textContent;
    basculerMenuMobile(false);
    // Page Serveur : mesures en direct tant qu'elle est affichée.
    vueActuelle = name;
    if(name === 'serveur') demarrerFluxServeur(); else arreterFluxServeur();
  }

  // Menu du mobile : toutes les sections en tuiles, puis les actions (extension,
  // revenus Amazon, voir le site, déconnexion). Construit à partir du menu de
  // gauche de l'ordinateur, pour qu'ils restent toujours identiques.
  function basculerMenuMobile(ouvrir){
    const menu = $('menu-mobile'), fond = $('menu-mobile-fond');
    const ouvert = typeof ouvrir === 'boolean' ? ouvrir : menu.hidden;
    if(ouvert && !$('menu-mobile-sections').childElementCount){
      $('menu-mobile-sections').innerHTML = [...document.querySelectorAll('.side > nav.nav [data-view]')].map(b => {
        const compte = b.querySelector('.count');
        return `<button data-onclick="showView('${b.dataset.view}')" data-vue="${b.dataset.view}">${b.querySelector('i').outerHTML}
          <span>${escapeHtml(b.querySelector('.lbl').textContent)}</span>${compte && compte.textContent ? `<em class="${compte.className}">${escapeHtml(compte.textContent)}</em>` : ''}</button>`;
      }).join('');
      $('menu-mobile-actions').innerHTML = [...document.querySelectorAll('.side-foot button')].map(b => b.outerHTML).join('');
    }
    if(ouvert){
      // Section ouverte en surbrillance, compteurs à jour.
      document.querySelectorAll('#menu-mobile-sections [data-vue]').forEach(t => {
        t.classList.toggle('active', t.dataset.vue === vueActuelle);
        const compte = document.querySelector(`.side > nav.nav [data-view="${t.dataset.vue}"] .count`);
        const em = t.querySelector('em');
        if(em) em.remove();
        if(compte && compte.textContent) t.insertAdjacentHTML('beforeend', `<em class="${compte.className}">${escapeHtml(compte.textContent)}</em>`);
      });
    }
    menu.hidden = fond.hidden = !ouvert;
    $('mobile-plus').setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  }
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && !$('menu-mobile').hidden) basculerMenuMobile(false); });

  // ---------------------------------------------------------------------
  // Tableau de bord
  // ---------------------------------------------------------------------
  let statsData = null;
  let quotas = null;

  function renderDashboard(){
    const enStock = components.filter(c => c.en_stock !== false).length;
    const produits = new Set(components.map(c => c.groupe_id ?? c.id)).size;
    const suspects = watchData ? watchData.prix_suspects.length : 0;
    const aRattacher = watchData ? watchData.annonces_isolees.length : 0;
    const bd = quotas && quotas.brightdata;
    const kpi = (label, value, hint, cls = '', view = '') => `
      <${view ? `button class="kpi ${cls}" data-onclick="showView('${view}')"` : `div class="kpi ${cls}"`}>
        <span class="label">${label}</span><span class="value">${value}</span>${hint ? `<span class="hint">${hint}</span>` : ''}
      </${view ? 'button' : 'div'}>`;
    $('dash-kpis').innerHTML = [
      kpi('Appareils différents sur 7 jours', statsData ? nombre(statsData.semaine.visiteurs) : '—',
          statsData ? `${nombre(statsData.jours[statsData.jours.length - 1].visiteurs)} aujourd'hui` : '', '', 'stats'),
      kpi('Pages vues sur 7 jours', statsData ? nombre(statsData.semaine.pages_vues) : '—', '', '', 'stats'),
      kpi('Produits au catalogue', nombre(produits), `${nombre(components.length)} annonces, ${nombre(enStock)} en stock`, '', 'catalog'),
      kpi('Prix suspects', nombre(suspects), aRattacher ? `${aRattacher} annonce${aRattacher > 1 ? 's' : ''} à rattacher` : 'aucune annonce à rattacher',
          suspects ? 'is-alert' : 'is-ok', 'watch'),
      kpi('Fiches incomplètes', watchData ? nombre(watchData.fiches_incompletes.length) : '—', 'champs de compatibilité manquants', '', 'watch'),
      bd ? `<div class="kpi"><span class="label">Bright Data ce mois-ci</span><span class="value">${nombre(bd.utilise)}<span class="faint"> / ${nombre(bd.quota)}</span></span>
            <div class="meter"><span style="width:${Math.min(100, Math.round(bd.utilise / bd.quota * 100))}%"></span></div>
            <span class="hint">${nombre(bd.ajouts_restants)} ajouts encore possibles</span></div>`
         : kpi('Bright Data ce mois-ci', '—', ''),
      (() => {
        // Bilan du dernier passage automatique des prix (4 par jour : 2 h, 8 h, 14 h, 20 h).
        const p = quotas && quotas.dernier_passage;
        if(!p) return kpi('Mise à jour des prix', '—', 'pas encore de bilan');
        const quand = new Date(p.date + 'Z').toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        if(p.prix_lus == null){
          return kpi('Mise à jour des prix', nombre(p.mis_a_jour),
            `prix revérifiés le ${quand} · ${nombre(p.erreurs)} non lus${p.passes_epuises ? ` · ${nombre(p.passes_epuises)} épuisés` : ''}`,
            p.mis_a_jour ? 'is-ok' : 'is-alert');
        }
        // Les fiches bloquées par Amazon sont reprises par Bright Data / ZenRows dans le
        // même passage si leur quota le permet ; les autres passent en premier au suivant.
        const s = p.en_stock || {};
        const details = [`relus le ${quand}`];
        if(s.prioritaires) details.push(`${nombre(s.prioritaires_aujourd_hui)} / ${nombre(s.prioritaires)} produits prioritaires (les plus achetables) à jour du jour`);
        if(s.total) details.push(`${nombre(s.moins_de_3_jours)} / ${nombre(s.total)} fiches en stock vérifiées depuis moins de 3 jours`);
        if(p.alertes) details.push(`${nombre(p.alertes)} produits suivis par une alerte relus en premier`);
        if(p.bloques) details.push(`${nombre(p.bloques)} bloqués chez Apify${p.repris != null ? `, dont ${nombre(p.repris)} repris par un autre service` : ''}`);
        const secours = Object.entries(p.secours || {}).filter(([, n]) => n);
        if(secours.length){
          const noms = { scraperapi: 'ScraperAPI', scrapingant: 'ScrapingAnt', scrapedo: 'Scrape.do' };
          details.push('lus en secours : ' + secours.map(([k, n]) => `${nombre(n)} via ${noms[k] || k}`).join(', '));
        }
        if(p.reportes) details.push(`${nombre(p.reportes)} reportés`);
        if(p.passes_epuises) details.push(`${nombre(p.passes_epuises)} passés épuisés`);
        details.push('les non lus passent en priorité au passage suivant');
        return kpi('Prix relus au dernier passage', nombre(p.prix_lus), details.join(' · '), p.prix_lus ? 'is-ok' : 'is-alert');
      })(),
      (() => {
        // Capacité de lecture des prix : ce que chaque service peut lire par jour
        // jusqu'au renouvellement de ses crédits gratuits.
        const c = quotas && quotas.capacite;
        if(!c || !c.services || !c.services.length) return '';
        const lignes = c.services.map(s => s.erreur
          ? `${escapeHtml(s.nom)} : illisible`
          : `${escapeHtml(s.nom)} ${nombre(s.par_jour)}/j${s.reste ? ` (${escapeHtml(s.reste)}${s.jours ? `, ${nombre(s.jours)} j` : ''})` : ''}`);
        const ext = quotas.extension || {};
        if(ext.date === new Date().toISOString().slice(0, 10)){
          lignes.push(`extension du navigateur : ${nombre(ext.lus || 0)} lus aujourd'hui${ext.bloques ? `, ${nombre(ext.bloques)} vérifications Amazon` : ''}`);
        }
        return kpi('Fiches lisibles par jour', nombre(c.total_par_jour), lignes.join(' · '), c.total_par_jour ? 'is-ok' : 'is-alert');
      })(),
    ].join('');

    // « À traiter » : les signalements qui demandent une décision, avec leurs actions.
    const todo = [];
    ticketsOuverts().slice(0, 4).forEach(t => todo.push(ticketTodoItem(t)));
    if(watchData){
      watchData.prix_suspects.slice(0, 5).forEach(s => todo.push(priceItem(s)));
      watchData.annonces_isolees.slice(0, 3).forEach(p => todo.push(isolatedItem(p)));
    }
    $('dash-todo').innerHTML = todo.join('') || '<p class="empty">Rien à traiter. Le catalogue est propre.</p>';

    const setCount = (id, n, alert) => { const el = $(id); el.textContent = n ? String(n) : ''; el.classList.toggle('alert', !!alert && n > 0); };
    setCount('nav-watch', suspects + aRattacher, true);
    setCount('nav-tickets', ticketsOuverts().length, true);
    setCount('nav-catalog', components.length, false);
  }

  // ---------------------------------------------------------------------
  // À surveiller
  // ---------------------------------------------------------------------
  async function loadWatch(){
    try{
      watchData = await api('/api/admin/controle-catalogue');
      const counts = { prix: watchData.prix_suspects.length, isolees: watchData.annonces_isolees.length,
        incompletes: watchData.fiches_incompletes.length, auto: (watchData.corrections_auto || []).length };
      const labels = { prix: 'Prix suspects', isolees: 'Annonces à rattacher', incompletes: 'Fiches incomplètes', auto: 'Corrigé automatiquement' };
      Object.entries(counts).forEach(([k, n]) => { $('watch-tab-' + k).innerHTML = `${labels[k]}<span class="n">${n}</span>`; });
      renderWatch();
    }catch(e){
      $('watch-content').innerHTML = '<p class="empty">Contrôle indisponible pour le moment.</p>';
    }
  }

  function showWatchTab(tab){
    watchTab = tab;
    renderWatch();
  }

  function priceItem(s){
    return `<div class="item">
      <div><div class="t">${escapeHtml(s.nom)}</div>
        <div class="why"><b>${euros(s.prix)}</b> au lieu d'environ ${euros(s.reference)} · ${escapeHtml(s.motif)}</div>
        <div class="why conseil">${(s.ratio || 0) >= 3 || /moins cher/.test(s.motif)
          ? 'Conseil : supprimer l’annonce (prix aberrant ou autre article que celui indiqué).'
          : 'Conseil : ouvrir l’annonce pour vérifier le prix sur Amazon, puis « Prix normal » s’il est juste.'}</div></div>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" data-onclick="openComponent(${s.id})">Ouvrir</button>
        <button class="btn btn-danger btn-sm" data-onclick="deleteComponent(${s.id})">Supprimer</button>
        <button class="btn btn-secondary btn-sm" data-onclick="ignoreWatch('prix:${s.id}:${s.prix}')">Prix normal</button>
      </div></div>`;
  }

  function isolatedItem(p){
    const cle = `isolee:${Math.min(p.id, p.proche_id)}:${Math.max(p.id, p.proche_id)}`;
    return `<div class="item">
      <div><div class="t">${escapeHtml(p.nom)}</div>
        <div class="why">Ressemble à ${escapeHtml(p.proche_nom)}${p.proche_variantes > 1 ? ` (${p.proche_variantes} variantes)` : ''}. Même produit ?</div></div>
      <div class="actions">
        <button class="btn btn-primary btn-sm" data-onclick="attachVariant(${p.id}, ${p.proche_id})">Oui, en faire une variante</button>
        <button class="btn btn-secondary btn-sm" data-onclick="ignoreWatch('${cle}')">Non</button>
      </div></div>`;
  }

  function renderWatch(){
    document.querySelectorAll('[data-section="watch"] .tabs button').forEach(b => b.classList.toggle('active', b.id === 'watch-tab-' + watchTab));
    if(!watchData) return;
    let html;
    if(watchTab === 'prix'){
      html = watchData.prix_suspects.map(priceItem).join('') || '<p class="empty">Aucun prix suspect.</p>';
    }else if(watchTab === 'auto'){
      const icone = { fiche: 'ph-note-pencil', rattachement: 'ph-link-simple', prix: 'ph-tag' };
      html = (watchData.corrections_auto || []).map(e => `<div class="item">
        <div><div class="t"><i class="ph ${icone[e.type] || 'ph-check'}"></i> ${escapeHtml(e.nom)}</div>
          <div class="why">${escapeHtml(e.detail)} <span class="faint">· ${new Date(e.date + 'Z').toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span></div></div>
        <div class="actions">
          ${e.type === 'rattachement' ? `<button class="btn btn-secondary btn-sm" data-onclick="separateById(${e.id})">Annuler (séparer)</button>` : ''}
          <button class="btn btn-ghost btn-sm" data-onclick="openComponent(${e.id})">Ouvrir</button></div>
      </div>`).join('') || '<p class="empty">Aucune correction automatique pour l’instant.</p>';
    }else if(watchTab === 'isolees'){
      html = watchData.annonces_isolees.map(isolatedItem).join('') || '<p class="empty">Aucune annonce à rattacher.</p>';
    }else{
      html = watchData.fiches_incompletes.map(f => {
        const sug = Object.entries(f.suggestions || {});
        return `<div class="item">
        <div><div class="t">${escapeHtml(f.nom)} <span class="faint">· ${escapeHtml(f.categorie)}</span></div>
          <div class="why">${f.manques.map(m => `<span class="tag">${escapeHtml(FIELD_LABELS[m] || m)}</span>`).join('')}</div>
          ${sug.length ? `<div class="why conseil">Suggestion : ${sug.map(([k, v]) => `<b>${escapeHtml(FIELD_LABELS[k] || k)} = ${escapeHtml(Array.isArray(v.valeur) ? v.valeur.join(', ') : v.valeur)}</b> <span class="faint">(${escapeHtml(v.source)})</span>`).join(' · ')}</div>` : ''}</div>
        <div class="actions">
          ${sug.length ? `<button class="btn btn-primary btn-sm" data-onclick="applySuggestions(${f.id})">Appliquer la suggestion</button>` : ''}
          <button class="btn btn-secondary btn-sm" data-onclick="openComponent(${f.id})">Compléter à la main</button></div>
      </div>`;
      }).join('') || '<p class="empty">Toutes les fiches sont complètes.</p>';
    }
    $('watch-content').innerHTML = html;
  }

  async function applySuggestions(id){
    const f = (watchData.fiches_incompletes || []).find(x => x.id === id);
    if(!f || !f.suggestions) return;
    const champs = Object.fromEntries(Object.entries(f.suggestions).map(([k, v]) => [k, v.valeur]));
    try{
      await post(`/api/admin/components/${id}/completer`, { champs });
      toast('Suggestion appliquée.');
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  async function separateById(id){
    if(!await uiConfirm('Cette annonce redeviendra un produit à part.', { title: 'Annuler le rattachement ?', confirmLabel: 'Séparer' })) return;
    try{
      await post('/api/admin/variantes/separer', { id });
      toast('Annonce séparée.');
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  async function ignoreWatch(cle){
    try{ await post('/api/admin/controle/ignorer', { cle }); toast('Signalement ignoré.'); await refreshAll(); }
    catch(e){ toast(e.message, true); }
  }

  async function attachVariant(id, cible){
    try{ await post('/api/admin/variantes/rattacher', { id, cible }); toast('Rattaché comme variante.'); await refreshAll(); }
    catch(e){ toast(e.message, true); }
  }

  // ---------------------------------------------------------------------
  // Catalogue
  // ---------------------------------------------------------------------
  async function loadComponents(){
    try{
      const data = await api('/api/admin/components');
      components = Object.values(data.components || {}).flat();
      $('spec-keys').innerHTML = [...new Set(components.flatMap(c => Object.keys(parseSpecs(c))))].sort()
        .map(k => `<option value="${escapeHtml(k)}">`).join('');
      renderCatalog();
    }catch(e){
      $('catalog-rows').innerHTML = `<tr><td colspan="5" class="empty">Catalogue indisponible : ${escapeHtml(e.message)}</td></tr>`;
    }
  }

  function parseSpecs(c){
    if(c.specs && typeof c.specs === 'object') return c.specs;
    try{ return JSON.parse(c.specs_json || '{}') || {}; }catch(e){ return {}; }
  }

  function filteredComponents(){
    const brut = $('catalog-search').value.trim();
    // Un ASIN ou un numéro de fiche : recherche exacte. Sinon, recherche
    // tolérante (static/recherche.js) : fautes, mots collés, abréviations.
    const exact = /^(b0[a-z0-9]{8}|\d+)$/i.test(brut);
    const q = exact ? [norm(brut)] : [];
    const scores = new Map();
    const cat = $('catalog-category').value;
    const f = $('catalog-filter').value;
    return components.filter(c => {
      if(cat && c.categorie !== cat) return false;
      if(f === 'stock' && c.en_stock === false) return false;
      if(f === 'epuise' && c.en_stock !== false) return false;
      if(f === 'suspect' && !c.prix_suspect) return false;
      if(f === 'variantes' && !(c.nb_variantes > 1)) return false;
      if(f === 'sans-image' && c.image_url) return false;
      if(q.length){
        const hay = norm(`${c.nom} ${c.asin || ''} ${c.id}`);
        if(!q.every(t => hay.includes(t))) return false;
      }else if(brut && window.pcrRecherche){
        const sc = pcrRecherche.score(brut, c);
        if(!sc) return false;
        scores.set(c, sc);
      }
      return true;
    }).sort((a, b) => (scores.get(b) || 0) - (scores.get(a) || 0)
      || a.categorie.localeCompare(b.categorie) || a.nom.localeCompare(b.nom));
  }

  function renderCatalog(){
    const list = filteredComponents();
    $('catalog-summary').textContent = `${nombre(list.length)} annonce${list.length > 1 ? 's' : ''} affichée${list.length > 1 ? 's' : ''} sur ${nombre(components.length)}`;
    $('catalog-rows').innerHTML = list.slice(0, rowsShown).map(c => {
      const thumb = c.image_url
        ? `<div class="thumb${String(c.image_url).startsWith('data:') ? ' transparent' : ''}"><img src="/api/components/${c.id}/image?w=80" alt="" loading="lazy"></div>`
        : '<div class="thumb none"><i class="ph ph-image"></i></div>';
      const tags = [
        c.en_stock === false ? '<span class="tag">Épuisé</span>' : '<span class="tag ok">En stock</span>',
        c.prix_suspect ? '<span class="tag danger">Prix suspect</span>' : '',
      ].join('');
      return `<tr class="${editing && editing.id === c.id ? 'active' : ''}" data-onclick="openComponent(${c.id})">
        <td>${thumb}</td>
        <td><div class="name">${escapeHtml(c.nom)}</div>${c.nb_variantes > 1 ? `<div class="faint">${escapeHtml(c.variante || '')} · ${c.nb_variantes} variantes</div>` : ''}</td>
        <td class="hide-sm muted">${escapeHtml(c.categorie)}</td>
        <td class="num">${c.prix_indicatif ? euros(c.prix_indicatif) : '<span class="muted">—</span>'}</td>
        <td class="hide-sm">${tags}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5" class="empty" style="padding:18px 12px;">Aucun produit ne correspond.</td></tr>';
    $('catalog-more').hidden = list.length <= rowsShown;
  }

  function showMoreRows(){ rowsShown += 300; renderCatalog(); }

  // ---------------------------------------------------------------------
  // Tiroir d'édition
  // ---------------------------------------------------------------------
  function openDrawer(){
    $('drawer').hidden = false;
    $('drawer-backdrop').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer(){
    $('drawer').hidden = true;
    $('drawer-backdrop').hidden = true;
    document.body.style.overflow = '';
    editing = null;
    renderCatalog();
  }

  function setNote(text, kind){
    const el = $('drawer-note');
    if(!text){ el.hidden = true; return; }
    el.className = 'note' + (kind ? ' ' + kind : '');
    el.textContent = text;
    el.hidden = false;
  }

  function openComponent(id){
    const c = components.find(x => x.id === id);
    if(!c){ toast('Produit introuvable (peut-être supprimé).', true); return; }
    editing = c;
    currentAmazonDetails = c.caracteristiques_amazon || [];
    currentAmazonDescription = c.description || null;
    $('drawer-title').textContent = c.nom;
    $('drawer-page').hidden = !c.page;
    if(c.page) $('drawer-page').href = c.page;
    $('f-nom').value = c.nom;
    $('f-categorie').value = c.categorie;
    $('f-prix').value = c.prix_indicatif ?? '';
    $('f-asin').value = c.asin || '';
    $('f-image').value = c.image_url || '';
    $('f-specs').innerHTML = '';
    Object.entries(parseSpecs(c)).forEach(([k, v]) => addSpecRow(k, Array.isArray(v) ? v.join(', ') : v));
    $('f-prices').innerHTML = '';
    (c.prix_marche || []).forEach(p => addPriceRow(p));
    $('f-delete').hidden = false;
    $('f-regen').hidden = !c.asin;
    $('f-separate').hidden = !(c.nb_variantes > 1);
    const notes = [];
    if(c.nb_variantes > 1) notes.push(`Variante « ${c.variante || ''} » d'un produit à ${c.nb_variantes} annonces.`);
    if(c.prix_suspect) notes.push('Prix signalé suspect par le contrôle du catalogue.');
    setNote(notes.join(' '), c.prix_suspect ? 'error' : '');
    renderRequiredHint();
    updatePreview();
    openDrawer();
    renderCatalog();
  }

  function openNewComponent(){
    editing = null;
    currentAmazonDetails = [];
    currentAmazonDescription = null;
    $('drawer-title').textContent = 'Nouveau composant';
    $('drawer-page').hidden = true;
    ['f-nom', 'f-prix', 'f-asin', 'f-image'].forEach(id => { $(id).value = ''; });
    $('f-categorie').value = $('catalog-category').value || 'CPU';
    $('f-specs').innerHTML = '';
    $('f-prices').innerHTML = '';
    $('f-delete').hidden = true;
    $('f-regen').hidden = true;
    $('f-separate').hidden = true;
    setNote('Astuce : renseigne l\'ASIN puis « Reprendre depuis Amazon » pour tout remplir automatiquement.');
    renderRequiredHint();
    updatePreview();
    openDrawer();
  }

  // Ajoute les champs de compatibilité manquants de la catégorie (vides, à remplir).
  function renderRequiredHint(){
    const required = Object.keys(REQUIRED_FIELDS[$('f-categorie').value] || {});
    const present = new Set([...document.querySelectorAll('#f-specs .s-key')].map(i => i.value.trim()));
    required.filter(k => !present.has(k)).forEach(k => addSpecRow(k, ''));
    document.querySelectorAll('#f-specs .kv-row').forEach(row => {
      row.classList.toggle('required', required.includes(row.querySelector('.s-key').value.trim()));
    });
    $('f-required').textContent = required.length
      ? 'En vert : champs utilisés par le contrôle de compatibilité (' + required.map(k => FIELD_LABELS[k] || k).join(', ') + ').'
      : 'Aucun champ obligatoire pour cette catégorie.';
  }

  function addSpecRow(key, value){
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.innerHTML = `<input type="text" class="s-key" list="spec-keys" placeholder="champ (ex : socket)" value="${escapeHtml(key)}">
      <input type="text" class="s-value" placeholder="valeur (liste : a, b, c)" value="${escapeHtml(value)}">
      <button class="icon-btn" data-onclick="this.parentElement.remove()" title="Retirer"><i class="ph ph-x"></i></button>`;
    $('f-specs').appendChild(row);
  }

  function addPriceRow(p){
    const row = document.createElement('div');
    row.className = 'price-row';
    row.dataset.date = p?.date_releve || '';
    row.innerHTML = `<input type="text" class="p-vendeur" placeholder="Marchand" value="${escapeHtml(p?.vendeur || '')}">
      <input type="number" class="p-prix mono" step="0.01" placeholder="Prix" value="${p?.prix ?? ''}">
      <input type="text" class="p-lien" placeholder="Lien" value="${escapeHtml(p?.lien || '')}">
      <button class="icon-btn" data-onclick="this.parentElement.remove()" title="Retirer"><i class="ph ph-x"></i></button>`;
    $('f-prices').appendChild(row);
  }

  function updatePreview(){
    const url = $('f-image').value.trim();
    const box = $('f-preview');
    box.classList.toggle('transparent', url.startsWith('data:'));
    box.innerHTML = url ? `<img src="${escapeHtml(url)}" alt="">` : '<i class="ph ph-image muted"></i>';
  }

  function parseSpecValue(raw, type){
    const v = (raw || '').trim();
    if(v === '') return '';
    if(type === 'number'){ const m = v.match(/-?\d+(\.\d+)?/); return m ? Number(m[0]) : v; }
    if(type === 'list' || v.includes(',')) return v.split(',').map(x => x.trim()).filter(Boolean);
    if(type !== 'str' && !isNaN(v)) return Number(v);
    return v;
  }

  async function saveComponent(){
    const categorie = $('f-categorie').value;
    const types = REQUIRED_FIELDS[categorie] || {};
    const specs = {};
    document.querySelectorAll('#f-specs .kv-row').forEach(row => {
      const key = row.querySelector('.s-key').value.trim();
      const value = parseSpecValue(row.querySelector('.s-value').value, types[key]);
      if(key && value !== '') specs[key] = value;
    });
    // lien_mort / dernier_check (vérification automatique) gardés tant que le lien ne change pas.
    const original = {};
    (editing?.prix_marche || []).forEach(p => { original[p.vendeur] = p; });
    const today = new Date().toISOString().slice(0, 10);
    const prix_marche = [...document.querySelectorAll('#f-prices .price-row')].map(row => {
      const vendeur = row.querySelector('.p-vendeur').value.trim();
      const lien = row.querySelector('.p-lien').value.trim();
      const prix = Number(row.querySelector('.p-prix').value);
      const o = original[vendeur];
      const entry = { vendeur, prix, lien, date_releve: (o && o.prix === prix && row.dataset.date) || today };
      if(o && o.lien === lien){
        if('lien_mort' in o) entry.lien_mort = o.lien_mort;
        if('dernier_check' in o) entry.dernier_check = o.dernier_check;
      }
      return entry;
    }).filter(p => p.vendeur && p.lien);
    const prixRaw = $('f-prix').value;
    const payload = {
      categorie, nom: $('f-nom').value.trim(), prix_indicatif: prixRaw === '' ? null : Number(prixRaw),
      specs, prix_marche, image_url: $('f-image').value.trim() || null, asin: $('f-asin').value.trim() || null,
      caracteristiques_amazon: currentAmazonDetails, description: currentAmazonDescription,
    };
    $('f-save').disabled = true;
    try{
      if(editing){
        await api(`/api/admin/components/${editing.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      }else{
        await post('/api/admin/components', { components: [payload] });
      }
      toast('Enregistré.');
      const id = editing?.id;
      await loadComponents();
      const saved = id ? components.find(c => c.id === id) : components.find(c => c.categorie === categorie && c.nom === payload.nom);
      if(saved) openComponent(saved.id);
      loadWatch().then(renderDashboard);
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-save').disabled = false;
    }
  }

  async function deleteComponent(id){
    const c = components.find(x => x.id === id);
    if(!await uiConfirm(`« ${c ? c.nom : id} » sera retiré du catalogue. Les configurations qui l'utilisent le perdront.`,
      { title: 'Supprimer ce composant ?', confirmLabel: 'Supprimer', danger: true })) return;
    try{
      await api(`/api/admin/components/${id}`, { method: 'DELETE' });
      toast('Supprimé.');
      if(editing && editing.id === id) closeDrawer();
      await refreshAll();
    }catch(e){ toast(e.message, true); }
  }

  function deleteCurrent(){ if(editing) deleteComponent(editing.id); }

  async function separateCurrent(){
    if(!editing || !await uiConfirm(`« ${editing.nom} » redevient une fiche à part.`,
      { title: 'Sortir de ce produit ?', confirmLabel: 'Séparer' })) return;
    try{
      await post('/api/admin/variantes/separer', { id: editing.id });
      toast('Séparé de ses variantes.');
      const id = editing.id;
      await refreshAll();
      openComponent(id);
    }catch(e){ toast(e.message, true); }
  }

  // Reprend nom (si vide), prix, image et caractéristiques depuis Amazon ; rien n'est
  // enregistré tant que « Enregistrer » n'est pas cliqué.
  async function refetchFromAmazon(){
    const asin = $('f-asin').value.trim();
    if(!asin){ setNote('Renseigne d\'abord l\'ASIN (ou colle un lien Amazon).', 'error'); return; }
    const categorie = $('f-categorie').value;
    $('f-refetch').disabled = true;
    setNote('Récupération depuis Amazon…');
    try{
      const d = await post('/api/admin/fetch-asin', { asin, categorie });
      $('f-asin').value = d.asin;
      if(!$('f-nom').value.trim() && d.nom) $('f-nom').value = d.nom;
      if(d.prix != null) $('f-prix').value = d.prix;
      if(d.image_url){ $('f-image').value = d.image_url; updatePreview(); }
      if(d.prix != null && d.lien){
        document.querySelectorAll('#f-prices .price-row').forEach(r => { if(r.querySelector('.p-vendeur').value.trim() === 'Amazon') r.remove(); });
        addPriceRow({ vendeur: 'Amazon', prix: d.prix, lien: d.lien, date_releve: new Date().toISOString().slice(0, 10) });
      }
      const present = {};
      document.querySelectorAll('#f-specs .kv-row').forEach(r => { present[r.querySelector('.s-key').value.trim()] = r; });
      Object.entries(d.specs || {}).forEach(([k, v]) => {
        if(v === null || v === undefined || v === '') return;
        const val = Array.isArray(v) ? v.join(', ') : v;
        if(present[k]){ if(!present[k].querySelector('.s-value').value.trim()) present[k].querySelector('.s-value').value = val; }
        else addSpecRow(k, val);
      });
      currentAmazonDetails = Array.isArray(d.caracteristiques_amazon) ? d.caracteristiques_amazon : currentAmazonDetails;
      currentAmazonDescription = d.description || currentAmazonDescription;
      renderRequiredHint();
      setNote('Données Amazon reprises. Vérifie puis clique « Enregistrer ».', 'ok');
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-refetch').disabled = false;
    }
  }

  // Nouvelle photo Amazon pour cet ASIN (enregistrée tout de suite, détourée ensuite
  // automatiquement par la surveillance locale).
  async function regenerateImage(){
    if(!editing) return;
    $('f-regen').disabled = true;
    try{
      const d = await post(`/api/admin/components/${editing.id}/regenerate-image`);
      $('f-image').value = d.image_url;
      updatePreview();
      setNote('Nouvelle photo enregistrée. Elle sera détourée automatiquement d\'ici une vingtaine de secondes.', 'ok');
      loadComponents();
    }catch(e){
      setNote(e.message, 'error');
    }finally{
      $('f-regen').disabled = false;
    }
  }

  async function loadQuotas(){
    try{
      quotas = await api('/api/admin/quotas');
    }catch(e){ quotas = null; }
  }

  // ---------------------------------------------------------------------
  // Statistiques
  // ---------------------------------------------------------------------
  async function loadStats(){
    try{
      statsData = await api('/api/admin/stats');
      renderStats();
    }catch(e){
      statsData = null;
      $('stats-content').innerHTML = '<p class="empty">Statistiques indisponibles pour le moment.</p>';
    }
  }

  // Graduation « ronde » au-dessus du maximum (10, 20, 50, 100, 200…).
  function niceMax(v){
    if(v <= 4) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const step = [1, 2, 2.5, 5, 10].find(s => s * p * 4 >= v) * p;
    return step * 4;
  }

  function renderStats(){
    const s = statsData;
    const jours = s.jours;
    const today = jours[jours.length - 1];
    const moyenne = Math.round(jours.slice(-7).reduce((a, j) => a + j.visiteurs, 0) / 7);
    const visites = s.semaine.visites ?? jours.slice(-7).reduce((a, j) => a + j.visiteurs, 0);
    const revenus = Math.max(0, visites - s.semaine.visiteurs);
    const max = niceMax(Math.max(1, ...jours.map(j => j.visiteurs)));
    const axis = [4, 3, 2, 1, 0].map(i => `<span>${nombre(max * i / 4)}</span>`).join('');
    const bars = jours.map((j, i) => `
      <div class="bar${i === jours.length - 1 ? ' is-today' : ''}" title="${new Date(j.date).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })} : ${j.visiteurs} appareils, ${j.pages_vues} pages vues">
        <div class="fill" style="height:calc((100% - 22px) * ${j.visiteurs / max})"></div>
        <small>${j.date.slice(8, 10)}</small>
      </div>`).join('');
    const rank = (rows, label, value) => {
      if(!rows.length) return '<p class="empty">Pas encore de données.</p>';
      const top = Math.max(...rows.map(r => r[value]));
      return `<ul class="rank">${rows.map(r => `<li><div class="bg" style="width:${Math.round(r[value] / top * 100)}%"></div>
        <span title="${escapeHtml(r[label])}">${escapeHtml(r[label])}</span><b>${nombre(r[value])}</b></li>`).join('')}</ul>`;
    };
    // Liens de partage (pcradar.tech/tiktok, /insta...) : clics et visiteurs réels.
    const L = s.liens || [];
    const cellule = p => `<td class="num"><b>${nombre(p.visiteurs)}</b><span class="faint"> / ${nombre(p.clics)}</span></td>`;
    const liensPanel = L.length ? `
      <div class="panel">
        <div class="panel-head"><h3>Liens de partage</h3><span class="faint">visiteurs / clics</span></div>
        <div class="table-wrap" style="overflow-x:auto;"><table class="list liens-table">
          <thead><tr><th>Réseau</th><th>Lien</th><th class="num">Aujourd'hui</th><th class="num">7 jours</th><th class="num">Total</th></tr></thead>
          <tbody>${L.map(l => `<tr>
            <td>${escapeHtml(l.source)}</td>
            <td><button class="btn btn-ghost btn-sm" data-onclick="copyLink('${jsArg(l.lien)}')" title="Copier le lien"><i class="ph ph-copy"></i>${escapeHtml(l.lien.replace('https://', ''))}</button></td>
            ${cellule(l.aujourdhui)}${cellule(l.semaine)}${cellule(l.total)}</tr>`).join('')}</tbody>
        </table></div>
        <p class="faint" style="margin-top:10px;font-size:0.82rem;">Clics : ouvertures du lien. Visiteurs : personnes qui ont ensuite vraiment utilisé le site (robots et toi exclus).</p>
      </div>` : '';
    // Assistant IA : de la discussion jusqu'au panier Amazon.
    const A = s.assistant;
    const LIGNES_ASSISTANT = [
      ['discussion', 'Discussions commencées'], ['message', 'Messages envoyés'],
      ['guide_debut', 'Parcours « Je débute » commencés'], ['guide_fini', 'Parcours « Je débute » terminés'],
      ['config', 'Configs proposées'], ['ajout', 'Composants ajoutés un par un'],
      ['tout_ajouter', 'Configs ajoutées en entier'], ['amazon', 'Paniers Amazon ouverts'], ['partage', 'Configs partagées'],
    ];
    const assistantPanel = A ? `
      <div class="panel">
        <div class="panel-head"><h3>Assistant IA</h3><span class="faint">de la discussion au panier</span></div>
        <div class="table-wrap" style="overflow-x:auto;"><table class="list liens-table">
          <thead><tr><th>Étape</th><th class="num">Aujourd'hui</th><th class="num">7 jours</th><th class="num">Total</th></tr></thead>
          <tbody>${LIGNES_ASSISTANT.map(([cle, libelle]) => { const v = A[cle] || { jour: 0, semaine: 0, total: 0 }; return `<tr>
            <td>${libelle}</td><td class="num"><b>${nombre(v.jour)}</b></td><td class="num">${nombre(v.semaine)}</td><td class="num">${nombre(v.total)}</td></tr>`; }).join('')}</tbody>
        </table></div>
      </div>` : '';
    // Totaux depuis le premier jour archivé (voir _archiver_stats côté serveur).
    const T = s.total;
    const dateLongue = d => new Date(d).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    const totalApp = T ? Object.values(T.appareils).reduce((a, b) => a + b, 0) : 0;
    const partMobile = totalApp ? Math.round((T.appareils.Mobile || 0) / totalApp * 100) : 0;
    const totaux = T ? `
      <div class="panel">
        <div class="panel-head"><h3>Total depuis le ${dateLongue(T.depuis)}</h3><span class="faint">${nombre(T.jours)} jour${T.jours > 1 ? 's' : ''}</span></div>
        <div class="kpis" style="margin:0 0 16px;">
          <div class="kpi"><span class="label">Visites au total</span><span class="value">${nombre(T.visites)}</span><span class="hint">${nombre(Math.round(T.visites / Math.max(1, T.jours)))} par jour en moyenne</span></div>
          <div class="kpi"><span class="label">Pages vues au total</span><span class="value">${nombre(T.pages_vues)}</span><span class="hint">${(T.visites ? T.pages_vues / T.visites : 0).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} pages par visite</span></div>
          <div class="kpi"><span class="label">Meilleur jour</span><span class="value">${nombre(T.meilleur_jour.visiteurs)}</span><span class="hint">${T.meilleur_jour.date ? dateLongue(T.meilleur_jour.date) : '—'}</span></div>
          <div class="kpi"><span class="label">Sur téléphone</span><span class="value">${partMobile} %</span><span class="hint">${100 - partMobile} % sur ordinateur</span></div>
        </div>
        <div class="grid-2">
          <div><div class="panel-head" style="margin:0;"><h3>Pages les plus vues</h3><span class="faint">au total</span></div>${rank(T.pages, 'page', 'vues')}</div>
          <div><div class="panel-head" style="margin:0;"><h3>Provenance</h3><span class="faint">au total</span></div>${rank(T.provenance, 'source', 'visites')}</div>
        </div>
      </div>` : '';
    const total = Object.values(s.appareils).reduce((a, b) => a + b, 0) || 1;
    const shades = ['var(--accent)', '#2a9d6b', 'var(--line-strong)', 'var(--text-3)'];
    const devices = Object.entries(s.appareils).sort((a, b) => b[1] - a[1]);
    $('stats-content').innerHTML = `
      <div class="kpis">
        <div class="kpi"><span class="label">Appareils différents aujourd'hui</span><span class="value">${nombre(today.visiteurs)}</span><span class="hint">${nombre(today.pages_vues)} pages vues</span></div>
        <div class="kpi"><span class="label">Appareils différents sur 7 jours</span><span class="value">${nombre(s.semaine.visiteurs)}</span><span class="hint">${nombre(moyenne)} par jour · ${nombre(revenus)} retour${revenus > 1 ? 's' : ''}</span></div>
        <div class="kpi"><span class="label">Appareils différents sur 14 jours</span><span class="value">${nombre(s.quinzaine ? s.quinzaine.visiteurs : 0)}</span><span class="hint">meilleur jour : ${nombre(Math.max(...jours.map(j => j.visiteurs)))}</span></div>
        <div class="kpi"><span class="label">Pages vues sur 7 jours</span><span class="value">${nombre(s.semaine.pages_vues)}</span><span class="hint">${(s.semaine.visiteurs ? s.semaine.pages_vues / s.semaine.visiteurs : 0).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} pages par appareil</span></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>Appareils différents par jour</h3><div class="legend"><span><i style="background:var(--accent)"></i>Téléphones et ordinateurs distincts</span></div></div>
        <div class="chart"><div class="chart-axis">${axis}</div><div class="chart-bars">${bars}</div></div>
      </div>
      <div class="grid-2">
        <div class="panel" style="margin:0;"><div class="panel-head"><h3>Pages les plus vues</h3><span class="faint">7 jours</span></div>${rank(s.pages, 'page', 'vues')}</div>
        <div class="panel" style="margin:0;">
          <div class="panel-head"><h3>Provenance</h3><span class="faint">7 jours</span></div>${rank(s.provenance, 'source', 'visites')}
          <div class="panel-head" style="margin:18px 0 0;"><h3>Appareils</h3><span class="faint">7 jours</span></div>
          <div class="devices">${devices.map(([k, v], i) => `<span style="width:${v / total * 100}%; background:${shades[i % shades.length]}" title="${escapeHtml(k)}"></span>`).join('')}</div>
          <div class="devices-legend">${devices.map(([k, v], i) => `<span><i style="background:${shades[i % shades.length]}"></i>${escapeHtml(k)} ${Math.round(v / total * 100)} %</span>`).join('') || '<span>—</span>'}</div>
        </div>
      </div>
      ${assistantPanel}
      ${liensPanel}
      ${totaux}`;
  }

  // ---------------------------------------------------------------------
  // Tickets (bulle d'aide du site)
  // ---------------------------------------------------------------------
  let tickets = [];
  let ticketsTab = 'ouverts';
  const STATUTS_TICKET = { ouvert: 'Nouveau', en_cours: 'En cours', resolu: 'Résolu' };
  const ticketsOuverts = () => tickets.filter(t => t.statut !== 'resolu');
  const dateTicket = d => new Date(d + 'Z').toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

  async function loadTickets(){
    try{
      tickets = (await api('/api/admin/tickets')).tickets || [];
    }catch(e){
      $('tickets-list').innerHTML = '<p class="empty">Tickets indisponibles.</p>';
      return;
    }
    renderTickets();
    if(components.length) renderDashboard();
  }

  function showTicketsTab(tab){
    ticketsTab = tab;
    renderTickets();
  }

  function ticketTodoItem(t){
    return `<div class="item">
      <div><div class="t">${escapeHtml(t.titre)} <span class="tag">${escapeHtml(t.categorie_label)}</span></div>
        <div class="why">Ticket n° ${t.id} · ${dateTicket(t.date)}${t.page ? ' · ' + escapeHtml(t.page) : ''}</div></div>
      <div class="actions"><button class="btn btn-secondary btn-sm" data-onclick="showView('tickets')">Voir</button></div>
    </div>`;
  }

  function renderTickets(){
    document.querySelectorAll('[data-section="tickets"] .tabs button').forEach(b => b.classList.toggle('active', b.id === 'tickets-tab-' + ticketsTab));
    const liste = ticketsTab === 'resolu' ? tickets.filter(t => t.statut === 'resolu') : ticketsOuverts();
    $('tickets-tab-ouverts').textContent = `À traiter (${ticketsOuverts().length})`;
    $('tickets-tab-resolu').textContent = `Résolus (${tickets.length - ticketsOuverts().length})`;
    $('tickets-list').innerHTML = liste.map(t => {
      const discussion = (t.discussion || []).map(m =>
        `<div class="ticket-msg ${m.role === 'user' ? 'moi' : ''}"><b>${m.role === 'user' ? 'Visiteur' : 'Aide IA'}</b> ${escapeHtml(m.content)}</div>`).join('');
      const actions = [
        t.statut === 'ouvert' ? `<button class="btn btn-secondary btn-sm" data-onclick="setTicketStatut(${t.id}, 'en_cours')">Je m’en occupe</button>` : '',
        t.statut !== 'resolu' ? `<button class="btn btn-primary btn-sm" data-onclick="setTicketStatut(${t.id}, 'resolu')">Résolu</button>`
                              : `<button class="btn btn-secondary btn-sm" data-onclick="setTicketStatut(${t.id}, 'ouvert')">Rouvrir</button>`,
        t.email ? `<a class="btn btn-ghost btn-sm" href="mailto:${escapeHtml(t.email)}?subject=${encodeURIComponent('PC Radar : ' + t.titre)}">Répondre</a>` : '',
        `<button class="btn btn-danger btn-sm" data-onclick="deleteTicket(${t.id})">Supprimer</button>`,
      ].join('');
      return `<div class="item ticket">
        <div class="ticket-corps">
          <div class="t">${escapeHtml(t.titre)} <span class="tag">${escapeHtml(t.categorie_label)}</span>
            <span class="tag ${t.statut === 'resolu' ? 'ok' : t.statut === 'ouvert' ? 'danger' : ''}">${STATUTS_TICKET[t.statut] || t.statut}</span></div>
          <div class="why">n° ${t.id} · ${dateTicket(t.date)}${t.page ? ` · page <a href="${escapeHtml(t.page)}" target="_blank" rel="noopener">${escapeHtml(t.page)}</a>` : ''} · ${t.email ? escapeHtml(t.email) : 'pas d’e-mail laissé'}</div>
          <p class="ticket-desc">${escapeHtml(t.description)}</p>
          ${discussion ? `<details class="ticket-discussion"><summary>Discussion avec l’aide (${t.discussion.length} messages)</summary>${discussion}</details>` : ''}
          <label class="ticket-note"><span>Note pour toi</span>
            <textarea rows="2" maxlength="2000" data-ticket-note="${t.id}" placeholder="Ce que tu as fait, à vérifier…">${escapeHtml(t.note_admin || '')}</textarea></label>
        </div>
        <div class="actions">${actions}</div>
      </div>`;
    }).join('') || `<p class="empty">${ticketsTab === 'resolu' ? 'Aucun ticket résolu pour l’instant.' : 'Aucun ticket à traiter.'}</p>`;
  }

  async function setTicketStatut(id, statut){
    try{
      await post(`/api/admin/tickets/${id}`, { statut });
      const t = tickets.find(x => x.id === id);
      if(t) t.statut = statut;
      renderTickets();
      renderDashboard();
      toast(statut === 'resolu' ? 'Ticket résolu.' : 'Ticket mis à jour.');
    }catch(e){ toast(e.message, true); }
  }

  async function deleteTicket(id){
    if(!await uiConfirm('Le ticket et sa discussion seront supprimés définitivement.',
      { title: 'Supprimer ce ticket ?', confirmLabel: 'Supprimer', danger: true })) return;
    try{
      await api(`/api/admin/tickets/${id}`, { method: 'DELETE' });
      tickets = tickets.filter(t => t.id !== id);
      renderTickets();
      renderDashboard();
      toast('Ticket supprimé.');
    }catch(e){ toast(e.message, true); }
  }

  // Note de l'admin : enregistrée quand on quitte le champ.
  document.addEventListener('change', async e => {
    const champ = e.target.closest && e.target.closest('[data-ticket-note]');
    if(!champ) return;
    const id = Number(champ.dataset.ticketNote);
    try{
      await post(`/api/admin/tickets/${id}`, { note_admin: champ.value });
      const t = tickets.find(x => x.id === id);
      if(t) t.note_admin = champ.value;
      toast('Note enregistrée.');
    }catch(err){ toast(err.message, true); }
  });

  // ---------------------------------------------------------------------
  // Serveur (processeur, mémoire, disque, services)
  // ---------------------------------------------------------------------
  let vueActuelle = '', fluxServeur = null, etatServeur = null;

  // Flux en direct (/api/admin/serveur/direct) : une mesure par seconde, l'état
  // complet toutes les 30 s. Coupé quand on quitte la page ou l'onglet, puis
  // reconnecté tout seul.
  function arreterFluxServeur(){
    if(fluxServeur){ fluxServeur.abort(); fluxServeur = null; }
  }
  async function demarrerFluxServeur(){
    arreterFluxServeur();
    const controle = new AbortController();
    fluxServeur = controle;
    try{
      const res = await fetch(API_BASE + '/api/admin/serveur/direct', {
        headers: { 'X-Admin-Secret': adminSecret }, signal: controle.signal, cache: 'no-store' });
      if(!res.ok) throw new Error('Erreur ' + res.status);
      const lecteur = res.body.getReader(), decodeur = new TextDecoder();
      let tampon = '';
      for(;;){
        const { value, done } = await lecteur.read();
        if(done) break;
        tampon += decodeur.decode(value, { stream: true });
        let fin;
        while((fin = tampon.indexOf('\n\n')) >= 0){
          const bloc = tampon.slice(0, fin); tampon = tampon.slice(fin + 2);
          const ligne = bloc.split('\n').find(l => l.startsWith('data: '));
          if(ligne) afficherServeur(JSON.parse(ligne.slice(6)));
        }
      }
    }catch(e){
      if(e.name === 'AbortError') return;
      $('serveur-direct').className = 'direct hors-ligne';
      $('serveur-direct-texte').textContent = 'Connexion perdue, nouvel essai…';
    }
    if(fluxServeur === controle && vueActuelle === 'serveur' && !document.hidden) setTimeout(() => {
      if(fluxServeur === controle) demarrerFluxServeur();
    }, 1500);
  }
  document.addEventListener('visibilitychange', () => {
    if(vueActuelle !== 'serveur') return;
    if(document.hidden) arreterFluxServeur(); else demarrerFluxServeur();
  });
  async function loadServeur(){ demarrerFluxServeur(); }
  const octets = n => {
    if(n == null) return '—';
    const u = ['o', 'Ko', 'Mo', 'Go', 'To']; let i = 0, v = n;
    while(v >= 1024 && i < u.length - 1){ v /= 1024; i++; }
    return v.toLocaleString('fr-FR', { maximumFractionDigits: v < 10 && i > 1 ? 1 : 0 }) + ' ' + u[i];
  };
  const duree = s => {
    if(s == null) return '—';
    const j = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return j ? `${j} j ${h} h` : h ? `${h} h ${m} min` : `${m} min`;
  };
  // Dates de systemctl (« Wed 2026-10-07 03:30:22 UTC ») -> « 7 oct., 05:30 » à l'heure locale.
  const dateSysteme = t => {
    if(!t) return '—';
    const m = String(t).match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})/);
    const d = m ? new Date(`${m[1]}T${m[2]}Z`) : new Date(t + (String(t).endsWith('Z') ? '' : 'Z'));
    return isNaN(d) ? escapeHtml(t) : d.toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  };
  function jauge(label, valeur, pourcent, hint){
    const niveau = pourcent == null ? '' : pourcent >= 90 ? 'is-alert' : pourcent >= 75 ? 'is-warn' : '';
    return `<div class="kpi ${niveau}"><span class="label">${label}</span><span class="value">${valeur}</span>
      ${pourcent == null ? '' : `<div class="meter"><span style="width:${Math.min(100, Math.max(2, pourcent))}%"></span></div>`}
      ${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  }

  function afficherServeur(mesure){
    // Les mesures rapides complètent le dernier état complet.
    etatServeur = mesure.complet || !etatServeur ? mesure : { ...etatServeur, ...mesure };
    const d = etatServeur;
    const cpu = d.cpu || {}, mem = d.memoire, disque = d.disque, cert = d.certificat, sauv = d.sauvegarde;
    const pctMem = mem ? mem.utilise / mem.total * 100 : null;
    const pctDisque = disque ? disque.utilise / disque.total * 100 : null;
    $('serveur-kpis').innerHTML = [
      jauge('Processeur', cpu.utilisation == null ? '—' : `${nombre(cpu.utilisation)} %`, cpu.utilisation,
        `${cpu.coeurs || '?'} cœurs${cpu.charge ? ` · charge ${cpu.charge.map(x => x.toLocaleString('fr-FR')).join(' / ')}` : ''}`),
      jauge('Mémoire vive', mem ? octets(mem.utilise) : '—', pctMem,
        mem ? `sur ${octets(mem.total)} · ${octets(mem.disponible)} disponibles${mem.swap_total ? ` · swap ${octets(mem.swap_utilise)} / ${octets(mem.swap_total)}` : ''}` : ''),
      jauge('Disque', disque ? octets(disque.utilise) : '—', pctDisque,
        disque ? `sur ${octets(disque.total)} · ${octets(disque.libre)} libres` : ''),
      jauge('En ligne depuis', duree(d.demarre_depuis_s), null, escapeHtml([d.nom, d.systeme].filter(Boolean).join(' · '))),
      jauge('Certificat HTTPS', cert ? `${cert.jours} j` : '—', null,
        cert ? `expire le ${new Date(cert.expire + 'Z').toLocaleDateString('fr-FR')} · renouvelé automatiquement` : 'non vérifié'),
      jauge('Dernière sauvegarde', sauv ? dateSysteme(sauv.date) : '—', null,
        sauv ? `${octets(sauv.taille)} compressée · ${sauv.nombre} gardées` : 'aucune trouvée'),
    ].join('');
    if(cert && cert.jours < 15) $('serveur-kpis').children[4].classList.add('is-alert');

    const services = d.services || [];
    const enPanne = services.filter(s => s.etat !== 'active');
    $('serveur-services').innerHTML = services.map(s => `<div class="item">
      <div><div class="t">${escapeHtml(s.nom)} <span class="tag ${s.etat === 'active' ? 'ok' : 'danger'}">${s.etat === 'active' ? 'En marche' : escapeHtml(s.etat)}</span></div>
        <div class="why">${s.memoire != null ? octets(s.memoire) + ' de mémoire · ' : ''}démarré le ${dateSysteme(s.depuis)}</div></div></div>`).join('')
      || '<p class="empty">Services non disponibles.</p>';
    $('serveur-taches').innerHTML = (d.taches || []).map(t => `<div class="item">
      <div><div class="t">${escapeHtml(t.nom)}</div>
        <div class="why">dernière fois ${dateSysteme(t.dernier)}${t.prochain ? ` · prochaine ${dateSysteme(t.prochain)}` : ' · toutes les 5 minutes'}</div></div></div>`).join('')
      || '<p class="empty">Tâches non disponibles.</p>';
    $('serveur-dossiers').innerHTML = disque ? disque.dossiers.map(x => `<div class="item">
      <div><div class="t">${escapeHtml(x.nom)}</div></div><div class="actions"><span class="serveur-taille">${octets(x.taille)}</span></div></div>`).join('') : '';
    $('serveur-direct').className = 'direct';
    $('serveur-direct-texte').textContent = `En direct · ${new Date(d.mesure_le + 'Z').toLocaleTimeString('fr-FR')}`;
    const compteur = $('nav-serveur');
    compteur.textContent = enPanne.length ? String(enPanne.length) : '';
    compteur.classList.toggle('alert', enPanne.length > 0);
  }

  // ---------------------------------------------------------------------
  // Configurations recommandées
  // ---------------------------------------------------------------------
  async function loadBuilds(){
    try{
      const d = await api('/api/admin/builds');
      const builds = (d.builds || []).slice().sort((a, b) => (b.est_officielle ? 1 : 0) - (a.est_officielle ? 1 : 0));
      $('builds-list').innerHTML = builds.map(b => `<div class="item">
        <div><div class="t">${escapeHtml(b.nom)} ${b.est_officielle ? '<span class="tag ok">Recommandée</span>' : ''}</div>
          <div class="why">${escapeHtml(b.user_email || 'anonyme')} · ${new Date(b.date).toLocaleDateString('fr-FR')}</div></div>
        <div class="actions">
          <a class="btn btn-ghost btn-sm" href="/build/${b.id}" target="_blank" rel="noopener">Voir</a>
          <button class="btn ${b.est_officielle ? 'btn-secondary' : 'btn-primary'} btn-sm" data-onclick="toggleOfficialBuild(${b.id})">${b.est_officielle ? 'Retirer' : 'Mettre en avant'}</button>
          <button class="btn btn-danger btn-sm" data-onclick="deleteBuild(${b.id})">Supprimer</button>
        </div></div>`).join('') || '<p class="empty">Aucune configuration sauvegardée pour l\'instant.</p>';
    }catch(e){
      $('builds-list').innerHTML = '<p class="empty">Liste indisponible.</p>';
    }
  }

  async function toggleOfficialBuild(id){
    try{ await post(`/api/admin/builds/${id}/toggle-officielle`); await loadBuilds(); }
    catch(e){ toast(e.message, true); }
  }

  async function deleteBuild(id){
    if(!await uiConfirm('La configuration sera supprimée définitivement, pour son propriétaire aussi (ses alertes de prix avec).',
      { title: 'Supprimer cette configuration ?', confirmLabel: 'Supprimer', danger: true })) return;
    try{ await api(`/api/admin/builds/${id}`, { method: 'DELETE' }); toast('Configuration supprimée.'); await loadBuilds(); }
    catch(e){ toast(e.message, true); }
  }

  // ---------------------------------------------------------------------
  // Raccourcis et écouteurs
  // ---------------------------------------------------------------------
  ['catalog-search', 'catalog-category', 'catalog-filter'].forEach(id => {
    $(id).addEventListener(id === 'catalog-search' ? 'input' : 'change', () => { rowsShown = 150; renderCatalog(); });
  });
  document.addEventListener('keydown', e => {
    if(e.key === 'Escape' && !$('drawer').hidden){ closeDrawer(); return; }
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if(e.key === '/' && !typing && !$('app').hidden){
      e.preventDefault();
      showView('catalog');
    }
    if((e.ctrlKey || e.metaKey) && e.key === 's' && !$('drawer').hidden){
      e.preventDefault();
      saveComponent();
    }
  });
  window.addEventListener('hashchange', () => {
    const name = location.hash.slice(1);
    if(document.querySelector(`[data-section="${name}"]`)) showView(name);
  });

  tryAutoLogin();
