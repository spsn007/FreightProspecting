document.addEventListener('alpine:init', () => {
  const user = JSON.parse(document.getElementById('team-user-data').textContent);
  const initial = JSON.parse(document.getElementById('team-initial-data').textContent);
  Alpine.store('team', {
    user, state: initial, users: [], refreshError: '', refreshing: false, resultsChanged: false,
    notifications: {items: [], unread_count: 0}, notificationError: '', notificationsRefreshing: false,
    mine(id) { return this.state[id]?.owner_id === this.user.id; },
    callAccessMessage(id) {
      if (this.mine(id)) return '';
      const owner = this.state[id]?.owner_name;
      return owner ? 'Only ' + owner + ' can log calls or update status. Ask ' + owner + ' or Admin to transfer this company to you.' : 'Select Start Working before logging a call or updating status.';
    },
    count(status) {
      return Object.values(this.state).filter(s =>
        (this.user.role !== 'BROKER' || status === 'NOT_INTERESTED' || s.owner_id === this.user.id) &&
        (status === 'FOLLOW_UP' ? !!s.next_follow_up_at : s.outreach_status === status)
      ).length;
    },
    async refreshNotifications() {
      if (this.notificationsRefreshing) return;
      this.notificationsRefreshing = true;
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        this.notifications = await teamRequest('/api/notifications?tz=' + encodeURIComponent(tz));
        this.notificationError = '';
      } catch (_) { this.notificationError = 'Notifications could not refresh. Try again.'; }
      finally { this.notificationsRefreshing = false; }
    },
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
        await this.refreshNotifications();
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

function teamCompany(companyId, callingZone = null) {
  return {
    companyId, busy: false, error: '', transferring: false, targetId: '', note: '', rescheduling: false, newFollowUp: '',
    callingZone, timePreview: '', previewVersion: 0,
    async previewReschedule() {
      const version = ++this.previewVersion;
      const [date,time] = this.newFollowUp.split('T');
      try { const text = await callingTimes.preview(this.callingZone,date,time); if (version === this.previewVersion) this.timePreview = text; }
      catch(error) { if (version === this.previewVersion) this.timePreview = error.message; }
    },
    get state() { return this.$store.team.state[this.companyId] || {}; },
    get mine() { return this.$store.team.mine(this.companyId); },
    get canManage() { return this.mine || this.$store.team.user.role === 'ADMIN'; },
    beginReschedule() {
      const due = new Date(this.state.next_follow_up_at);
      if (Number.isNaN(due.getTime())) return;
      due.setMinutes(due.getMinutes() - due.getTimezoneOffset());
      this.newFollowUp = due.toISOString().slice(0,16);
      this.rescheduling = true; this.error = '';
      this.previewReschedule();
    },
    async reschedule() {
      if (this.busy) return;
      const due = new Date(this.newFollowUp);
      if (!this.newFollowUp || Number.isNaN(due.getTime())) { this.error = 'Choose a valid follow-up date and time.'; return; }
      this.busy = true; this.error = '';
      try {
        this.$store.team.state[this.companyId] = await teamRequest('/api/admin/companies/' + this.companyId + '/follow-up', {follow_up_at:due.toISOString()});
        this.rescheduling = false;
        window.dispatchEvent(new CustomEvent('team-updated', {detail:this.$store.team.state}));
        await this.$store.team.refreshNotifications();
        freightWorkflow.notice('Follow-up rescheduled. The assigned broker has been notified.');
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
    async act(action) {
      if (this.busy) return;
      if (action === 'release' && !await freightWorkflow.confirm('Release this company for the team? Call history and follow-ups will remain saved.', 'Release company?', 'Release company')) return;
      if (action === 'claim' && this.state.outreach_status === 'NOT_INTERESTED' && !await freightWorkflow.confirm('This company previously said Not Interested. Review its history before contacting it. Start working anyway?', 'Review before calling', 'Start working')) return;
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
    operation: '', newName: '', newPassword: '', transferTo: '',
    async save(url, data) {
      this.busy = true; this.error = '';
      try { await teamRequest(url, data); window.location.reload(); }
      catch (error) { this.error = error.message; this.busy = false; }
    }
  };
}


function notificationPanel() {
  return {
    open: false, busy: false, title: '', message: '', error: '',
    async toggle() {
      this.open = !this.open;
      if (this.open) await this.$store.team.refreshNotifications();
    },
    async read(item = null) {
      this.error = '';
      try {
        await teamRequest('/api/notifications/read', {
          keys: item ? [item.key] : null, tz: Intl.DateTimeFormat().resolvedOptions().timeZone
        });
        await this.$store.team.refreshNotifications();
      } catch (error) { this.error = error.message; }
    },
    async visit(item) {
      await this.read(item);
      if (item.url) window.location.assign(item.url);
    },
    async send() {
      if (this.busy) return;
      this.busy = true; this.error = '';
      try {
        const result = await teamRequest('/api/admin/announcements', {title:this.title, message:this.message});
        this.title = ''; this.message = '';
        freightWorkflow.notice('Announcement sent to ' + result.recipients + ' active brokers.');
        await this.$store.team.refreshNotifications();
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    }
  };
}
