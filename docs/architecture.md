# Architecture

This document describes the high-level architecture of research-claw based on the actual project structure.

## Overview

research-claw is a multi-agent system that automates the research paper generation pipeline. It coordinates specialized agents for literature review, methodology design, experiment planning, writing, and review.

## Module Map

```
researchclaw/
├── cli.py              # CLI entry point (researchclaw run, agent, etc.)
├── config.py           # YAML-based configuration loader
├── pipeline/           # Stage orchestration pipeline
│   ├── stages.py       # Pipeline stage definitions
│   ├── executor.py     # Stage execution engine
│   ├── contracts.py    # Stage input/output contracts
│   └── stage_impls/    # Individual stage implementations
├── agents/             # Specialized research agents
│   ├── base.py         # Base agent class
│   ├── figure_agent/   # Figure generation agent
│   ├── benchmark_agent/# Benchmark comparison agent
│   └── code_searcher/  # Related code search agent
├── literature/         # Paper search & ingestion
│   ├── search.py       # Unified search interface
│   ├── arxiv_client.py # arXiv API client
│   ├── openalex_client.py  # OpenAlex API client
│   ├── semantic_scholar.py # Semantic Scholar API
│   ├── daily_arxiv_source.py # Daily paper updates
│   ├── verify.py       # Source verification
│   ├── cache.py        # Search result caching
│   ├── models.py       # Paper data models
│   ├── novelty.py      # Novelty assessment
│   └── trends.py       # Research trend analysis
├── domains/            # Domain-specific adapters
│   ├── detector.py     # Domain detection from config
│   ├── profiles/       # Domain-specific prompt profiles
│   ├── adapters/       # Domain adapter interfaces
│   └── experiment_schema.py # Experiment schema per domain
├── knowledge/          # Knowledge management
│   ├── base.py         # Knowledge base interface
│   └── graph/          # Knowledge graph storage
├── experiment/         # Experiment runner
├── assessor/           # Quality assessment
├── feedback/           # Feedback loop handling
├── hitl/               # Human-in-the-loop support
├── report.py           # Report generation
├── quality.py          # Quality metrics
├── utils/              # Shared utilities
├── llm/                # LLM integration
├── mcp/                # MCP protocol integration
├── memory/             # Agent memory management
├── server/             # API server
├── web/                # Web interface
├── skills/             # AI skill definitions
├── collaboration/      # Multi-agent coordination
├── templates/          # Prompt/output templates
└── writing_guide.py    # Writing style guidance
```

## Data Flow

```
User Config (YAML)
       │
       ▼
  pipeline/stages.py ──► executor.py ──► stage_impls/
       │                                        │
       ├── literature_search ────────────────── literature/search.py
       ├── methodology_design ───────────────── agents/base.py
       ├── experiment_planning ──────────────── experiment/
       ├── code_generation ──────────────────── pipeline/code_agent.py
       ├── paper_writing ────────────────────── writing_guide.py
       └── review ───────────────────────────── assessor/ + quality.py
```

## Agent Types

| Agent | Location | Purpose |
|-------|----------|---------|
| Literature Agent | `literature/` | Searches arXiv, OpenAlex, Semantic Scholar; caches results |
| Methodology Agent | `agents/base.py` | Designs methodology from literature survey |
| Figure Agent | `agents/figure_agent/` | Generates experiment figures and diagrams |
| Benchmark Agent | `agents/benchmark_agent/` | Compares against existing benchmarks |
| Code Agent | `pipeline/code_agent.py` | Generates experiment code |
| Paper Verifier | `pipeline/paper_verifier.py` | Validates paper consistency |
| Diagnosis Agent | `pipeline/experiment_diagnosis.py` | Diagnoses experiment failures |

## Key Design Decisions

- **Config-driven pipeline**: All research parameters are defined in a single YAML config file (`config.researchclaw.example.yaml`)
- **Stage contracts**: Each pipeline stage defines typed input/output contracts (`pipeline/contracts.py`), enabling independent development and testing of stages
- **Multi-source literature**: Supports arXiv, OpenAlex, and Semantic Scholar with a unified search interface and result caching
- **Domain-aware**: Domain-specific prompt profiles and experiment schemas allow the system to adapt to different research fields
- **External integrations**: Overleaf (via `overleaf/`), MCP protocol (via `mcp/`), and OpenCode bridge (via `pipeline/opencode_bridge.py`)

## Dependencies

- Python 3.10+
- LLM API access (configurable provider via `llm/`)
- Internet access for literature search (arXiv, OpenAlex, Semantic Scholar)
- Optional: Docker for sandboxed experiment execution
