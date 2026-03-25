"""Canonical pinned competitor registry, authoritative sources, and discovery seeds."""

from __future__ import annotations


COMPETITORS = [
    {"slug": "aws", "name": "AWS", "provider_type": "hyperscaler", "display_order": 1, "tier": 1},
    {"slug": "azure", "name": "Microsoft Azure", "provider_type": "hyperscaler", "display_order": 2, "tier": 1},
    {"slug": "gcp", "name": "Google Cloud", "provider_type": "hyperscaler", "display_order": 3, "tier": 1},
    {"slug": "oracle-cloud", "name": "Oracle Cloud", "provider_type": "hyperscaler", "display_order": 4, "tier": 1},
    {"slug": "coreweave", "name": "CoreWeave", "provider_type": "gpu_cloud", "display_order": 5, "tier": 1},
    {"slug": "alibaba-cloud", "name": "Alibaba Cloud", "provider_type": "hyperscaler", "display_order": 6, "tier": 2},
    {"slug": "ovhcloud", "name": "OVHcloud", "provider_type": "eu_sovereign", "display_order": 7, "tier": 2},
    {"slug": "scaleway", "name": "Scaleway", "provider_type": "eu_sovereign", "display_order": 8, "tier": 2},
    {"slug": "open-telekom-cloud", "name": "Open Telekom Cloud", "provider_type": "eu_sovereign", "display_order": 9, "tier": 3},
    {"slug": "ionos-cloud", "name": "IONOS Cloud", "provider_type": "eu_sovereign", "display_order": 10, "tier": 2},
    {"slug": "digitalocean", "name": "DigitalOcean", "provider_type": "developer_cloud", "display_order": 11, "tier": 2},
    {"slug": "akamai-linode", "name": "Akamai/Linode", "provider_type": "developer_cloud", "display_order": 12, "tier": 3},
    {"slug": "vultr", "name": "Vultr", "provider_type": "developer_cloud", "display_order": 13, "tier": 3},
    {"slug": "hetzner", "name": "Hetzner", "provider_type": "developer_cloud", "display_order": 14, "tier": 2},
    {"slug": "ibm-cloud", "name": "IBM Cloud", "provider_type": "enterprise", "display_order": 15, "tier": 3},
    {"slug": "crusoe", "name": "Crusoe", "provider_type": "gpu_cloud", "display_order": 16, "tier": 3},
    {"slug": "lambda-labs", "name": "Lambda Labs", "provider_type": "gpu_cloud", "display_order": 17, "tier": 3},
]


def endpoint(
    source_kind: str,
    purpose: str,
    endpoint_url: str,
    adapter_type: str,
    *,
    trust_tier: int = 1,
    poll_interval_seconds: int = 900,
    is_primary: int = 0,
    parser_config: dict | None = None,
) -> dict:
    return {
        "source_kind": source_kind,
        "purpose": purpose,
        "endpoint_url": endpoint_url,
        "adapter_type": adapter_type,
        "trust_tier": trust_tier,
        "poll_interval_seconds": poll_interval_seconds,
        "is_primary": is_primary,
        "parser_config": parser_config or {},
    }


