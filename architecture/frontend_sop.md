# SOP: Frontend Dashboard

## Goal
Deliver a high-density, dark-theme, CEO-facing intelligence dashboard that presents competitive events in real time, filtered by competitor and category.

## Technology
- **HTML/CSS/JS** — static files served by Flask from `dashboard/`
- **Chart.js** — competitor activity bar chart and category distribution donut
- **Polling** — `app.js` fetches `/api/events` every 60 seconds for live updates

## File Structure
```
dashboard/
├── index.html   — Layout, markup, filter controls
├── styles.css   — Dark theme, severity color palette, typography
└── app.js       — API polling, DOM rendering, Chart.js init
```

## Layout Spec
```
┌─────────────────────────────────────────────────────┐
│  HEADER: Aleph Cloud · Competitive Intel · [live]   │
├──────────────────────────┬──────────────────────────┤
│  FILTERS                 │  STATS BAR               │
│  Competitor / Category   │  Total · Critical · Today │
├──────────────────────────┴──────────────────────────┤
│                                                     │
│  EVENT FEED (scrollable cards)                      │
│  [CRITICAL] AWS · Outage · 2h ago                   │
│  Headline text ...                                  │
│  Strategic impact: ...                              │
│                                                     │
├─────────────────────────────────────────────────────┤
│  CHART ROW: Activity by competitor | By category   │
└─────────────────────────────────────────────────────┘
```

## Severity Color Palette
| Severity | Color       | Hex       |
|----------|-------------|-----------|
| Critical | Red         | `#FF3B3B` |
| High     | Orange      | `#FF8C00` |
| Medium   | Yellow      | `#FFD700` |
| Low      | Slate       | `#6B7280` |

## Competitor Badge Colors
- AWS: `#FF9900`
- Azure: `#0078D4`
- GCP: `#4285F4`
- OVHcloud: `#123F6D`
- Scaleway: `#6930C3`
- Hetzner: `#D50C2D`
- DigitalOcean: `#0080FF`
- CoreWeave: `#7C3AED`
- IONOS: `#003D8F`
- Other: `#6B7280`

## API Contract
- `GET /api/events?competitor=&category=&severity=&limit=50`
- Response: `{ "events": [CompetitorEvent], "last_updated": "ISO8601", "total": int }`

## Refresh Behavior
- Auto-refresh every **60 seconds** (configurable via `POLL_INTERVAL` const in `app.js`)
- Live indicator pulses green when last fetch < 90 seconds ago, red if stale
- New events since last poll are highlighted with a brief flash animation
