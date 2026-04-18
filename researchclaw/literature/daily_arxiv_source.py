"""Daily arXiv paper source from power-papers-daily GitHub repository.

Fetches pre-crawled, AI-enhanced arXiv papers from the ``data`` branch
of the ``power-papers-daily`` repository.  This avoids redundant crawling
and provides papers that already have AI-generated summaries.

Data format (JSONL):
    Each line is a JSON object with fields: id, title, authors, summary,
    categories, pdf, abs, AI (with tldr/motivation/method/result/conclusion).

Public API
----------
- ``fetch_daily_papers(days_back, repo_owner, repo_name, language)``
  → ``list[Paper]``
- ``search_daily_arxiv(query, days_back, limit, ...)``
  → ``list[Paper]``
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from researchclaw.literature.models import Author, Paper

logger = logging.getLogger(__name__)

_DEFAULT_REPO_OWNER = os.environ.get("DAILY_ARXIV_REPO_OWNER", "disdorqin")
_DEFAULT_REPO_NAME = os.environ.get("DAILY_ARXIV_REPO_NAME", "power-papers-daily")
_DEFAULT_BRANCH = os.environ.get("DAILY_ARXIV_BRANCH", "data")
_DEFAULT_LANGUAGE = os.environ.get("DAILY_ARXIV_LANGUAGE", "Chinese")

_BASE_RAW_URL = (
    "https://raw.githubusercontent.com"
    "/{owner}/{repo}/{branch}/data/{filename}"
)


def _build_url(
    date: str,
    *,
    owner: str = _DEFAULT_REPO_OWNER,
    repo: str = _DEFAULT_REPO_NAME,
    branch: str = _DEFAULT_BRANCH,
    language: str = _DEFAULT_LANGUAGE,
) -> str:
    filename = f"{date}_AI_enhanced_{language}.jsonl"
    return _BASE_RAW_URL.format(
        owner=owner, repo=repo, branch=branch, filename=filename
    )


def _fetch_jsonl(url: str, timeout: int = 15) -> list[dict[str, Any]]:
    """Fetch and parse a JSONL file from a URL. Returns list of dicts."""
    logger.info("Fetching daily arXiv data: %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchClaw/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                logger.warning("HTTP %d for %s", resp.status, url)
                return []
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info("No data file for URL (404): %s", url)
        else:
            logger.warning("HTTP error fetching %s: %s", url, exc)
        return []
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Network error fetching %s: %s", url, exc)
        return []

    papers: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            papers.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON on line %d of %s", line_no, url)
    return papers


def _convert_to_paper(item: dict[str, Any]) -> Paper:
    """Convert a JSONL record from power-papers-daily to a Paper object."""
    arxiv_id = str(item.get("id", ""))
    title = str(item.get("title", ""))

    authors_raw = item.get("authors", [])
    if isinstance(authors_raw, (list, tuple)):
        authors = tuple(
            Author(name=str(a) if isinstance(a, str) else str(a.get("name", "")))
            for a in authors_raw
        )
    else:
        authors = ()

    abstract = str(item.get("summary", ""))

    ai_data = item.get("AI", {})
    if isinstance(ai_data, dict) and ai_data:
        tldr = ai_data.get("tldr", "")
        motivation = ai_data.get("motivation", "")
        method = ai_data.get("method", "")
        result = ai_data.get("result", "")
        conclusion = ai_data.get("conclusion", "")
        ai_summary = (
            f"[AI Summary] TL;DR: {tldr}\n"
            f"Motivation: {motivation}\n"
            f"Method: {method}\n"
            f"Result: {result}\n"
            f"Conclusion: {conclusion}"
        )
        if abstract:
            abstract = f"{abstract}\n\n{ai_summary}"
        else:
            abstract = ai_summary

    categories = item.get("categories", [])
    if isinstance(categories, (list, tuple)):
        venue = categories[0] if categories else ""
    else:
        venue = str(categories)

    year = 0
    arxiv_id_match = re.match(r"(\d{2})(\d{2})\.", arxiv_id)
    if arxiv_id_match:
        year = 2000 + int(arxiv_id_match.group(1))

    url = str(item.get("abs", f"https://arxiv.org/abs/{arxiv_id}"))

    return Paper(
        paper_id=f"daily-arxiv-{arxiv_id}" if arxiv_id else f"daily-arxiv-{hash(title) % 100000}",
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        venue=venue,
        citation_count=0,
        doi=item.get("doi", ""),
        arxiv_id=arxiv_id,
        url=url,
        source="daily_arxiv",
    )


def fetch_daily_papers(
    days_back: int = 7,
    *,
    owner: str = _DEFAULT_REPO_OWNER,
    repo: str = _DEFAULT_REPO_NAME,
    branch: str = _DEFAULT_BRANCH,
    language: str = _DEFAULT_LANGUAGE,
    timeout: int = 15,
) -> list[Paper]:
    """Fetch papers from the last *days_back* days of power-papers-daily.

    Parameters
    ----------
    days_back:
        Number of days to look back from today.
    owner:
        GitHub repository owner.
    repo:
        GitHub repository name.
    branch:
        Branch containing the data (default: ``data``).
    language:
        Language of AI-enhanced summaries (default: ``Chinese``).
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    list[Paper]
        Papers found across all requested dates.
    """
    all_papers: list[Paper] = []
    today = datetime.now()

    for i in range(days_back):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        url = _build_url(date, owner=owner, repo=repo, branch=branch, language=language)
        items = _fetch_jsonl(url, timeout=timeout)

        if not items:
            logger.debug("No papers found for %s", date)
            continue

        for item in items:
            try:
                all_papers.append(_convert_to_paper(item))
            except Exception as exc:
                logger.warning("Failed to convert paper for %s: %s", date, exc)

        logger.info("Fetched %d papers for %s", len(items), date)

    logger.info(
        "Total daily arXiv papers fetched: %d (last %d days)",
        len(all_papers), days_back,
    )
    return all_papers


def search_daily_arxiv(
    query: str,
    *,
    days_back: int = 7,
    limit: int = 50,
    owner: str = _DEFAULT_REPO_OWNER,
    repo: str = _DEFAULT_REPO_NAME,
    branch: str = _DEFAULT_BRANCH,
    language: str = _DEFAULT_LANGUAGE,
) -> list[Paper]:
    """Search pre-crawled daily arXiv papers by keyword.

    Fetches papers from the last *days_back* days, then filters by
    matching *query* against title and abstract (case-insensitive).

    Parameters
    ----------
    query:
        Search keyword or phrase.
    days_back:
        How many days of data to fetch.
    limit:
        Maximum number of results to return.
    owner / repo / branch / language:
        GitHub repository configuration.

    Returns
    -------
    list[Paper]
        Matching papers, sorted by date (newest first).
    """
    all_papers = fetch_daily_papers(
        days_back=days_back,
        owner=owner,
        repo=repo,
        branch=branch,
        language=language,
    )

    if not all_papers:
        return []

    query_lower = query.lower()
    query_terms = [t.strip() for t in query_lower.split() if t.strip()]

    matched: list[Paper] = []
    for paper in all_papers:
        text = f"{paper.title} {paper.abstract}".lower()
        if any(term in text for term in query_terms):
            matched.append(paper)

    matched.sort(key=lambda p: p.year, reverse=True)
    return matched[:limit]
