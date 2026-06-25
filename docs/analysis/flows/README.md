# Flow documents

Per-behaviour analysis flows. Each flow follows the standard in
[CLAUDE.md](../../../CLAUDE.md): **Purpose → Trigger → Domain events → Mermaid
diagram → Steps → Edge cases → Requirements satisfied**. Every domain term used
here must already be defined in the
[Ubiquitous Language glossary](../system-overview.md#ubiquitous-language).

Write them one at a time, starting with the control cycle.

| Flow                        | Covers                                                                                                                                                | Status  |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|---------|
| `00-control-cycle.md`       | The coordinator loop: read sensors → smooth → resolve active mode via profile → dispatch to mode module → apply peak protection → set charger current | Planned |
| `01-solar-flow.md`          | `Solar` mode, including grid fallback (R1)                                                                                                            | Planned |
| `02-solar-only-flow.md`     | `SolarOnly` mode (R2)                                                                                                                                 | Planned |
| `03-captar-flow.md`         | `Captar` mode (R4)                                                                                                                                    | Planned |
| `04-power-flow.md`          | `Power` mode, incl. configurable peak-breach option (R17)                                                                                             | Planned |
| `05-soc-management.md`      | Active SOC limit resolution & lifecycle and solar step-up (R6, R7, R8)                                                                                | Planned |
| `06-deadline-override.md`   | Deadline urgency as a cross-cutting override (R5)                                                                                                     | Planned |
| `07-solar-reserve-logic.md` | Solar-reserve overnight cap and the home-day flag (R9, R13)                                                                                           | Planned |
| `08-profile-selection.md`   | Profiles select modes; the `Auto` profile (R16, NF1)                                                                                                  | Planned |
