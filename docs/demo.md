# Demo — Example Session

This page walks through a realistic research-claw session using a sample topic.
It mirrors the commands documented in the README. Status labels mark what is
part of the current pipeline versus what is on the roadmap.

> Note: the snippets below show the *shape* of the inputs and outputs. They are
> illustrative, not the output of a specific run.

## 1. Define a topic

`topic.txt`

```
graph neural networks for molecular property prediction
```

## 2. Run the literature agent

```bash
python -m researchclaw agent:literature --topic topic.txt
# → produces literature_review.md
```

Example `literature_review.md` shape:

```markdown
# Literature Review: GNNs for Molecular Property Prediction

## Surveyed themes
- Message-passing GNNs (GCN, GIN, GraphSAGE)
- Transformer-based molecular models (Uni-Mol, MoFlow)
- Pretraining strategies (self-supervised, geometric)

## Open questions
- Generalization to out-of-distribution molecules
- Data efficiency under small labeled sets
```

Status: **Supported** (literature survey agent, per README).

## 3. Run the methodology agent

```bash
python -m researchclaw agent:methodology --review literature_review.md
# → produces methodology.md
```

Example `methodology.md` shape:

```markdown
# Methodology

## Proposed approach
- Backbone: graph isomorphism network with edge features
- Pretraining: masked node/edge reconstruction
- Evaluation: scaffold split, MAE/RMSE on downstream targets

## Experiment plan
- Ablation: pretraining vs. from-scratch
- Baselines: RF on molecular fingerprints, SchNet
```

Status: **Supported** (methodology agent, per README).

## 4. Run the writing agent

```bash
python -m researchclaw agent:writing --all
# → produces draft_paper.md
```

Example `draft_paper.md` shape:

```markdown
# Title

## Abstract
...

## 1. Introduction
...

## 2. Related Work
...
```

Status: **Supported** (writing agent, per README).

## Capability status

| Capability | Status | Notes |
|------------|--------|-------|
| Topic → literature survey | Supported | CLI `agent:literature` |
| Methodology design | Supported | CLI `agent:methodology` |
| Paper writing (sections) | Supported | CLI `agent:writing` |
| Experiment code generation | Planned | on roadmap, not yet in stable CLI |
| Figure generation | Planned | roadmap |
| Human-in-the-loop quality gates | Planned | roadmap |
| Distributed / parallel agents | Planned | roadmap |

See [architecture.md](architecture.md) for the agent pipeline. The version plan
is tracked in the project roadmap.
