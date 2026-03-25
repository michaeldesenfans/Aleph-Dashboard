const API_BASE = `${window.location.origin}/api/v2`;
const state = {
  competitor: '',
  window: '30d',
  headlines: [],
  currentSlide: 0,
  carouselTimer: null,
};

const $outageRail = document.querySelector('.outage-list');
const $outageCount = document.getElementById('outageCount');
const $headlineCarousel = document.querySelector('.carousel');
const $headlinePips = document.querySelector('.nav-pips');
const $headlinePrev = document.querySelector('#headlinePrev') || document.querySelectorAll('.nav-btn')[0];
const $headlineNext = document.querySelector('#headlineNext') || document.querySelectorAll('.nav-btn')[1];
const $filters = document.querySelector('.filter-pills');
const $feed = document.querySelector('.feed-scroll');
const $macro = document.querySelector('.macro-card');
const $momentumList = document.querySelector('.ms-list');
const $signals = document.querySelector('.signals-list');
const $watchlist = document.querySelector('.watchlist');
const $momentumMeta = document.getElementById('momentumMeta');
const $signalsMeta = document.getElementById('signalsMeta');
const $updated = document.getElementById('synthesisUpdated');
const $pipelineBadgeLabel = document.getElementById('pipelineBadgeLabel');
const $runButton = document.getElementById('runPipelineBtn') || document.querySelector('.run-btn');
const $kpiEvents = document.getElementById('kpiEvents');
const $kpiCritical = document.getElementById('kpiCritical');
const $kpiHigh = document.getElementById('kpiHigh');
const $kpi24h = document.getElementById('kpi24h');

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