SOURCE_ENDPOINTS = {
    "aws": [
        endpoint("status_page", "status", "https://status.aws.amazon.com/rss/all.rss", "aws_health_rss", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://aws.amazon.com/blogs/aws/feed/", "rss"),
        endpoint("rss_blog", "news", "https://aws.amazon.com/blogs/machine-learning/feed/", "rss"),
        endpoint("rss_press", "press", "https://aws.amazon.com/about-aws/whats-new/recent/feed/", "rss", poll_interval_seconds=1800),
    ],
    "azure": [
        endpoint("status_page", "status", "https://azure.status.microsoft/en-us/status/feed/", "rss", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://azure.microsoft.com/en-us/blog/feed/", "rss"),
        endpoint("rss_press", "press", "https://news.microsoft.com/source/feed/", "rss", poll_interval_seconds=1800),
    ],
    "gcp": [
        endpoint("status_page", "status", "https://status.cloud.google.com/incidents.json", "gcp_incidents", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://cloud.google.com/blog/rss/", "rss"),
        endpoint("rss_releases", "news", "https://cloud.google.com/feeds/gcp-release-notes.xml", "rss", poll_interval_seconds=1800),
    ],
    "oracle-cloud": [
        endpoint("status_page", "status", "https://ocistatus.oraclecloud.com/api/v2/status.json", "statuspage_status_json", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://blogs.oracle.com/cloud-infrastructure/rss", "rss"),
    ],
    "coreweave": [
        endpoint("status_page", "status", "https://status.coreweave.com/pages/5e126e998f2f032e1f8f0f4b/rss", "rss", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.coreweave.com/blog/rss.xml", "rss"),
    ],
    "alibaba-cloud": [
        endpoint("rss_blog", "news", "https://www.alibabacloud.com/blog/feed", "rss"),
    ],
    "ovhcloud": [
        endpoint("status_page", "status", "https://public-cloud.status-ovhcloud.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://blog.ovhcloud.com/feed/", "rss"),
        endpoint("rss_press", "press", "https://corporate.ovhcloud.com/en/newsroom/rss.xml", "rss", poll_interval_seconds=1800),
    ],
    "scaleway": [
        endpoint("status_page", "status", "https://status.scaleway.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.scaleway.com/en/blog/feed/", "rss"),
    ],
    "open-telekom-cloud": [
        endpoint("rss_blog", "news", "https://open-telekom-cloud.com/en/newsroom/rss", "rss", trust_tier=2),
    ],
    "ionos-cloud": [
        endpoint("status_page", "status", "https://status.ionos.cloud/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.ionos.com/newsroom/rss.xml", "rss"),
    ],
    "digitalocean": [
        endpoint("status_page", "status", "https://status.digitalocean.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.digitalocean.com/blog/rss.xml", "rss"),
    ],
    "akamai-linode": [
        endpoint("status_page", "status", "https://status.linode.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=900, is_primary=1),
        endpoint("rss_blog", "news", "https://www.linode.com/blog/feed/", "rss"),
    ],
    "vultr": [
        endpoint("status_page", "status", "https://status.vultr.com/status.json", "vultr_status_json", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.vultr.com/company/updates/rss.xml", "rss", trust_tier=2),
    ],
    "hetzner": [
        endpoint("status_page", "status", "https://www.hetzner-status.de/en.atom", "rss", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.hetzner.com/news/rss.xml", "rss"),
    ],
    "ibm-cloud": [
        endpoint("status_page", "status", "https://cloud.ibm.com/status/api/notifications/feed.rss", "rss", poll_interval_seconds=900, is_primary=1),
        endpoint("rss_blog", "news", "https://www.ibm.com/cloud/blog/feed", "rss"),
    ],
    "crusoe": [
        endpoint("status_page", "status", "https://status.crusoecloud.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=720, is_primary=1),
        endpoint("rss_blog", "news", "https://www.crusoe.ai/resources/blog/rss.xml", "rss"),
    ],
    "lambda-labs": [
        endpoint("status_page", "status", "https://status.lambdalabs.com/api/v2/incidents.json", "atlassian_v2", poll_interval_seconds=900, is_primary=1),
        endpoint("rss_blog", "news", "https://lambda.ai/blog/rss.xml", "rss"),
    ],
}

QUERY_FAMILIES = [
    "launches_capacity",
    "funding_capital",
    "policy_regulation",
    "partnerships",
    "pricing",
    "market_mentions",
]

QUERY_TEMPLATES = {
    "launches_capacity": '"{name}" cloud (launch OR released OR region OR datacenter OR GPU OR capacity)',
    "funding_capital": '"{name}" cloud (funding OR investment OR revenue OR earnings OR acquisition)',
    "policy_regulation": '"{name}" cloud (sovereign OR compliance OR regulation OR secnumcloud OR eucs OR c5)',
    "partnerships": '"{name}" cloud (partnership OR alliance OR integration OR collaboration)',
    "pricing": '"{name}" cloud (pricing OR price OR discount OR cost OR free tier)',
    "market_mentions": '"{name}" cloud Europe market competition Aleph alternative',
}

TIER_CONFIG = {
    1: {"cadence_minutes": 60, "count": 5, "freshness": "pw", "max_monthly": 320},
    2: {"cadence_minutes": 120, "count": 4, "freshness": "pw", "max_monthly": 180},
    3: {"cadence_minutes": 240, "count": 3, "freshness": "pm", "max_monthly": 90},
}

INDUSTRY_QUERIES = [
    {"query_family": "policy_regulation", "endpoint_type": "news", "query_template": "EU cloud sovereignty regulation secnumcloud eucs cloud 2026", "cadence_minutes": 180, "count": 5, "freshness_window": "pw"},
    {"query_family": "launches_capacity", "endpoint_type": "news", "query_template": "Europe GPU cloud datacenter launch AI infrastructure 2026", "cadence_minutes": 180, "count": 5, "freshness_window": "pw"},
    {"query_family": "funding_capital", "endpoint_type": "news", "query_template": "cloud infrastructure funding europe gpu startup 2026", "cadence_minutes": 360, "count": 4, "freshness_window": "pm"},
]


def build_discovery_queries() -> list[dict]:
    queries: list[dict] = []
    for competitor in COMPETITORS:
        cfg = TIER_CONFIG[competitor["tier"]]
        for family in QUERY_FAMILIES:
            queries.append({
                "competitor_slug": competitor["slug"],
                "provider": "brave",
                "query_family": family,
                "endpoint_type": "news",
                "query_template": QUERY_TEMPLATES[family].format(name=competitor["name"]),
                "freshness_window": cfg["freshness"],
                "count": cfg["count"],
                "cadence_minutes": cfg["cadence_minutes"],
                "cooldown_minutes": max(cfg["cadence_minutes"] // 2, 30),
                "priority": competitor["tier"],
                "trigger_only": 0,
                "max_monthly_calls": cfg["max_monthly"],
            })

    for query in INDUSTRY_QUERIES:
        queries.append({
            "competitor_slug": None,
            "provider": "brave",
            "query_family": query["query_family"],
            "endpoint_type": query["endpoint_type"],
            "query_template": query["query_template"],
            "freshness_window": query["freshness_window"],
            "count": query["count"],
            "cadence_minutes": query["cadence_minutes"],
            "cooldown_minutes": max(query["cadence_minutes"] // 2, 60),
            "priority": 1,
            "trigger_only": 0,
            "max_monthly_calls": 180,
        })

    return queries
