// Fonctions réservées aux comptes : suivi de prix (favoris) et alertes de
// baisse de prix. Partagé entre le configurateur, le comparateur et la page
// compte, qui appellent PCAccount.mountFollow() dans leur fenêtre de détail.
(function(){
  const state = { loaded: null, loggedIn: false, favorites: new Map() };

  function esc(str){
    return String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function fmtPrice(n){
    return Number(n).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  }

  async function load(force){
    if(state.loaded && !force) return state.loaded;
    state.loaded = (async () => {
      try{
        const me = await fetch('/api/auth/me', { credentials: 'include' }).then(r => r.json());
        state.loggedIn = !!me.logged_in;
        state.favorites = new Map();
        if(state.loggedIn){
          const data = await fetch('/api/favorites', { credentials: 'include' }).then(r => r.json());
          (data.favorites || []).forEach(f => state.favorites.set(f.component_id, f));
        }
      }catch(e){
        console.error('Chargement du compte impossible', e);
      }
      return state;
    })();
    return state.loaded;
  }

  async function api(method, url, body){
    const res = await fetch(url, {
      method, credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if(!res.ok){
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Erreur, réessaie dans un instant.');
    }
    return res.json();
  }

  // Bloc "Suivre le prix" dans une fenêtre de détail composant.
  async function mountFollow(slot, item){
    if(!slot || !item) return;
    slot.innerHTML = '<div class="follow-box is-loading"><span class="skel" style="display:block; height:38px;"></span></div>';
    await load();
    if(!slot.isConnected) return;

    if(!state.loggedIn){
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      slot.innerHTML = `
        <div class="follow-box">
          <div class="follow-text">
            <strong>Suivre le prix de ce composant</strong>
            <span>Crée un compte gratuit pour être prévenu quand il baisse.</span>
          </div>
          <a class="btn btn-secondary" href="/compte?next=${next}"><i class="ph ph-bell-simple" aria-hidden="true"></i> Se connecter</a>
        </div>`;
      return;
    }

    const fav = state.favorites.get(item.id);
    if(!fav){
      slot.innerHTML = `
        <div class="follow-box">
          <div class="follow-text">
            <strong>Suivre le prix</strong>
            <span>Retrouve-le dans ton compte et reçois une alerte quand il baisse.</span>
          </div>
          <button type="button" class="btn btn-primary" data-act="follow"><i class="ph ph-bell-simple" aria-hidden="true"></i> Suivre</button>
        </div>`;
      slot.querySelector('[data-act="follow"]').onclick = async (e) => {
        e.currentTarget.disabled = true;
        try{
          await api('POST', '/api/favorites', { component_id: item.id });
          await load(true);
        }catch(err){ alertInline(slot, err.message); }
        mountFollow(slot, item);
      };
      return;
    }

    slot.innerHTML = `
      <div class="follow-box is-following">
        <div class="follow-text">
          <strong><i class="ph ph-check-circle" aria-hidden="true"></i> Prix suivi</strong>
          <span>${fav.prix_cible ? `Alerte si le prix passe sous ${fmtPrice(fav.prix_cible)}.` : 'Ajoute un prix cible pour recevoir une alerte par e-mail.'}</span>
        </div>
        <form class="follow-target" data-act="target">
          <label class="visually-hidden" for="target-${item.id}">Prix cible en euros</label>
          <input id="target-${item.id}" type="number" min="1" step="0.01" inputmode="decimal" placeholder="Prix cible €" value="${fav.prix_cible ?? ''}">
          <button type="submit" class="btn btn-secondary">${fav.prix_cible ? 'Modifier' : 'Alerte'}</button>
          <button type="button" class="btn-link" data-act="unfollow">Ne plus suivre</button>
        </form>
        <p class="follow-error" role="alert"></p>
      </div>`;
    slot.querySelector('[data-act="target"]').onsubmit = async (e) => {
      e.preventDefault();
      const raw = e.currentTarget.querySelector('input').value.trim();
      try{
        await api('PATCH', `/api/favorites/${item.id}`, { prix_cible: raw ? Number(raw) : null });
        await load(true);
        mountFollow(slot, item);
      }catch(err){ alertInline(slot, err.message); }
    };
    slot.querySelector('[data-act="unfollow"]').onclick = async () => {
      try{
        await api('DELETE', `/api/favorites/${item.id}`);
        await load(true);
        mountFollow(slot, item);
      }catch(err){ alertInline(slot, err.message); }
    };
  }

  function alertInline(slot, message){
    const el = slot.querySelector('.follow-error');
    if(el){ el.textContent = message; }
  }

  // Section "Composants suivis" de la page compte.
  async function renderFavorites(container, onOpenDetail){
    if(!container) return;
    await load(true);
    const favs = [...state.favorites.values()];
    if(!favs.length){
      container.innerHTML = `
        <div class="empty-state">
          <i class="ph ph-bell-simple" aria-hidden="true"></i>
          <div>
            <strong>Aucun composant suivi</strong>
            <p>Ouvre la fiche d'un composant dans le <a href="/configurateur">configurateur</a> ou le <a href="/comparateur">comparateur</a> et clique sur « Suivre » pour voir l'évolution de son prix ici.</p>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = favs.map(f => {
      const delta = (f.prix_actuel && f.prix_ajout) ? f.prix_actuel - f.prix_ajout : null;
      const deltaHtml = delta === null || Math.abs(delta) < 0.01
        ? '<span class="delta">Stable depuis le suivi</span>'
        : `<span class="delta ${delta < 0 ? 'down' : 'up'}">${delta < 0 ? '−' : '+'}${fmtPrice(Math.abs(delta))} depuis le suivi</span>`;
      const offer = f.meilleure_offre && f.meilleure_offre.lien && typeof withAffiliateTag === 'function'
        ? `<a class="btn btn-secondary" href="${esc(withAffiliateTag(f.meilleure_offre.lien, f.meilleure_offre.vendeur))}" target="_blank" rel="noopener noreferrer sponsored">Voir l'offre</a>` : '';
      return `
        <div class="fav-row" data-id="${f.component_id}">
          <button type="button" class="fav-main" data-act="detail">
            <span class="row-thumb">${f.image_url ? `<img src="${esc(f.image_url)}?w=100" alt="" loading="lazy" decoding="async">` : ''}</span>
            <span class="fav-name">
              <span class="cat">${esc(f.categorie)}${f.en_stock ? '' : ' · épuisé'}</span>
              <span class="nom">${esc(f.nom)}</span>
            </span>
          </button>
          <div class="fav-price">
            <span class="now">${f.prix_actuel ? fmtPrice(f.prix_actuel) : 'Prix indisponible'}</span>
            ${deltaHtml}
            ${f.prix_plus_bas && f.prix_actuel && f.prix_plus_bas < f.prix_actuel - 0.01 ? `<span class="low">Plus bas relevé : ${fmtPrice(f.prix_plus_bas)}</span>` : ''}
          </div>
          <form class="follow-target" data-act="target">
            <label class="visually-hidden" for="fav-target-${f.component_id}">Prix cible en euros</label>
            <input id="fav-target-${f.component_id}" type="number" min="1" step="0.01" inputmode="decimal" placeholder="Alerte sous… €" value="${f.prix_cible ?? ''}">
            <button type="submit" class="btn btn-secondary" title="Enregistrer le prix cible"><i class="ph ph-bell-simple" aria-hidden="true"></i><span class="visually-hidden">Enregistrer l'alerte</span></button>
          </form>
          <div class="fav-actions">
            ${offer}
            <button type="button" class="btn-link" data-act="unfollow">Retirer</button>
          </div>
          <p class="follow-error" role="alert"></p>
        </div>`;
    }).join('');

    container.querySelectorAll('.fav-row').forEach(row => {
      const id = Number(row.dataset.id);
      row.querySelector('[data-act="detail"]').onclick = () => onOpenDetail && onOpenDetail(id);
      row.querySelector('[data-act="target"]').onsubmit = async (e) => {
        e.preventDefault();
        const raw = e.currentTarget.querySelector('input').value.trim();
        try{
          await api('PATCH', `/api/favorites/${id}`, { prix_cible: raw ? Number(raw) : null });
          renderFavorites(container, onOpenDetail);
        }catch(err){ row.querySelector('.follow-error').textContent = err.message; }
      };
      row.querySelector('[data-act="unfollow"]').onclick = async () => {
        try{
          await api('DELETE', `/api/favorites/${id}`);
          renderFavorites(container, onOpenDetail);
        }catch(err){ row.querySelector('.follow-error').textContent = err.message; }
      };
    });
  }

  window.PCAccount = { load, mountFollow, renderFavorites, fmtPrice };
})();
