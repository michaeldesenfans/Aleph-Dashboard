/**
 * Aleph Cloud — Competitive Intelligence Dashboard
 * app.js — API polling, DOM rendering, Chart.js visualizations
 * SOP: architecture/frontend_sop.md
 */

// ── Config ────────────────────────────────────────────────────────────────────
const API_BASE        = 'http://localhost:8080';
const POLL_INTERVAL   = 60_000;   // ms — refetch events every 60s
const STALE_THRESHOLD = 90_000;   // ms — live indicator turns red after 90s

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  competitor: '',
  category:   '',
  severity:   '',
  hours:      0,
  events:     [],
  seenIds:    new Set(),
  lastFetch:  null,
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $feed         = document.getElementById('eventFeed');
const $feedCount    = document.getElementById('feedCount');
const $lastUpdated  = document.getElementById('lastUpdated');
const $liveIndicator= document.getElementById('liveIndicator');
const $statTotal    = document.getElementById('statTotal');
const $statCritical = document.getElementById('statCritical');
const $statHigh     = document.getElementById('statHigh');
const $statToday    = document.getElementById('statToday');
const $statPipeline = document.getElementById('statPipeline');
const $runBtn       = document.getElementById('runPipelineBtn');

// ── Charts ────────────────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
};

const COMPETITOR_COLORS = {
  AWS: '#ff9900', Azure: '#0078d4', GCP: '#4285f4',
  OVHcloud: '#2a6eb5', Scaleway: '#7c3aed', Hetzner: '#d50c2d',
  DigitalOcean: '#0080ff', CoreWeave: '#9333ea', IONOS: '#4a90d9', Other: '#484f58',
};

let competitorChart = null;
let categoryChart   = null;

function initCharts() {
  const chartOpts = {
    ...CHART_DEFAULTS,
    scales: {
      x: { ticks: { color: '#484f58', font: { size: 10 } }, grid: { color: '#1a1f25' } },
      y: { ticks: { color: '#484f58', font: { size: 10 } }, grid: { color: '#1a1f25' }, beginAtZero: true },
    },
  };

  competitorChart = new Chart(document.getElementById('competitorChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 3 }] },
    options: { ...chartOpts, indexAxis: 'y' },
  });

  categoryChart = new Chart(document.getElementById('categoryChart'), {
    type: 'doughnut',
    data: {
      labels: [],
      datasets: [{
        data: [],
        backgroundColor: ['#ff3b3b','#ff8c00','#ffd700','#4f8ef7','#22c55e'],
        borderWidth: 0,
        hoverOffset: 4,
      }],
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#8b949e', font: { size: 10 }, boxWidth: 10, padding: 8 },
        },
      },
    },
  });
}

function updateCharts(events) {
  // Competitor bar chart
  const compCounts = {};
  events.forEach(e => { compCounts[e.competitor] = (compCounts[e.competitor] || 0) + 1; });
  const compLabels = Object.keys(compCounts).sort((a, b) => compCounts[b] - compCounts[a]);

  competitorChart.data.labels = compLabels;
  competitorChart.data.datasets[0].data = compLabels.map(l => compCounts[l]);
  competitorChart.data.datasets[0].backgroundColor = compLabels.map(l => COMPETITOR_COLORS[l] || '#484f58');
  competitorChart.update('none');

  // Category donut chart
  const CATEGORIES = ['Outage', 'Funding', 'Product Launch', 'Policy', 'News'];
  const catCounts = {};
  events.forEach(e => { catCounts[e.category] = (catCounts[e.category] || 0) + 1; });

  categoryChart.data.labels = CATEGORIES.filter(c => catCounts[c]);
  categoryChart.data.datasets[0].data = CATEGORIES.filter(c => catCounts[c]).map(c => catCounts[c]);
  categoryChart.update('none');
}

// ── Event Card Rendering ──────────────────────────────────────────────────────
function badgeClass(competitor) {
  const map = {
    AWS: 'badge-aws', Azure: 'badge-azure', GCP: 'badge-gcp',
    OVHcloud: 'badge-ovhcloud', Scaleway: 'badge-scaleway', Hetzner: 'badge-hetzner',
    DigitalOcean: 'badge-digitalocean', CoreWeave: 'badge-coreweave', IONOS: 'badge-ionos',
  };
  return map[competitor] || 'badge-other';
}

function formatRelativeTime(isoString) {
  const then = new Date(isoString);
  const diffMs = Date.now() - then.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1)   return 'just now';
  if (diffMins < 60)  return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24)   return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