function formatRelativeTime(value) {
  if (!value) return 'unknown';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return 'unknown';
  const diffMs = Date.now() - dt.getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function renderStats(stats) {
  $kpiEvents.textContent = String(stats.events_24h ?? 0);
  $kpiCritical.textContent = String(stats.critical_24h ?? 0);
  $kpiHigh.textContent = String(stats.high_24h ?? 0);
  $kpi24h.textContent = String(stats.events_24h ?? 0);
  $pipelineBadgeLabel.textContent = stats.pipeline_running ? 'PIPELINE RUNNING' : 'PIPELINE LIVE';
}

function providerClass(slug) {
  return `comp-${slug || 'neutral'}`;
}

function statusVisual(stateValue) {
  if (stateValue === 'outage') return { dot: 'active', label: 'active-label', text: 'OUTAGE' };
  if (stateValue === 'degraded') return { dot: 'degraded', label: 'degraded-label', text: 'DEGRADED' };
  if (stateValue === 'clear') return { dot: 'resolved', label: 'resolved-label', text: 'CLEAR' };
  return { dot: 'resolved', label: 'resolved-label', text: 'UNKNOWN' };
}

function renderStatus(payload) {
  const items = payload.items || [];
  $outageCount.textContent = `${payload.active_count || 0} active`;
  $outageRail.innerHTML = items.map(item => {
    const visual = statusVisual(item.state);
    const desc = escapeHtml(item.latest_incident_title || (item.state === 'clear' ? 'No active incidents reported' : 'No authoritative incident detail'));
    const url = item.latest_incident_url || '';
    const tag = url ? 'a' : 'div';
    const href = url ? ` href="${url}" target="_blank" rel="noreferrer"` : '';
    const srcLabel = url ? 'Source' : escapeHtml((item.source_coverage || 'none').toUpperCase());
    return `
      <${tag} class="outage-row"${href}>
        <span class="outage-dot ${visual.dot}"></span>
        <span class="outage-csp">${escapeHtml(item.provider)}</span>
        <span class="outage-desc">${desc}</span>
        <span class="outage-meta">
          <span class="outage-status-label ${visual.label}">${visual.text}</span>
          <span class="outage-time">${escapeHtml(item.freshness_label || 'unknown')}</span>
          <span class="outage-src">${srcLabel}</span>
        </span>
      </${tag}>
    `;
  }).join('');
}

function heroClass(eventType) {
  if (eventType === 'outage') return 'outage';
  if (eventType === 'funding') return 'capital';
  if (eventType === 'policy') return 'policy';
  return 'launch';
}

function tagClass(eventType) {
  if (eventType === 'outage') return 'tag-outage';
  if (eventType === 'funding') return 'tag-capital';
  if (eventType === 'policy') return 'tag-policy';
  return 'tag-launch';
}

function renderHeadlines(items) {
  state.headlines = items || [];
  state.currentSlide = 0;
  if (!state.headlines.length) {
    $headlineCarousel.innerHTML = '<div class="slide active"><div class="hero-card launch"><div class="hero-headline">No high-priority headlines yet</div></div></div>';
    $headlinePips.innerHTML = '';
    return;
  }

  $headlineCarousel.innerHTML = state.headlines.map((item, idx) => `
    <div class="slide ${idx === 0 ? 'active' : ''}">
      <div class="hero-card ${heroClass(item.event_type)}">
        <div class="severity-badge ${(item.severity || '').toLowerCase()}">${escapeHtml((item.severity || '').toUpperCase())}</div>
        <div class="hero-headline">${escapeHtml(item.headline)}</div>
        <div class="hero-summary">${escapeHtml(item.summary || '')}</div>
        <div class="hero-foot">
          <span class="hero-source">${escapeHtml(item.source_name || item.provider || '')} • ${escapeHtml(item.relative_time || '')}</span>
          <div class="tag-row">
            <span class="tag ${tagClass(item.event_type)}">${escapeHtml((item.event_type || 'news').toUpperCase())}</span>
            <span class="tag tag-neutral">${escapeHtml(item.provider || 'Industry')}</span>
          </div>
        </div>
      </div>
    </div>
  `).join('');

  $headlinePips.innerHTML = state.headlines.map((_, idx) => `<div class="pip ${idx === 0 ? 'active' : ''}" data-idx="${idx}"></div>`).join('');
  $headlinePips.querySelectorAll('.pip').forEach(pip => {
    pip.addEventListener('click', () => showSlide(Number(pip.dataset.idx)));
  });

  resetCarouselTimer();
}

function showSlide(index) {
  const slides = $headlineCarousel.querySelectorAll('.slide');
  const pips = $headlinePips.querySelectorAll('.pip');
  if (!slides.length) return;
  state.currentSlide = (index + slides.length) % slides.length;
  slides.forEach((slide, idx) => slide.classList.toggle('active', idx === state.currentSlide));
  pips.forEach((pip, idx) => pip.classList.toggle('active', idx === state.currentSlide));
}

function resetCarouselTimer() {
  clearInterval(state.carouselTimer);
  state.carouselTimer = setInterval(() => showSlide(state.currentSlide + 1), 9000);
}

window.prevSlide = () => { showSlide(state.currentSlide - 1); resetCarouselTimer(); };
window.nextSlide = () => { showSlide(state.currentSlide + 1); resetCarouselTimer(); };

$headlinePrev?.addEventListener('click', window.prevSlide);
$headlineNext?.addEventListener('click', window.nextSlide);

function renderFilters(providers) {
  const items = [{ slug: '', provider: 'All' }, ...providers.map(item => ({ slug: item.slug, provider: item.provider }))];
  $filters.innerHTML = items.map(item => `
    <button class="pill ${item.slug === state.competitor ? 'active' : ''}" data-slug="${item.slug}">
      ${escapeHtml(item.provider)}
    </button>
  `).join('');
  $filters.querySelectorAll('.pill').forEach(button => {
    button.addEventListener('click', async () => {
      state.competitor = button.dataset.slug || '';
      renderFilters(providers);
      await loadEvents();
    });
  });
}

function renderEvents(payload) {
  const items = payload.items || [];
  if (!items.length) {
    $feed.innerHTML = '<div class="event-card"><div class="event-headline">No tactical signals for the current filter.</div></div>';
    return;
  }
  $feed.innerHTML = items.map(item => `
    <div class="event-card" data-url="${escapeHtml(item.source_url || '')}">
      <div class="event-meta-row">
        <span class="event-competitor">
          <span class="comp-dot ${providerClass(item.slug)}"></span>${escapeHtml(item.provider || 'Industry')}
        </span>
        <span>${escapeHtml(item.relative_time || '')}</span>
      </div>
      <div class="event-headline">${escapeHtml(item.headline)}</div>
      <div class="tag-row">
        <span class="tag ${tagClass(item.event_type)}">${escapeHtml((item.event_type || 'news').toUpperCase())}</span>
        ${(item.tags || []).slice(0, 2).map(tag => `<span class="tag tag-neutral">${escapeHtml(tag)}</span>`).join('')}
      </div>
    </div>
  `).join('');
  $feed.querySelectorAll('.event-card').forEach(card => {
    const url = card.dataset.url;
    if (url) {
      card.addEventListener('click', () => window.open(url, '_blank', 'noopener'));
    }
  });
}

function renderTrend(trend) {
  if (!trend || !trend.title) {
    $macro.innerHTML = '<div class="macro-title">Macro Trend unavailable</div>';
    return;
  }
  $macro.innerHTML = `
    <div class="macro-head">
      <div class="macro-icon">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="white">
          <path d="M1 10L5 6L8 9L13 3" stroke="white" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="13" cy="3" r="1.5" fill="white"/>
        </svg>
      </div>
      <div class="macro-title">${escapeHtml(trend.title)}</div>
    </div>
    <div class="macro-body">${escapeHtml(trend.narrative || '')}</div>
    <div class="macro-meta">
      <span class="tag tag-neutral">Confidence: ${Math.round((trend.confidence || 0) * 100)}%</span>
      <span class="tag tag-neutral">Window: ${escapeHtml(formatRelativeTime(trend.window_start))} → now</span>
      <span class="tag tag-neutral">Impact: ${escapeHtml((trend.impact_level || 'medium').toUpperCase())}</span>
      <span class="tag tag-neutral">AI Generated: ${escapeHtml(formatRelativeTime(trend.generated_at))}</span>
    </div>
  `;
}

function attentionClass(label) {
  const upper = (label || '').toUpperCase();
  if (upper === 'SURGING') return 'attn-surging';
  if (upper === 'RISING') return 'attn-rising';
  if (upper === 'EMERGING') return 'attn-emerging';
  return 'attn-active';
}

function renderMomentum(momentum) {
  const themes = momentum.themes || [];
  $momentumMeta.textContent = `${themes.length} THEMES TRACKED`;
  if (!themes.length) {
    $momentumList.innerHTML = '<div class="ms-card"><div class="ms-subject">No momentum themes available</div></div>';
    return;
  }
  $momentumList.innerHTML = themes.map(theme => `
    <div class="ms-card">
      <div class="ms-top">
        <div class="ms-subject">${escapeHtml(theme.subject)}</div>
        <span class="attn-badge ${attentionClass(theme.attention)}">${escapeHtml(theme.attention)}</span>
      </div>
      <div class="ms-csps">
        ${(theme.competitors || []).map(name => `<span class="csp-tag">${escapeHtml(name)}</span>`).join('')}
      </div>
      <div class="ms-blurb">${escapeHtml(theme.blurb || '')}</div>
      ${renderSources(theme.sources)}
    </div>
  `).join('');

  const watchlist = momentum.watchlist || [];
  $watchlist.innerHTML = watchlist.map(item => `
    <div class="watchlist-row">
      <div class="watchlist-name">${escapeHtml(item.name)}</div>
      <div class="watchlist-desc">${escapeHtml(item.summary || '')}</div>
      <div class="watchlist-stat">
        <div class="stat-num ${item.trend === 'up' ? 'trend-up' : ''}">${escapeHtml(String(item.event_count || 0))}</div>
        <div class="stat-label">events/${escapeHtml(String(momentum.days || 30))}d</div>
      </div>
    </div>
  `).join('');
}

const SIGNAL_ICONS = {
  threat: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2L12 11H2L7 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><line x1="7" y1="5.5" x2="7" y2="8.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><circle cx="7" cy="10" r="0.6" fill="currentColor"/></svg>',
  opportunity: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.4"/><path d="M7 4.5V7L9 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  regulatory: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="2.5" y="1.5" width="9" height="11" rx="1.5" stroke="currentColor" stroke-width="1.4"/><line x1="5" y1="5" x2="9" y2="5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><line x1="5" y1="7.5" x2="9" y2="7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><line x1="5" y1="10" x2="7.5" y2="10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  market_shift: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 10L6 6L9 8.5L12 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 4H12V6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
};
const SRC_ARROW_SVG = '<svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1 8L8 1M8 1H4M8 1V5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';

function signalClass(type) {
  if (type === 'threat') return ['icon-threat', 'type-threat'];
  if (type === 'opportunity') return ['icon-opportunity', 'type-opportunity'];
  if (type === 'regulatory') return ['icon-regulatory', 'type-regulatory'];
  return ['icon-shift', 'type-shift'];
}

function safeHostname(url) {
  try { return new URL(url).hostname; } catch { return url; }
}

function renderSources(sources) {
  if (!sources || !sources.length) return '';
  return `<div class="ms-sources">${sources.map(s =>
    `<a class="src-link" href="${s.url}" target="_blank" rel="noreferrer">${SRC_ARROW_SVG} ${escapeHtml(s.name || safeHostname(s.url))}</a>`
  ).join('')}</div>`;
}

function renderSignals(items) {
  $signalsMeta.textContent = `${items.length} ACTIVE`;
  if (!items.length) {
    $signals.innerHTML = '<div class="signal-card"><div class="signal-body"><div class="signal-text">No strategic signals available.</div></div></div>';
    return;
  }
  $signals.innerHTML = items.map(item => {
    const [iconClass, typeClass] = signalClass(item.signal_type);
    const svg = SIGNAL_ICONS[item.signal_type] || SIGNAL_ICONS.market_shift;
    const sources = (item.sources || []);
    const srcHtml = sources.length ? `<div class="signal-sources">${sources.map(s =>
      `<a class="src-link" href="${s.url}" target="_blank" rel="noreferrer">${SRC_ARROW_SVG} ${escapeHtml(s.name || safeHostname(s.url))}</a>`
    ).join('')}</div>` : '';
    return `
      <div class="signal-card">
        <div class="signal-icon-wrap ${iconClass}">${svg}</div>
        <div class="signal-body">
          <div class="signal-type ${typeClass}">${escapeHtml((item.signal_type || '').replace(/_/g, ' ').toUpperCase())}</div>
          <div class="signal-text">${escapeHtml(item.analysis || item.title || '')}</div>
          ${srcHtml}
          <div class="signal-foot">
            ${escapeHtml(item.relative_time || '')}
            <span class="confidence-bar">Confidence ${Math.round((item.confidence || 0) * 100)}%</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderUpdated(value) {
  $updated.textContent = `UPDATED ${formatRelativeTime(value).toUpperCase()}`;
}

async function loadEvents() {
  const qs = new URLSearchParams({ limit: '30' });
  if (state.competitor) qs.set('competitor', state.competitor);
  const events = await fetchJson(`/events?${qs.toString()}`);
  renderEvents(events);
}

async function loadDashboard() {
  try {
    const [stats, status, headlines, momentum, trend, signals] = await Promise.all([
      fetchJson('/stats'),
      fetchJson('/csp-status'),
      fetchJson('/headlines'),
      fetchJson(`/momentum?window=${state.window}`),
      fetchJson('/synthesis/trend'),
      fetchJson('/synthesis/signals'),
    ]);

    renderStats(stats);
    renderStatus(status);
    renderHeadlines(headlines.items || []);
    renderFilters(status.items || []);
    renderTrend(trend);
    renderMomentum(momentum);
    renderSignals(signals.items || []);
    renderUpdated(stats.last_updated_at || trend.generated_at);
    await loadEvents();
  } catch (error) {
    console.error('Dashboard load failed', error);
  }
}

async function pollPipelineCompletion() {
  const health = await fetchJson('/health');
  if (!health.pipeline_running) {
    $runButton.disabled = false;
    $runButton.textContent = 'Run Pipeline';
    await loadDashboard();
    return;
  }
  window.setTimeout(pollPipelineCompletion, 3000);
}

$runButton?.addEventListener('click', async () => {
  $runButton.disabled = true;
  $runButton.textContent = 'Running...';
  const response = await fetch(`${window.location.origin}/api/run`, { method: 'POST' });
  if (response.status === 409) {
    await pollPipelineCompletion();
    return;
  }
  await pollPipelineCompletion();
});

loadDashboard();
window.setInterval(loadDashboard, 60000);
