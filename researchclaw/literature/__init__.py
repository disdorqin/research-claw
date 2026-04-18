"""Real literature search and citation management for ResearchClaw.

Provides API clients for Semantic Scholar, arXiv, and daily_arxiv
(pre-crawled AI-enhanced papers from power-papers-daily), plus unified
search with deduplication and BibTeX generation.  All network I/O uses
stdlib ``urllib`` — **zero** extra pip dependencies.
"""

from researchclaw.literature.daily_arxiv_source import (
    fetch_daily_papers,
    search_daily_arxiv,
)
from researchclaw.literature.models import Author, Paper
from researchclaw.literature.search import search_papers
from researchclaw.literature.verify import (
    CitationResult,
    VerificationReport,
    VerifyStatus,
    verify_citations,
)

__all__ = [
    "Author",
    "CitationResult",
    "Paper",
    "VerificationReport",
    "VerifyStatus",
    "fetch_daily_papers",
    "search_daily_arxiv",
    "search_papers",
    "verify_citations",
]
