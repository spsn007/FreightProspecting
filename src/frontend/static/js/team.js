document.addEventListener('alpine:init', () => {
  const user = JSON.parse(document.getElementById('team-user-data').textContent);
  const initial = JSON.parse(document.getElementById('team-initial-data').textContent);
  Alpine.store('team', {
    user, state: initial, users: [], refreshError: '', refreshing: false, resultsChanged: false,
    mine(id) { return this.state[id]?.owner_id === this.user.id; },
    count(status) { return Object.values(this.state).filter(s => status === 'FOLLOW_UP' ? !!s.next_follow_up_at : s.outreach_status === status).length; },
    async refresh() {
      if (this.refreshing || document.hidden) return;
      this.refreshing = true;
      try {
        const response = await fetch('/api/team/state');
        if (response.status === 401) { window.location.assign('/login'); return; }
        if (!response.ok) throw new Error();
        const incoming = await response.json();
        const p = new URLSearchParams(location.search), view = p.get('team_view');
        const statuses = p.getAll('outreach').flatMap(v => v.split(','));
        const membership = state => Object.values(state).filter(s =>
          (view !== 'mine' || s.owner_id === this.user.id) &&
          (view !== 'available' || !s.owner_id && s.outreach_status !== 'NOT_INTERESTED' && !s.is_suppressed) &&
          (!statuses.length || statuses.some(status => ['FOLLOW_UP','FOLLOW_UPS'].includes(status) ? !!s.next_follow_up_at : status === s.outreach_status))
        ).map(s => s.company_id).sort((a,b) => a-b).join(',');
        if (document.getElementById('prospect-directory') && membership(incoming) !== membership(this.state)) this.resultsChanged = true;
        this.state = incoming;
        this.refreshError = '';
        window.dispatchEvent(new CustomEvent('team-updated', { detail: this.state }));
        if (this.resultsChanged && !document.querySelector('#log-call-modal:not([style*="display: none"])') &&
            !document.activeElement?.matches('input,textarea,select') && !document.querySelector('.team-transfer:not([style*="display: none"])')) {
          window.dispatchEvent(new Event('team-results-changing'));
          location.reload();
        }
      } catch (_) { this.refreshError = 'Team updates paused. Check your connection before calling.'; }
      finally { this.refreshing = false; }
    },
    async init() {
      this.refresh();
      try { this.users = await teamRequest('/api/team/users'); } catch (_) {}
      setInterval(() => this.refresh(), 15000);
      document.addEventListener('visibilitychange', () => this.refresh());
      window.addEventListener('outreach-logged', () => this.refresh());
    }
  });
});

async function teamRequest(url, body) {
  const response = await fetch(url, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  });
  if (response.status === 401) { window.location.assign('/login'); throw new Error('Please log in again.'); }
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the form and try again.');
  return data;
}

function teamCompany(companyId) {
  return {
    companyId, busy: false, error: '', transferring: false, targetId: '', note: '',
    get state() { return this.$store.team.state[this.companyId] || {}; },
    get mine() { return this.$store.team.mine(this.companyId); },
    get canManage() { return this.mine || this.$store.team.user.role === 'ADMIN'; },
    async act(action) {
      if (this.busy) return;
      if (action === 'release' && !confirm('Release this company for the team? Call history and follow-ups will remain saved.')) return;
      if (action === 'claim' && this.state.outreach_status === 'NOT_INTERESTED' && !confirm('This company previously said Not Interested. Review its history before contacting it. Start working anyway?')) return;
      this.busy = true; this.error = '';
      try {
        const state = await teamRequest('/api/team/companies/' + this.companyId, {
          action, target_id: action === 'transfer' ? Number(this.targetId) : null, note: this.note
        });
        this.$store.team.state[this.companyId] = state;
        this.transferring = false; this.note = '';
        window.dispatchEvent(new CustomEvent('team-updated', { detail: this.$store.team.state }));
        if (new URLSearchParams(location.search).get('team_view') && new URLSearchParams(location.search).get('team_view') !== 'all') { this.$store.team.resultsChanged = true; await this.$store.team.refresh(); }
        freightWorkflow.notice(action === 'claim' ? 'Company assigned to you.' : action === 'release' ? 'Company released.' : 'Company transferred.');
      } catch (error) { this.error = error.message; await this.$store.team.refresh(); }
      finally { this.busy = false; }
    }
  };
}

function teamLabel(status) {
  const labels = JSON.parse(document.getElementById('outreach-labels-global')?.textContent || '{}');
  return labels[status] || status || 'No Active Call Status';
}

// All phone/email entry points share this ownership guard, including facility cards.
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="tel:"],a[href^="mailto:"]');
  if (!link || !window.Alpine) return;
  const card = link.closest('[data-company-id]');
  const profile = document.getElementById('profile-workflow-data');
  const companyId = card ? Number(card.dataset.companyId) : profile ? JSON.parse(profile.textContent).companyId : null;
  if (companyId && !Alpine.store('team').mine(companyId)) {
    event.preventDefault(); event.stopPropagation();
    freightWorkflow.notice('Start Working before contacting this company.');
  }
}, true);

function teamAdmin() {
  return {
    username: '', password: '', error: '', busy: false, selectedUser: null, selectedName: '',
    operation: '', newPassword: '', transferTo: '',
    async save(url, data) {
      this.busy = true; this.error = '';
      try { await teamRequest(url, data); window.location.reload(); }
      catch (error) { this.error = error.message; this.busy = false; }
    }
  };
}
