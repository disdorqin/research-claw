# Roadmap

Status labels: **done** · **in progress** · **planned**

## Current status
research-claw provides a config-driven, multi-agent pipeline. The orchestration
layer and the literature-review agent are operational. Methodology, experiment,
and writing agents are exposed in the CLI but tracked as in-progress in the
project roadmap.

## v0.1 — Foundation (done)
- [x] Multi-agent orchestration (pipeline coordinator)
- [x] Literature review agent
- [x] Config-driven runs (`config.researchclaw.yaml`)
- [x] CLI entry point (`python -m researchclaw`)

## v0.2 — Deeper agents (in progress)
- [ ] Methodology design agent (CLI present, hardening)
- [ ] Experiment generation agent
- [ ] Paper writing agent (section drafting)
- [ ] Human-in-the-loop quality gates
- [ ] Figure generation

## v0.3 — Scale & integration (planned)
- [ ] Distributed / parallel agent runs
- [ ] Evaluation harness
- [ ] Integration with external research tooling (e.g., DARIS, tsplab)
- [ ] Public examples gallery

> No fixed release dates are committed; versions advance as capabilities land.

See [demo.md](demo.md) for an example session and
[architecture.md](architecture.md) for the agent pipeline.
