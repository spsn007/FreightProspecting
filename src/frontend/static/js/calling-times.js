// Server IANA offsets keep browser clocks consistent with current Canadian rules.
window.callingTimes = {
  normalize(text) { return String(text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim(); },
  matches(text, query) {
    const haystack = this.normalize(text), words = haystack.split(' ');
    return this.normalize(query).split(' ').filter(Boolean).every(term => term.length <= 2 ? words.includes(term) : haystack.includes(term));
  },
  parts(at, offset, format = '12', seconds = false) {
    const d = new Date(new Date(at).getTime() + offset * 60000);
    return {hour: d.getUTCHours(), minute: d.getUTCMinutes(), day: d.getUTCDay(),
      text: new Intl.DateTimeFormat('en-US', {timeZone:'UTC', weekday:'short', month:'short', day:'numeric', hour:'numeric', minute:'2-digit', hourCycle:format === '24' ? 'h23' : 'h12', ...(seconds ? {second:'2-digit'} : {})}).format(d)};
  },
  status(parts, start, end) {
    if (parts.day === 0 || parts.day === 6) return 'Outside calling hours · Weekend';
    const minutes = parts.hour * 60 + parts.minute;
    if (minutes < start * 60 || minutes >= end * 60) return 'Outside calling hours';
    return end * 60 - minutes <= 30 ? 'Closing soon' : 'Within calling hours';
  },
  async preview(zone, date, time) {
    if (!date) return '';
    const at = new Date(`${date}T${time || '09:00'}:00`);
    if (isNaN(at)) return 'Choose a valid date and time.';
    const response = await fetch('/api/calling-times?at=' + encodeURIComponent(at.toISOString()));
    if (!response.ok) throw new Error('Time conversion unavailable. Please try again.');
    const data = await response.json();
    const format = Alpine.store('calling').format;
    const india = this.parts(at, 330, format).text;
    if (!zone || !data.zones[zone]) return `India: ${india} IST · Company time zone needs confirmation.`;
    const local = this.parts(at, data.zones[zone].offset, format);
    const store = Alpine.store('calling');
    const status = this.status(local, store.start, store.end);
    return `Company: ${local.text} (${zone.split('/').pop().replaceAll('_',' ')}) · India: ${india} IST` +
      (status !== 'Within calling hours' ? ` · ${status} (estimated). You can still schedule the requested time.` : '');
  }
};
document.addEventListener('alpine:init', () => {
  const user = JSON.parse(document.getElementById('team-user-data').textContent);
  const key = 'calling-window-' + user.id;
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) {}
  if (!prefs || typeof prefs !== 'object') prefs = {};
  if (!Number.isInteger(prefs.start) || !Number.isInteger(prefs.end) || prefs.start < 0 || prefs.end > 24 || prefs.end <= prefs.start) {
    prefs.start = 9; prefs.end = 17;
  }
  const query = new URLSearchParams(location.search);
  if (query.has('calling_start')) prefs.start = Number(query.get('calling_start'));
  if (query.has('calling_end')) prefs.end = Number(query.get('calling_end'));
  Alpine.store('calling', {
    zones: {}, now: 0, serverAt: 0, syncedWall: 0, syncedPerf: 0, synced: false,
    refreshing: false, error: '', windowError: '', start: prefs.start ?? 9, end: prefs.end ?? 17,
    format: prefs.format === '24' ? '24' : '12',
    get fresh() {
      return this.synced && this.now - this.serverAt < 120000 &&
        Date.now() - this.syncedWall < 120000 &&
        Math.abs((Date.now() - this.syncedWall) - (performance.now() - this.syncedPerf)) < 5000;
    },
    async init() {
      await this.refresh();
      setInterval(() => this.tick(), 1000);
      setInterval(() => this.refresh(), 60000);
      const resume = () => { if (!document.hidden) { this.synced = false; this.refresh(); } };
      document.addEventListener('visibilitychange', resume);
      window.addEventListener('focus', resume);
      window.addEventListener('online', resume);
    },
    tick() {
      this.now = this.serverAt + Math.max(0, performance.now() - this.syncedPerf);
      if (this.synced && !this.fresh) { this.synced = false; this.refresh(); }
    },
    persist() {
      if (this.end <= this.start) return;
      try { localStorage.setItem(key, JSON.stringify({start:this.start,end:this.end,format:this.format})); } catch (_) {}
    },
    setFormat(value) { this.format = value; this.persist(); },
    hourLabel(hour) {
      if (this.format === '24') return `${String(hour % 24).padStart(2,'0')}:00${hour === 24 ? ' (next day)' : ''}`;
      return `${hour % 12 || 12}:00 ${hour % 24 < 12 ? 'AM' : 'PM'}${hour === 24 ? ' (next day)' : ''}`;
    },
    saveWindow() {
      this.start = Number(this.start); this.end = Number(this.end);
      if (this.end <= this.start) { this.windowError = 'Closing time must be after opening time.'; return; }
      this.windowError = ''; this.persist();
    },
    async refresh() {
      if (this.refreshing) return;
      this.refreshing = true;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      try {
        const sent = performance.now();
        const r = await fetch('/api/calling-times', {cache:'no-store', signal:controller.signal});
        if (!r.ok) throw new Error();
        const data = await r.json();
        const received = performance.now();
        const server = Date.parse(data.at);
        if (!Number.isFinite(server) || !data.zones || received - sent > 8000) throw new Error();
        this.zones = data.zones;
        this.serverAt = server + (received - sent) / 2;
        this.syncedPerf = received; this.syncedWall = Date.now();
        this.now = this.serverAt; this.synced = true; this.error = '';
      } catch (_) {
        this.synced = false;
        this.error = 'Live time unavailable. Reconnect or retry before relying on calling-hour guidance.';
      } finally { clearTimeout(timer); this.refreshing = false; }
    },
    indiaNow() {
      return this.fresh ? callingTimes.parts(this.now,330,this.format,true).text + ' IST' : 'Waiting for live time…';
    },
    info(zone) {
      const entry = this.zones[zone];
      if (!entry || !this.fresh) {
        const text = !zone ? 'Time zone needs confirmation' : 'Waiting for live time…';
        return {text,shortText:text,clock:text,status:'Time unavailable',good:false,kind:'unknown'};
      }
      const local = callingTimes.parts(this.now,entry.offset,this.format,true);
      const status = callingTimes.status(local,this.start,this.end);
      return {clock:local.text, text:`${local.text} · ${entry.name} · ${status}`,status,
        shortText:`${callingTimes.parts(this.now,entry.offset,this.format).text} · ${entry.name} · ${status}`,
        good:status === 'Within calling hours',
        kind:status === 'Within calling hours' ? 'open' : status === 'Closing soon' ? 'closing' : 'outside'};
    },
    link(zone) {
      return '/prospects?' + new URLSearchParams({team_view:'available',calling_zone:zone,calling_start:this.start,calling_end:this.end});
    },
    indiaWindow(zone) {
      const entry = this.zones[zone];
      if (!entry || !this.fresh) return 'Waiting for live time…';
      const convert = hour => {
        const minutes = hour * 60 - entry.offset + 330;
        const day = Math.floor(minutes / 1440);
        const n = ((minutes % 1440) + 1440) % 1440;
        const h = Math.floor(n / 60), m = String(n % 60).padStart(2,'0');
        const time = this.format === '24' ? `${String(h).padStart(2,'0')}:${m}` : `${h % 12 || 12}:${m} ${h < 12 ? 'AM' : 'PM'}`;
        return time + (day > 0 ? ' (next day)' : day < 0 ? ' (previous day)' : '');
      };
      return `${convert(this.start)}–${convert(this.end)} IST`;
    }
  });
});
