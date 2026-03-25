"""
Tool: deduplicate.py
Layer: 3 — Execution
SOP: architecture/data_pipeline_sop.md

Merges raw_news.json + raw_status.json, removes duplicate signals by:
  1. Exact URL match
  2. Near-identical headline (Jaccard similarity > 0.85)

Input:  .tmp/raw_news.json, .tmp/raw_status.json
Output: .tmp/deduped_signals.json
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TMP_DIR = ROOT / ".tmp"
INPUT_FILES = [TMP_DIR / "raw_news.json", TMP_DIR / "raw_status.json"]
OUTPUT_FILE = TMP_DIR / "deduped_signals.json"


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    set_a = set(_normalize(a).split())
    set_b = set(_normalize(b).split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _is_duplicate(signal: dict, seen_urls: set, seen_titles: list[str], threshold: float = 0.85) -> bool:
    """Return True if this signal is a duplicate of a previously seen one."""
    url = signal.get("raw_url", "").strip()
    title = signal.get("raw_title", "").strip()

    # 1. Exact URL match
    if url and url in seen_urls:
        return True

    # 2. Near-identical headline
    for existing_title in seen_titles:
        if _jaccard(title, existing_title) >= threshold:
            return True

    return False


def deduplicate() -> list[dict]:
    """
    Load, merge, and deduplicate raw signals.
    Returns the cleaned list and writes to .tmp/deduped_signals.json.
    """
    all_signals: list[dict] = []

    for input_file in INPUT_FILES:
        if not input_file.exists():
            logger.warning(f"deduplicate.py: {input_file} not found — skipping")
            continue
        try:
            data = json.loads(input_file.read_text(encoding='utf-8'))
            all_signals.extend(data)
            logger.info(f"  Loaded {len(data)} signals from {input_file.name}")
        except Exception as e:
            logger.error(f"  Failed to load {input_file}: {e}")

    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    deduped: list[dict] = []

    for signal in all_signals:
        if _is_duplicate(signal, seen_urls, seen_titles):
            continue

        url = signal.get("raw_url", "").strip()
        title = signal.get("raw_title", "").strip()

        if url:
            seen_urls.add(url)
        if title:
            seen_titles.append(title)

        deduped.append(signal)

    removed = len(all_signals) - len(deduped)
    logger.info(f"deduplicate.py: {len(all_signals)} in → {len(deduped)} out ({removed} duplicates removed)")

    OUTPUT_FILE.write_text(json.dumps(deduped, indent=2, ensure_ascii=False), encoding='utf-8')
    return deduped


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signals = deduplicate()
    print(f"Deduplication complete: {len(signals)} unique signals.")
