const API_BASE = (window.__ENV__?.API_BASE_URL || window.location.origin) + '/api/v2';
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

// Store trend data for expand/collapse
state.trendData = null;
state.trendExpanded = false;

function renderDatapoints(datapoints) {
  if (!datapoints || !datapoints.length) return '';
  return `<div class="macro-datapoints">${datapoints.map(dp =>
    `<span class="datapoint-chip">
      <span class="dp-value">${escapeHtml(String(dp.value || ''))}</span>
      <span class="dp-label">${escapeHtml(dp.label || '')}</span>
      ${dp.source ? `<span class="dp-source">${escapeHtml(dp.source)}</span>` : ''}
    </span>`
  ).join('')}</div>`;
}

function renderTrend(trend) {
  if (!trend || !trend.title) {
    $macro.innerHTML = '<div class="macro-title">Macro Trend unavailable</div>';
    return;
  }
  state.trendData = trend;
  state.trendExpanded = false;

  const headlineTrend = trend.headline_trend
    ? `<div class="macro-thesis">${escapeHtml(trend.headline_trend)}</div>` : '';
  const whyItMatters = trend.why_it_matters
    ? `<div class="macro-why">${escapeHtml(trend.why_it_matters)}</div>` : '';
  const keyDriver = trend.key_driver
    ? `<span class="tag tag-driver">KEY DRIVER: ${escapeHtml(trend.key_driver)}</span>` : '';

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
    ${headlineTrend}
    ${whyItMatters}
    <div class="macro-body">${escapeHtml(trend.narrative || '')}</div>
    ${renderDatapoints(trend.key_datapoints)}
    <div class="macro-meta">
      ${keyDriver}
      <span class="tag tag-neutral">Confidence: ${Math.round((trend.confidence || 0) * 100)}%</span>
      <span class="tag tag-neutral">Window: ${escapeHtml(formatRelativeTime(trend.window_start))} → now</span>
      <span class="tag tag-neutral">Impact: ${escapeHtml((trend.impact_level || 'medium').toUpperCase())}</span>
      <span class="tag tag-neutral">AI Generated: ${escapeHtml(formatRelativeTime(trend.generated_at))}</span>
    </div>
    <div class="macro-expand-toggle" id="macroExpandToggle">CLICK TO EXPLORE ▾</div>
    <div class="macro-article" id="macroArticle"></div>
  `;

  document.getElementById('macroExpandToggle')?.addEventListener('click', toggleTrendArticle);
}

function formatMarkdown(md) {
  if (!md) return '';
  let html = escapeHtml(md);
  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  // Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, match => `<ul>${match}</ul>`);
  // Paragraphs (double newline)
  html = html.split(/\n\n+/).map(block => {
    const trimmed = block.trim();
    if (trimmed.startsWith('<h2>') || trimmed.startsWith('<h3>') || trimmed.startsWith('<ul>')) return trimmed;
    if (!trimmed) return '';
    return `<p>${trimmed}</p>`;
  }).join('\n');
  // Single newlines within paragraphs
  html = html.replace(/<p>([^<]*)\n([^<]*)<\/p>/g, '<p>$1<br>$2</p>');
  return html;
}

function renderArticleWithSources(sections) {
  if (!sections || !sections.length) return '';
  return sections.map(section => {
    let html = formatMarkdown(section.body_md || '');
    // Inject claim highlights with tooltips
    const claims = section.claims || [];
    for (const claim of claims) {
      const claimText = escapeHtml(claim.text || '');
      if (!claimText) continue;
      const sourceName = escapeHtml(claim.source_name || '');
      const sourceUrl = claim.source_url || '';
      const tooltipHtml = sourceUrl
        ? `<div class="claim-tooltip">
            <div class="claim-tooltip-source">${sourceName}</div>
            <a class="claim-tooltip-url" href="${sourceUrl}" target="_blank" rel="noreferrer">${escapeHtml(safeHostname(sourceUrl))}</a>
          </div>`
        : `<div class="claim-tooltip"><div class="claim-tooltip-source">${sourceName}</div></div>`;
      const replacement = `<span class="claim-highlight">${claimText}${tooltipHtml}</span>`;
      // Replace first occurrence only
      const idx = html.indexOf(claimText);
      if (idx !== -1) {
        html = html.substring(0, idx) + replacement + html.substring(idx + claimText.length);
      }
    }
    return `<h2>${escapeHtml(section.heading || '')}</h2>${html}`;
  }).join('');
}

// ── Component A: Key Evidence Timeline ──
function renderEvidenceTimeline(keyEvidence, windowStart, windowEnd) {
  if (!keyEvidence || !keyEvidence.length) return '';
  const colorMap = {
    launch: '#00d4ff', funding: '#00ffc8', policy: '#fbbf24',
    outage: '#ef4444', partnership: '#8b5cf6', pricing: '#d946ef', news: '#6b7280',
  };
  const startDate = new Date(windowStart || keyEvidence[keyEvidence.length - 1].detected_at);
  const endDate = new Date(windowEnd || Date.now());
  const range = Math.max(endDate - startDate, 86400000);
  const fmtDate = (d) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  const w = 700, h = 90, pad = 20, dotR = 6;
  const axisY = 35;
  let svgContent = '';
  // Axis line
  svgContent += `<line x1="${pad}" y1="${axisY}" x2="${w - pad}" y2="${axisY}" stroke="rgba(0,212,255,0.15)" stroke-width="1"/>`;
  // Axis labels
  svgContent += `<text x="${pad}" y="${axisY + 20}" class="evidence-label">${fmtDate(startDate)}</text>`;
  svgContent += `<text x="${w - pad}" y="${axisY + 20}" class="evidence-label" text-anchor="end">${fmtDate(endDate)}</text>`;

  keyEvidence.forEach((ev, i) => {
    const evDate = new Date(ev.detected_at);
    const pct = Math.min(Math.max((evDate - startDate) / range, 0), 1);
    const x = pad + pct * (w - 2 * pad);
    const color = colorMap[ev.event_type] || '#00d4ff';
    const labelY = axisY - 14;
    // Stagger labels to avoid overlap
    const labelOffset = (i % 2 === 0) ? -28 : 32;
    const tickEnd = (i % 2 === 0) ? axisY - 10 : axisY + 10;

    // Tick line
    svgContent += `<line x1="${x}" y1="${axisY}" x2="${x}" y2="${tickEnd}" stroke="${color}" stroke-width="0.5" opacity="0.4"/>`;
    // Dot
    svgContent += `<circle cx="${x}" cy="${axisY}" r="${dotR}" fill="${color}" class="evidence-dot"
      data-idx="${i}" onclick="window.open('${ev.source_url}','_blank')">
      <title>${escapeHtml(ev.title)}\n${ev.competitor} | ${ev.severity} | ${fmtDate(evDate)}</title>
    </circle>`;
    // Label below/above
    const textY = axisY + labelOffset;
    const comp = escapeHtml(ev.competitor || '').substring(0, 12);
    const label = escapeHtml(ev.short_label || '').substring(0, 25);
    svgContent += `<text x="${x}" y="${textY}" text-anchor="middle" class="evidence-label">${comp}</text>`;
    svgContent += `<text x="${x}" y="${textY + 10}" text-anchor="middle" class="evidence-label" style="font-size:7px;opacity:0.7;">${label}</text>`;
  });

  return `<div class="evidence-timeline">
    <div class="evidence-timeline-label">KEY EVIDENCE -- 30 DAY WINDOW</div>
    <svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" style="display:block;overflow:visible;">${svgContent}</svg>
  </div>`;
}

// ── Component B: Confidence Decomposition ──
function renderConfidenceDecomposition(data) {
  if (!data) return '';
  const pct = Math.round((data.overall_confidence || 0.5) * 100);
  const recency = data.evidence_recency || {};
  const coverage = data.coverage_breadth || {};
  const newestLabel = recency.newest_days_ago != null ? `${recency.newest_days_ago}d ago` : '?';
  const oldestLabel = recency.oldest_days_ago != null ? `${recency.oldest_days_ago}d ago` : '?';
  const recencyPct = Math.max(100 - (recency.newest_days_ago || 0) * 5, 10);
  const coveragePct = Math.round((coverage.covered || 0) / Math.max(coverage.total_tracked || 17, 1) * 100);

  const metrics = [
    { label: 'Source Quality', value: `Tier 1 (${data.source_quality_pct || 0}%)`, pct: data.source_quality_pct || 0 },
    { label: 'Evidence Recency', value: `${newestLabel} - ${oldestLabel}`, pct: recencyPct },
    { label: 'Coverage Breadth', value: `${coverage.covered || 0} / ${coverage.total_tracked || 17} comps`, pct: coveragePct },
    { label: 'Signal Agreement', value: `${data.signal_agreement_pct || 0}%`, pct: data.signal_agreement_pct || 0 },
  ];

  const barsHtml = metrics.map(m => `
    <div class="confidence-metric">
      <span class="confidence-metric-label">${escapeHtml(m.label)}</span>
      <div class="confidence-bar-track">
        <div class="confidence-bar-fill" style="width:${m.pct}%"></div>
      </div>
      <span class="confidence-metric-value">${escapeHtml(m.value)}</span>
    </div>
  `).join('');

  const sourcesHtml = (data.source_names || []).map(s =>
    `<span class="confidence-source-chip">${escapeHtml(s)}</span>`
  ).join('');

  return `<div class="confidence-panel">
    <div class="confidence-panel-title">CONFIDENCE DECOMPOSITION -- ${pct}%</div>
    <div class="confidence-summary">${data.independent_sources || 0} independent sources corroborate thesis</div>
    ${barsHtml}
    ${sourcesHtml ? `<div class="confidence-sources">${sourcesHtml}</div>` : ''}
  </div>`;
}

// ── Component C: Theme Trajectory ──
function renderThemeTrajectory(themes) {
  if (!themes || !themes.length) return '';

  const directionPill = (dir) => {
    if (dir === 'new') return '<span class="pill-new">NEW</span>';
    if (dir === 'fading' || dir === 'cooling') return '<span class="pill-fading">FADING</span>';
    if (dir === 'surging') return '<span class="pill-surging">SURGING</span>';
    return '';
  };

  const miniSparkline = (history) => {
    if (!history || history.length < 2) return '';
    const maxC = Math.max(...history.map(h => h.count), 1);
    const w = 80, h = 20;
    const step = w / (history.length - 1);
    const points = history.map((pt, i) => {
      const x = i * step;
      const y = h - (pt.count / maxC) * h;
      return `${x},${y}`;
    }).join(' ');
    // Area fill
    const areaPoints = `0,${h} ${points} ${w},${h}`;
    return `<svg class="trajectory-sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <polygon points="${areaPoints}" fill="rgba(0,212,255,0.08)"/>
      <polyline points="${points}" stroke="rgba(0,212,255,0.5)" stroke-width="1.5" fill="none"/>
    </svg>`;
  };

  const rowsHtml = themes.map(t => {
    const deltaCls = t.delta_pct > 0 ? 'up' : t.delta_pct < 0 ? 'down' : 'flat';
    const arrow = t.delta_pct > 0 ? '&#9650;' : t.delta_pct < 0 ? '&#9660;' : '';
    const deltaLabel = t.delta_pct !== 0 ? `${arrow} ${Math.abs(t.delta_pct)}%` : 'STEADY';

    return `<div class="trajectory-row">
      <span class="trajectory-name">${escapeHtml(t.subject)}</span>
      ${miniSparkline(t.history)}
      <span class="trajectory-delta ${deltaCls}">${deltaLabel}</span>
      ${directionPill(t.trend_direction)}
    </div>`;
  }).join('');

  return `<div class="theme-trajectory">
    <div class="theme-trajectory-label">THEME TRAJECTORY -- 30D WINDOW</div>
    ${rowsHtml}
  </div>`;
}

async function toggleTrendArticle() {
  const $article = document.getElementById('macroArticle');
  const $toggle = document.getElementById('macroExpandToggle');
  if (!$article || !$toggle) return;

  if (state.trendExpanded) {
    $article.classList.remove('expanded');
    $toggle.classList.remove('expanded');
    $toggle.textContent = 'CLICK TO EXPLORE ▾';
    state.trendExpanded = false;
    return;
  }

  $toggle.textContent = 'LOADING ARTICLE...';
  $toggle.classList.add('expanded');

  try {
    const articleData = await fetchJson('/synthesis/trend/article');

    let articleHtml = '';
    const sections = articleData.article_sections || [];

    // 1. Evidence Timeline — right after thesis
    if (articleData.key_evidence && articleData.key_evidence.length) {
      const windowStart = articleData.key_evidence[articleData.key_evidence.length - 1]?.detected_at;
      const windowEnd = articleData.key_evidence[0]?.detected_at;
      articleHtml += renderEvidenceTimeline(articleData.key_evidence, windowStart, windowEnd);
    }

    // 2. First half of article sections
    const midpoint = Math.ceil(sections.length / 2);
    if (sections.length) {
      articleHtml += renderArticleWithSources(sections.slice(0, midpoint));
    }

    // 3. Theme Trajectory — between analysis sections
    if (articleData.theme_trajectory && articleData.theme_trajectory.length) {
      articleHtml += renderThemeTrajectory(articleData.theme_trajectory);
    }

    // 4. Second half of article sections
    if (sections.length > midpoint) {
      articleHtml += renderArticleWithSources(sections.slice(midpoint));
    } else if (!sections.length && articleData.full_article_md) {
      articleHtml += formatMarkdown(articleData.full_article_md);
    }

    // 5. Confidence Decomposition — at the bottom
    if (articleData.confidence_decomposition) {
      articleHtml += renderConfidenceDecomposition(articleData.confidence_decomposition);
    }

    $article.innerHTML = `<div class="macro-article-inner">${articleHtml}</div>`;
    $article.classList.add('expanded');
    $toggle.textContent = 'COLLAPSE ▴';
    state.trendExpanded = true;
  } catch (err) {
    console.error('Failed to load trend article:', err);
    $toggle.textContent = 'CLICK TO EXPLORE ▾';
    $toggle.classList.remove('expanded');
  }
}

function attentionClass(label) {
  const upper = (label || '').toUpperCase();
  if (upper === 'SURGING') return 'attn-surging';
  if (upper === 'RISING') return 'attn-rising';
  if (upper === 'EMERGING') return 'attn-emerging';
  return 'attn-active';
}

function formatExploration(text) {
  if (!text) return '';
  // Convert markdown-style bold to HTML
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Highlight parenthetical citations and make them clickable
  html = html.replace(/\(([^)]{2,60})\)/g, (match, inner) => {
    // Check if it looks like a citation (not a regular parenthetical)
    const citationWords = ['source', 'report', '.com', '.org', '.io', '.net'];
    const lowerInner = inner.toLowerCase();
    const isCitation = citationWords.some(w => lowerInner.includes(w)) ||
      /^[A-Z]/.test(inner) && inner.split(' ').length <= 5;
    if (isCitation) {
      return `<span class="citation">(${inner})</span>`;
    }
    return `(${inner})`;
  });
  // Convert double newlines to paragraphs
  html = html.split(/\n\n+/).map(p => `<p>${p.trim()}</p>`).join('');
  // Convert single newlines to <br> within paragraphs
  html = html.replace(/\n/g, '<br>');
  return html;
}

function openMomentumModal(theme) {
  const $backdrop = document.getElementById('momentumBackdrop');
  const $modal = document.getElementById('momentumModal');
  const $title = document.getElementById('modalThemeTitle');
  const $meta = document.getElementById('modalThemeMeta');
  const $blurb = document.getElementById('modalBlurb');
  const $exploration = document.getElementById('modalExploration');
  const $sources = document.getElementById('modalSources');

  $title.textContent = theme.subject;
  $meta.innerHTML = `
    <span class="attn-badge ${attentionClass(theme.attention)}">${escapeHtml(theme.attention)}</span>
    ${(theme.competitors || []).map(name => `<span class="csp-tag">${escapeHtml(name)}</span>`).join('')}
  `;
  $blurb.textContent = theme.blurb || '';

  if (theme.detailed_exploration) {
    $exploration.innerHTML = formatExploration(theme.detailed_exploration);
    $exploration.style.display = '';
  } else {
    $exploration.innerHTML = '<p style="color:var(--text-dim);font-style:italic;">Detailed analysis will be available after the next synthesis cycle.</p>';
    $exploration.style.display = '';
  }

  const sources = theme.sources || [];
  $sources.innerHTML = sources.length ? sources.map(s =>
    `<a class="src-link" href="${s.url}" target="_blank" rel="noreferrer">${SRC_ARROW_SVG} ${escapeHtml(s.name || safeHostname(s.url))}</a>`
  ).join('') : '';
  $sources.style.display = sources.length ? '' : 'none';

  $backdrop.classList.add('open');
  $modal.classList.add('open');
}

function closeMomentumModal() {
  document.getElementById('momentumBackdrop').classList.remove('open');
  document.getElementById('momentumModal').classList.remove('open');
}

// Wire up modal close handlers
document.getElementById('momentumBackdrop')?.addEventListener('click', closeMomentumModal);
document.getElementById('modalClose')?.addEventListener('click', closeMomentumModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeMomentumModal();
});

// Store themes for click handlers
state.momentumThemes = [];

function renderDeltaBadge(deltas, subject) {
  if (!deltas || !deltas.length) return '';
  const d = deltas.find(x => x.subject === subject);
  if (!d) return '';
  if (d.is_new) return '<span class="delta-badge delta-new">NEW</span>';
  if (d.trend_direction === 'dying') return '<span class="delta-badge delta-fading">FADING</span>';
  if (d.delta === 0) return '';
  const arrow = d.delta > 0 ? '▲' : '▼';
  const cls = d.delta > 0 ? 'delta-up' : 'delta-down';
  const pct = Math.abs(d.delta_pct);
  return `<span class="delta-badge ${cls}">${arrow} ${pct > 0 ? pct + '% ' : ''}vs 7d</span>`;
}

function renderWindowProofBar(proof) {
  if (!proof || !proof.window_start) return '';
  const start = new Date(proof.window_start);
  const end = new Date(proof.window_end || Date.now());
  const fmtDate = (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return `<div class="window-proof-bar">
    <span class="wp-label">← ${escapeHtml(String(Math.round((end - start) / 86400000)))} DAY MOVING WINDOW →</span>
    <span class="wp-range">${fmtDate(start)} — ${fmtDate(end)}</span>
    <span class="wp-stats">${proof.total_signals_in_window || 0} signals · ${proof.signals_per_day_avg || 0}/day avg</span>
  </div>`;
}

function renderMomentum(momentum) {
  const themes = momentum.themes || [];
  const deltas = momentum.theme_deltas || [];
  state.momentumThemes = themes;
  $momentumMeta.textContent = `${themes.length} THEMES TRACKED`;
  if (!themes.length) {
    $momentumList.innerHTML = '<div class="ms-card"><div class="ms-subject">No momentum themes available</div></div>';
    return;
  }

  // Window proof bar
  const proofHtml = renderWindowProofBar(momentum.window_proof);

  $momentumList.innerHTML = proofHtml + themes.map((theme, idx) => `
    <div class="ms-card clickable" data-theme-idx="${idx}">
      <div class="ms-top">
        <div class="ms-subject">${escapeHtml(theme.subject)}</div>
        <div class="ms-badges">
          ${renderDeltaBadge(deltas, theme.subject)}
          <span class="attn-badge ${attentionClass(theme.attention)}">${escapeHtml(theme.attention)}</span>
        </div>
      </div>
      <div class="ms-csps">
        ${(theme.competitors || []).map(name => `<span class="csp-tag">${escapeHtml(name)}</span>`).join('')}
      </div>
      <div class="ms-blurb">${escapeHtml(theme.blurb || '')}</div>
      ${renderSources(theme.sources)}
    </div>
  `).join('');

  // Attach click handlers to momentum cards
  $momentumList.querySelectorAll('.ms-card.clickable').forEach(card => {
    card.addEventListener('click', () => {
      const idx = Number(card.dataset.themeIdx);
      const theme = state.momentumThemes[idx];
      if (theme) openMomentumModal(theme);
    });
  });

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

function renderUpdated(value, windowProof) {
  let text = `UPDATED ${formatRelativeTime(value).toUpperCase()}`;
  if (windowProof && windowProof.window_start) {
    const start = new Date(windowProof.window_start);
    const end = new Date(windowProof.window_end || Date.now());
    const fmtDate = (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
    text = `WINDOW: ${fmtDate(start)} → ${fmtDate(end)} · ${windowProof.total_signals_in_window || 0} SIGNALS · ${text}`;
  }
  $updated.textContent = text;
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
    renderUpdated(stats.last_updated_at || trend.generated_at, momentum.window_proof);
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
