// Boîtes de dialogue du site, à la place de confirm(), alert() et prompt()
// du navigateur (fenêtres grises « pcradar.tech indique »). Styles dans
// static/dialog.css. Chaque fonction renvoie une promesse :
//   await uiConfirm(message, { title, confirmLabel, danger })  → true / false
//   await uiAlert(message, { title, tone })                     → undefined
//   await uiPrompt(message, valeur, { title, confirmLabel })    → texte / null
// Échap ou clic à côté = Annuler ; Entrée = valider.
(function(){
  const ICONS = {
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/></svg>',
    danger: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4h6v3"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>',
    ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };

  let queue = Promise.resolve();

  function open({ kind, title, message, value, confirmLabel, cancelLabel, danger, tone, maxLength }){
    return new Promise(resolve => {
      const previousFocus = document.activeElement;
      const overlay = document.createElement('div');
      overlay.className = 'pcr-dlg-overlay';
      const box = document.createElement('div');
      box.className = 'pcr-dlg' + (danger ? ' is-danger' : '');
      box.setAttribute('role', kind === 'alert' ? 'alertdialog' : 'dialog');
      box.setAttribute('aria-modal', 'true');

      const id = 'pcr-dlg-' + Math.random().toString(36).slice(2);
      const head = document.createElement('div');
      head.className = 'pcr-dlg-head';
      const icon = document.createElement('div');
      icon.className = 'pcr-dlg-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.innerHTML = ICONS[danger ? 'danger' : kind === 'prompt' ? 'edit' : tone === 'ok' ? 'ok' : 'info'];
      const text = document.createElement('div');
      text.style.minWidth = '0';
      const h = document.createElement('h2');
      h.className = 'pcr-dlg-title';
      h.id = id + '-t';
      h.textContent = title;
      text.appendChild(h);
      box.setAttribute('aria-labelledby', h.id);
      if(message){
        const p = document.createElement('p');
        p.className = 'pcr-dlg-msg';
        p.id = id + '-m';
        p.textContent = message;
        text.appendChild(p);
        box.setAttribute('aria-describedby', p.id);
      }
      head.append(icon, text);
      box.appendChild(head);

      let input = null;
      if(kind === 'prompt'){
        input = document.createElement('input');
        input.className = 'pcr-dlg-input';
        input.type = 'text';
        input.value = value || '';
        if(maxLength) input.maxLength = maxLength;
        input.setAttribute('aria-labelledby', h.id);
        box.appendChild(input);
      }

      const actions = document.createElement('div');
      actions.className = 'pcr-dlg-actions';
      let cancelBtn = null;
      if(kind !== 'alert'){
        cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'pcr-dlg-btn is-secondary';
        cancelBtn.textContent = cancelLabel || 'Annuler';
        actions.appendChild(cancelBtn);
      }
      const okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = 'pcr-dlg-btn ' + (danger ? 'is-danger' : 'is-primary');
      okBtn.textContent = confirmLabel || 'OK';
      actions.appendChild(okBtn);
      box.appendChild(actions);
      overlay.appendChild(box);

      let done = false;
      function close(result){
        if(done) return;
        done = true;
        document.removeEventListener('keydown', onKey, true);
        overlay.classList.add('is-closing');
        const remove = () => overlay.remove();
        const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        reduce ? remove() : setTimeout(remove, 140);
        if(previousFocus && previousFocus.focus) try{ previousFocus.focus({ preventScroll: true }); }catch(e){}
        resolve(result);
      }
      const accept = () => {
        if(kind === 'prompt'){
          const v = input.value.trim();
          if(!v){ input.focus(); return; }
          close(v);
        }else close(kind === 'confirm' ? true : undefined);
      };
      const cancel = () => close(kind === 'confirm' ? false : kind === 'prompt' ? null : undefined);

      function onKey(e){
        if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); cancel(); }
        else if(e.key === 'Enter' && (e.target === input || !e.target.closest || !e.target.closest('.pcr-dlg-btn'))){ e.preventDefault(); accept(); }
        else if(e.key === 'Tab'){
          // Le focus reste dans la boîte.
          const items = [input, cancelBtn, okBtn].filter(Boolean);
          const i = items.indexOf(document.activeElement);
          e.preventDefault();
          items[(i + (e.shiftKey ? -1 : 1) + items.length) % items.length].focus();
        }
      }
      okBtn.addEventListener('click', accept);
      if(cancelBtn) cancelBtn.addEventListener('click', cancel);
      overlay.addEventListener('mousedown', e => { if(e.target === overlay) cancel(); });
      document.addEventListener('keydown', onKey, true);

      document.body.appendChild(overlay);
      if(input){ input.focus(); input.select(); }
      else (danger && cancelBtn ? cancelBtn : okBtn).focus();
    });
  }

  // Une seule boîte à la fois : les suivantes attendent leur tour.
  function enqueue(options){
    const next = queue.then(() => open(options));
    queue = next.catch(() => {});
    return next;
  }

  window.uiConfirm = (message, o = {}) => enqueue({ kind: 'confirm', title: o.title || 'Confirmer', message, confirmLabel: o.confirmLabel, cancelLabel: o.cancelLabel, danger: !!o.danger });
  window.uiAlert = (message, o = {}) => enqueue({ kind: 'alert', title: o.title || 'Information', message, confirmLabel: o.confirmLabel || 'OK', tone: o.tone });
  window.uiPrompt = (message, value, o = {}) => enqueue({ kind: 'prompt', title: o.title || message, message: o.title ? message : '', value, confirmLabel: o.confirmLabel || 'Valider', maxLength: o.maxLength });
})();
