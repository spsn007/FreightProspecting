window.freightWorkflow = {
  confirm(message, title = 'Confirm change', action = 'Confirm') {
    // Native dialog supplies focus containment, Escape and inert background.
    if (document.querySelector('.workflow-confirm[open]')) return Promise.resolve(false);
    const dialog = document.createElement('dialog');
    dialog.className = 'workflow-confirm';
    dialog.setAttribute('aria-labelledby', 'workflow-confirm-title');
    dialog.setAttribute('aria-describedby', 'workflow-confirm-description');
    dialog.innerHTML = '<form method="dialog"><div class="workflow-confirm-heading"><span class="workflow-confirm-icon" aria-hidden="true">!</span><h2 id="workflow-confirm-title"></h2></div><p id="workflow-confirm-description"></p><div class="workflow-confirm-actions"><button class="btn btn-secondary" value="cancel" autofocus>Cancel</button><button class="btn btn-primary" value="confirm"></button></div></form>';
    dialog.querySelector('h2').textContent = title;
    dialog.querySelector('p').textContent = message;
    dialog.querySelector('[value="confirm"]').textContent = action;
    document.body.appendChild(dialog);
    return new Promise(resolve => {
      dialog.addEventListener('close', () => { const confirmed = dialog.returnValue === 'confirm'; dialog.remove(); resolve(confirmed); }, {once:true});
      dialog.showModal();
    });
  },
  read(key, fallback = null) {
    try { return JSON.parse(sessionStorage.getItem(key)) ?? fallback; }
    catch (_) { return fallback; }
  },
  store(key, value) {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  },
  date(value) {
    const date = new Date(value);
    return value && !Number.isNaN(date.getTime())
      ? date.toLocaleString([], {month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short'})
      : 'Not scheduled';
  },
  notice(message) {
    window.dispatchEvent(new CustomEvent('workflow-notice', {detail: message}));
  },
  async copy(value, label) {
    try {
      await navigator.clipboard.writeText(value);
      this.notice(label + ' copied');
    } catch (_) { this.notice('Could not copy. Select the ' + label.toLowerCase() + ' and copy it manually.'); }
  },
  sortCompanies(items, sort) {
    if (sort === 'relevance') return items;
    return items.sort((a, b) => {
      const name = (a.operating_brand || '').localeCompare(b.operating_brand || '');
      if (sort === 'follow_up') return (a.next_follow_up_at || '9999').localeCompare(b.next_follow_up_at || '9999') || name;
      if (sort === 'fac_desc') return b.facility_count - a.facility_count || name;
      if (sort === 'fac_asc') return a.facility_count - b.facility_count || name;
      return name;
    });
  },
  sequence(items, mode) {
    return items.map(item => ({
      facilityId: mode === 'FACILITIES' ? item.facility_id : item.primary_facility_id,
      companyId: item.company_id,
      name: item.operating_brand
    })).filter(item => item.facilityId);
  },
  profileUrl(facilityId, returnTo) {
    return '/prospects/' + facilityId + '?return_to=' + encodeURIComponent(returnTo);
  },
  recentProfiles() {
    const items = this.read('fp_recent_profiles', []);
    return Array.isArray(items) ? items.filter(item => Number.isInteger(item.facilityId) && item.facilityId > 0).slice(0, 5) : [];
  },
  remember(profile) {
    const recent = this.recentProfiles().filter(item => item.facilityId !== profile.facilityId);
    recent.unshift({facilityId: profile.facilityId, name: profile.name});
    this.store('fp_recent_profiles', recent.slice(0, 5));
    window.dispatchEvent(new CustomEvent('recent-profiles-changed'));
  },
  async neighbors(profile) {
    const context = this.read('fp_directory_position');
    if (!context || context.url !== profile.returnTo || !Array.isArray(context.sequence)) return {};
    const index = context.sequence.findIndex(item => context.mode === 'FACILITIES'
      ? item.facilityId === profile.facilityId : item.companyId === profile.companyId);
    if (index < 0) return {};
    const neighbor = (item, state) => item ? {name: item.name, href: this.profileUrl(item.facilityId, state.url), context: state} : null;
    const result = {
      previous: neighbor(context.sequence[index - 1], context),
      next: neighbor(context.sequence[index + 1], context)
    };
    // Only fetch an adjacent results page when the current profile is at a page boundary.
    for (const [direction, step] of [['previous', -1], ['next', 1]]) {
      const page = context.page + step;
      if (result[direction] || page < 1 || page > context.totalPages) continue;
      const url = new window.URL(context.url, window.location.origin);
      url.searchParams.set('page', page);
      try {
        const response = await fetch(url.pathname + url.search);
        if (!response.ok) throw new Error('Could not load the adjacent results page');
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const id = context.mode === 'FACILITIES' ? 'prospects-data' : 'company-groups-data';
        let items = JSON.parse(doc.getElementById(id).textContent);
        if (context.mode !== 'FACILITIES') items = this.sortCompanies(items, context.sort);
        const state = {...context, url: url.pathname + url.search, page, scrollY: 0, anchorId: null, expandedCompanies: {}, sequence: this.sequence(items, context.mode)};
        result[direction] = neighbor(direction === 'next' ? state.sequence[0] : state.sequence[state.sequence.length - 1], state);
      } catch (_) { result.error = 'Could not load the next results page. Use Back to Results to continue.'; }
    }
    return result;
  }
};
