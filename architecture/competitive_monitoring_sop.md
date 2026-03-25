# SOP: Strategic Competitive Monitoring

## Goal
Automate the detection, analysis, and reporting of competitor activities in the EU cloud market to provide actionable intelligence for Aleph Cloud.

## Inputs

### 1. News API (fetch_news.py)
- **Primary:** NewsAPI.org — query terms per competitor (see below)
- **Backup:** Direct RSS feeds from competitor engineering blogs

#### NewsAPI Query Terms
| Competitor | Query String |
|---|---|
| AWS | `"AWS" OR "Amazon Web Services" EU cloud` |
| Azure | `"Azure" OR "Microsoft Cloud" EU sovereign` |
| GCP | `"Google Cloud" OR "GCP" EU` |
| OVHcloud | `"OVHcloud" OR "OVH"` |
| Scaleway | `"Scaleway" OR "Iliad cloud"` |
| Hetzner | `"Hetzner"` |
| DigitalOcean | `"DigitalOcean"` |
| CoreWeave | `"CoreWeave"` |
| IONOS | `"IONOS cloud"` |

#### RSS Feeds (backup)
- AWS: `https://aws.amazon.com/blogs/aws/feed/`
- Azure: `https://azure.microsoft.com/en-us/blog/feed/`
- GCP: `https://cloud.google.com/feeds/gcp-release-notes.xml`
- Hetzner: `https://www.hetzner.com/news/feed.rss`
- OVHcloud: `https://blog.ovhcloud.com/feed/`
- The New Stack: `https://thenewstack.io/feed/`
- VentureBeat AI: `https://venturebeat.com/category/ai/feed/`

### 2. Status Pages (fetch_status_pages.py)
| Provider | URL |
|---|---|
| AWS | `https://status.aws.amazon.com/data.json` |
| Azure | `https://azure.status.microsoft/en-us/status/feed/` |
| GCP | `https://status.cloud.google.com/incidents.json` |
| Hetzner | `https://status.hetzner.com/api/v2/incidents.json` |
| DigitalOcean | `https://s2k7tnzlhrpw.statuspage.io/api/v2/incidents.json` |
| OVHcloud | `https://travaux.ovh.net/?do=rss` |
| Scaleway | `https://status.scaleway.com/api/v2/incidents.json` |

## Logic (The Filter)
1. **Ingestion:** Collect raw signals into `.tmp/raw_news.json` and `.tmp/raw_status.json`
2. **Merge & Deduplicate:** Remove duplicate `source_url` or near-identical headlines
3. **LLM Categorization** (`analyze_impact.py`):
   - Identify competitor
   - Classify category: `Outage | Funding | Product Launch | News | Policy`
   - Score strategic impact 1-10 for Aleph Cloud
   - Generate 1-sentence `summary` and 2-sentence `strategic_impact`
4. **Severity Mapping:**
   - Score 8-10 → Critical
   - Score 5-7 → High
   - Score 3-4 → Medium
   - Score 1-2 → Low
5. **Payload Generation:** Write `CompetitorEvent` records above `MIN_SEVERITY` to `data/events.db`

## Outputs
- **Dashboard Feed:** `/api/events` endpoint serves stored events to the UI
- **Priority Alerts:** Slack webhook + email for `severity: Critical` events

## Edge Cases
- **False Positives:** "Aleph" appears in biology, linguistics, cryptocurrency contexts. Filter: require co-occurrence with cloud/infrastructure keywords or explicit "Aleph Cloud"/"Aleph.im"
- **Rate Limits:** Jitter NewsAPI calls with random 1-3s delay between queries. Max 48 NewsAPI calls/day (30-min schedule × 16 queries = under 100/day limit)
- **Stale Status Pages:** If a status page returns no data for >2 hours, log a warning but do not alert
