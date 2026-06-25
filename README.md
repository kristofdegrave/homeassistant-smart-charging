# homeassistant-smart-charging

Smart EV charging integration for Home Assistant — solar-first and
capacity-tariff-aware. Hardware-agnostic; targets single-phase grids for now
(three-phase later).

> **Status: analysis / specification phase.** This project follows an
> analysis-first, spec-driven methodology — the documents under
> [`docs/analysis/`](docs/analysis/) are the current source of truth, and no
> integration code is written until the relevant analysis is complete. See
> [CLAUDE.md](CLAUDE.md) for the working method.

## What it does

The integration charges an EV intelligently rather than at full power on plug-in,
pursuing four goals in priority order (bounded by the last):

1. **Maximise solar self-consumption** — use solar surplus before any grid power.
2. **Keep the monthly capacity-tariff (CapTar) peak under control** — never raise
   the billed peak through avoidable charging spikes.
3. **Charge cost-efficiently from the grid** — prefer low-tariff periods.
4. **Meet the departure deadline** whenever physically possible — escalating
   charging (and cost) only as far as a configurable maximum peak allows.

## Key concepts

A few terms recur throughout the documentation (all defined authoritatively in the
[Ubiquitous Language glossary](docs/analysis/system-overview.md#ubiquitous-language)):

- **Mode vs profile** — a *mode* (`Solar`, `SolarOnly`, `Captar`, `Power`, `Off`)
  is the concrete behaviour the coordinator executes; a *profile* (`Manual`, `Auto`)
  is the higher-level strategy that selects which mode is active over time. The
  coordinator never decides the mode itself — a profile does.
- **Effective peak limit & safety margin** — charging stays a configurable margin
  below `min(monthly peak demand, maximum peak)`; deadline urgency may raise the
  limit up to the configurable maximum peak.
- **Active SOC limit** — the charge target in force, resolved from the configured
  default, an optional solar step-up, and the solar-reserve overnight cap.
- **Configurable & sensor-driven** — values are configurable with sensible defaults,
  and inputs/outputs flow through the integration's own `sc_`-prefixed wrapper
  entities, so any charger, EV, or solar setup can be swapped in.

## Documentation

| Document                                                         | Purpose                                                                                                                       |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [Methodology](docs/plans/2026-06-24-analysis-approach-design.md) | The analysis-first, spec-driven approach this project follows.                                                                |
| [System overview](docs/analysis/system-overview.md)              | Stakeholders, problem, goals, hardware context, and the authoritative Ubiquitous Language glossary.                           |
| [Requirements](docs/analysis/requirements.md)                    | Functional (R1–R17), non-functional (NF1–NF4), and constraints (C1–C3), with MoSCoW priorities and SMART acceptance criteria. |
| [Flows](docs/analysis/flows/)                                    | Per-behaviour flow documents (control cycle, each mode, SOC management, deadline override, etc.) — *in progress*.             |

Reading order: **system overview → requirements → flows**. Every domain term used
anywhere must be defined in the glossary first.

> A previous iteration is kept under [`docs/archive/`](docs/archive/) for reference
> only — it is **not** a source of truth.