function renderCard(event, isNew = false) {
  const tags = Array.isArray(event.tags) ? event.tags : [];
  const severityLower = (event.severity || 'low').toLowerCase();

  const card = document.createElement('article');
  card.className = `event-card ${severityLower}${isNew ? ' new' : ''}`;
  card.dataset.id = event.id;

  card.innerHTML = `
    <div class="card-meta">
      <span class="competitor-badge ${badgeClass(event.competitor)}">${event.competitor}</span>
      <span class="category-tag">${event.category}</span>
      <span class="card-timestamp">${formatRelativeTime(event.timestamp)}</span>
      <span class="severity-tag sev-${severityLower}">${event.severity.toUpperCase()}</span>
    </div>
    <div class="card-headline">${escapeHtml(event.headline)}</div>
    ${event.summary ? `<div class="card-summary">${escapeHtml(event.summary)}</div>` : ''}
    ${event.strategic_impact ? `<div class="card-impact">${escapeHtml(event.strategic_impact)}</div>` : ''}
    ${tags.length ? `<div class="card-tags">${tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
  `;

  // Click to open source URL
  if (event.source_url) {
    card.addEventListener('click', () => window.open(event.source_url, '_blank', 'noopener'));
  }

  return card;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function renderFeed(events) {
  const newIds = new Set(events.map(e => e.id));
  const newEvents = events.filter(e => !state.seenIds.has(e.id));

  if (events.length === 0) {
    $feed.innerHTML = '<div class="empty-state">No events match the current filters</div>';
    $feedCount.textContent = '0 events';
    return;
  }

  // Full re-render on filter change, incremental on poll
  const isFilterChange = state.events.length === 0 || newIds.size === events.length;

  if (isFilterChange) {
    $feed.innerHTML = '';
    events.forEach(e => $feed.appendChild(renderCard(e, false)));
  } else {
    // Prepend new events
    newEvents.forEach(e => {
      $feed.insertBefore(renderCard(e, true), $feed.firstChild);
    });
  }

  newEvents.forEach(e => state.seenIds.add(e.id));
  $feedCount.textContent = `${events.length} event${events.length !== 1 ? 's' : ''}`;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats(events, pipeline) {
  const now = Date.now();
  const oneDayAgo = now - 86_400_000;

  $statTotal.textContent    = events.length;
  $statCritical.textContent = events.filter(e => e.severity === 'Critical').length;
  $statHigh.textContent     = events.filter(e => e.severity === 'High').length;
  $statToday.textContent    = events.filter(e => new Date(e.timestamp).getTime() > oneDayAgo).length;
  $statPipeline.textContent = pipeline?.running ? 'running' : 'idle';
}

// ── Live indicator ────────────────────────────────────────────────────────────
function updateLiveIndicator() {
  if (!state.lastFetch) return;
  const stale = Date.now() - state.lastFetch > STALE_THRESHOLD;
  $liveIndicator.classList.toggle('stale', stale);
  $lastUpdated.textContent = `Updated ${formatRelativeTime(new Date(state.lastFetch).toISOString())}`;
}

// ── API calls ─────────────────────────────────────────────────────────────────
function buildQueryString() {
  const params = new URLSearchParams();
  if (state.competitor) params.set('competitor', state.competitor);
  if (state.category)   params.set('category', state.category);
  if (state.severity)   params.set('severity', state.severity);
  if (state.hours)      params.set('hours', state.hours);
  params.set('limit', '100');
  return params.toString();
}

async function fetchEvents() {
  try {
    const res = await fetch(`${API_BASE}/api/events?${buildQueryString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.events   = data.events || [];
    state.lastFetch = Date.now();

    renderFeed(state.events);
    updateStats(state.events, data.pipeline);
    updateCharts(state.events);
    updateLiveIndicator();
  } catch (err) {
    console.error('fetchEvents error:', err);
    $liveIndicator.classList.add('stale');
  }
}

async function triggerPipeline() {
  $runBtn.disabled = true;
  $runBtn.textContent = '⟳ Running...';
  try {
    const res = await fetch(`${API_BASE}/api/run`, { method: 'POST' });
    if (res.status === 409) {
      console.log('Pipeline already running');
    }
    // Poll for completion
    const poll = setInterval(async () => {
      const status = await fetch(`${API_BASE}/api/status`).then(r => r.json());
      if (!status.pipeline.running) {
        clearInterval(poll);
        $runBtn.disabled = false;
        $runBtn.textContent = '▶ Run Pipeline';
        await fetchEvents();
      }
    }, 3000);
  } catch (err) {
    console.error('triggerPipeline error:', err);
    $runBtn.disabled = false;
    $runBtn.textContent = '▶ Run Pipeline';
  }
}

// ── Filter logic ──────────────────────────────────────────────────────────────
function setupFilters() {
  function bindFilterGroup(containerId, stateKey) {
    const container = document.getElementById(containerId);
    container.addEventListener('click', e => {
      const chip = e.target.closest('.chip');
      if (!chip) return;

      container.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state[stateKey] = chip.dataset.value;
      state.seenIds.clear();
      state.events = [];
      fetchEvents();
    });
  }

  bindFilterGroup('competitorFilters', 'competitor');
  bindFilterGroup('categoryFilters',   'category');
  bindFilterGroup('severityFilters',   'severity');
  bindFilterGroup('timeFilters',       'hours');

  $runBtn.addEventListener('click', triggerPipeline);
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  initCharts();
  setupFilters();
  fetchEvents();

  // Auto-refresh
  setInterval(fetchEvents, POLL_INTERVAL);

  // Update timestamps every 30s (relative time display)
  setInterval(() => {
    document.querySelectorAll('.card-timestamp[data-iso]').forEach(el => {
      el.textContent = formatRelativeTime(el.dataset.iso);
    });
    updateLiveIndicator();
  }, 30_000);
}

init();
