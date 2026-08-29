# Changelog

## [0.4.1](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.4.0...v0.4.1) (2026-08-29)


### Bug Fixes

* perf suite CPU quantization, tracemalloc overlap, zero RSS baseline ([#858](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/858)) ([70cfd7d](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/70cfd7da8d0f613055d525e3b5a5099e1c30ba7d))
* report a no-diff draft on _ai-draft.yml instead of stranding needs-draft ([#861](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/861)) ([009b5d8](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/009b5d8511c922c8ce02e2eda3739e03a2df50af)), closes [#467](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/467)

## [0.4.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.3.0...v0.4.0) (2026-08-26)


### Features

* add sync_disabled_by registry helper (ADR-0028) ([#800](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/800)) ([1f415c2](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/1f415c24cc84cf3fa833a36616566df4b596377a))
* add sync_labels registry helper (ADR-0028) ([#801](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/801)) ([b0443b6](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/b0443b6af97f1f6d4341c75292e6ae31c2780867))
* compare_baseline regression case (T0.2, issue [#708](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/708)) ([#734](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/734)) ([e67411a](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/e67411a147061467fe154825379196a70781547e))
* gate SmartChargingDepartureTime's registry state on deadline_available (ADR-0028) ([#803](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/803)) ([c65629d](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c65629d89f83c335411f08b0546f7cd17022c91e))
* gate SolarSurplusSensor's registry state on solar_available (ADR-0028) ([#802](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/802)) ([5fd8fd6](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5fd8fd62dab14a3bbafdd26c97720f08cbe30a38))
* SolarOnly post-surplus hold + restart debounce for solar modes ([#755](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/755), [#757](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/757)) ([#759](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/759)) ([212c3bd](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/212c3bdae0cddc4ed4f7b8590e066eda136f9507))
* update_baseline script (T1.1, issue [#708](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/708)) ([#735](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/735)) ([53f8774](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/53f8774a107384c0edbd09c6b0f9b21b6099710a))


### Bug Fixes

* omit Power-flow solar-surplus tile when solar_available is off ([#849](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/849)) ([90d1a75](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/90d1a758b67a251c3ac74444fdeac49a374d0856)), closes [#814](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/814)
* revert the unconsumed prompt_timeout_h config-flow field ([#818](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/818)) ([da7c334](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/da7c334a9a232e770863bae5bd03c24c53d0db67))
* route Manual mode dispatch through the ADR-0017 policy registry ([#731](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/731)) ([89f3fe9](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/89f3fe981c7529716ef2673e257d1c33f1cf9755))

## [0.3.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.1...v0.3.0) (2026-08-17)


### Features

* add Captar mode engine (E1) state machine per UC03 ([#254](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/254)) ([c888f19](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c888f195a8c4be800a9cdfaf04c421b7d69e7699)), closes [#222](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/222)
* add config keys for battery capacity, solar step-up, and solar-reserve cap (R8/R9/R15) ([#343](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/343)) ([d6f0bfb](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/d6f0bfb49abf91cd4a53c3bce7677e6db1ad816c))
* add config keys for CapTar-available toggle + peak protection + Captar cooldown + R17 opt-out ([#260](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/260)) ([5173dda](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5173dda18bd5bf92463188286545aafe5e06793e)), closes [#224](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/224)
* add Deadline engine -- departure-deadline resolution (E4, R14) ([#347](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/347)) ([c02ef4d](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c02ef4d4aca451c4d1dba767346c705e56d206d8))
* add device_class/state_class/entity_category to diagnostic sensors ([#649](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/649)) ([#657](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/657)) ([5ab3af2](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5ab3af209e52c6e56c1b84e10ae259255c5be3a8))
* add ManualPolicy mode-selection pass-through (ADR-0017 T1) ([#638](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/638)) ([7389e03](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/7389e03a0c4f090e836a1e548a4f4819ee0e286b)), closes [#551](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/551)
* add per-step schema fragments for the guided config flow (T1) ([#695](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/695)) ([147402e](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/147402ef17fa0649a22f7e414741ad692800d61f))
* add the step table and shared dispatcher for the guided config flow (T2) ([#698](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/698)) ([8ae0864](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/8ae0864cc87209905d196a1f29d97a7651e870a0))
* delete flat config-flow schema and pin extensibility (T13) ([#713](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/713)) ([7fea40b](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/7fea40be02df5e789e11e282f947508df76a7749))
* implement dashboard-prerequisite diagnostic sensors ([#602](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/602)) ([#626](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/626)) ([b9f9034](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/b9f903418bf466fbbc0c687c396201c595b751d9))
* implement the runtime dashboard (C5, [#601](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/601)) ([#635](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/635)) ([1174c35](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/1174c35a25aa7895ec0eaa75584a6feae16d85aa))
* install happy path -- core -&gt; mappings -&gt; thresholds -&gt; create entry (T3) ([#699](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/699)) ([545e837](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/545e8377ce2dd463bc37151d2a7ab8df56691020))
* publish DeadlineUnreachableCleared on the unreachable clearing edge (R5/ADR-0024) ([#672](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/672)) ([03680bf](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/03680bff6548f56f27ada145f5e2a4221e976398))
* re-arm the R5 notify-once latch on DeadlineUnreachableCleared (M3, ADR-0024) ([#673](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/673)) ([cde918b](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/cde918b5131cb3d6b5b6637e1f3a864275cf9bdf))
* the CapTar step, and the once-only EV state-of-charge mapping (T5) ([#701](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/701)) ([996487e](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/996487ec205d8bdc9299c24ca8357ef178ba1e76))
* the deadline step (T6) ([#702](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/702)) ([7d75b54](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/7d75b54e8cdd8c4fed4bf056e5818d28c675d353))
* the options flow's own table (T10) ([#709](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/709)) ([0d23770](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/0d2377095a4c9a2346248958f1be3dbaf8c428eb))
* the reconfigure flow (T9) ([#705](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/705)) ([702436b](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/702436b5b641378effb8869c53aa2d65f137894f))
* the solar step (T4) ([#700](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/700)) ([e9ea4be](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/e9ea4bec3017678b70c5cacd25dd837af5c487c4))
* the vehicle-charge-limit step, and removal of the validation safety net (T7) ([#703](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/703)) ([01cfbe6](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/01cfbe69fa7e6f82ec5d9a9b2fa3051c5cb644b2))


### Bug Fixes

* cap saturated required_a before it reaches notification payload ([#650](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/650)) ([#663](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/663)) ([d1d1e56](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/d1d1e56d5cd229c768c21d47769887f422193c6b))
* close no-magic-strings gaps for hass.data key, sensor status, config-flow error codes ([#523](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/523)) ([f902bcb](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/f902bcbdec6c907aa25b7f367bafe1787c4a9c29)), closes [#508](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/508)
* correct jq is_error gate misreading a successful AI run as errored ([#518](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/518)) ([cb07de7](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/cb07de7b9ae091bbc8d10b11d70f502fbf7d07d8)), closes [#517](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/517)
* don't advance adapter_readings_at on an ev_soc-fault cycle ([#648](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/648)) ([#658](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/658)) ([7f73c55](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/7f73c55544ec9f8a31e84048176be84b4dbfa555))
* expire NotifyAdapter answers, unsubscribe on reload, wire into factory ([#511](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/511)) ([df7200e](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/df7200ecac6fc172e5f44d94ad26005fc801962a)), closes [#498](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/498)
* gate departure-time entities' sc_runtime label on deadline_available ([#674](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/674)) ([#694](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/694)) ([273f0f7](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/273f0f75882b6aafcd57cb090bd9f170f082b099))
* guard against a second config entry for the same charger ([#513](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/513)) ([753fe50](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/753fe50e9bdb205e3d6ac50ace5f50780fa956fe)), closes [#500](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/500)
* guard malformed time.fromisoformat restore in time.py ([#643](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/643)) ([8e39745](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/8e39745d382cf0850b345cf5bb353d7dd77ac022)), closes [#571](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/571)
* label PR needs-approval on a clean AI review verdict ([#433](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/433)) ([8594861](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/85948619e06ac07668a49821f5bb1efb56b4ad1d))
* prefill reconfigure form with existing entity-role mappings ([#509](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/509)) ([5395d9c](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5395d9c6ff24364db29a9cfe262e683b7d78e574)), closes [#499](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/499)
* promote amp-step rounding constants to const.py, restore leaf-module boundary ([#520](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/520)) ([4a8a8f7](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/4a8a8f7cd0f386bb4ca852c779eb2731444296c2)), closes [#502](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/502)
* remove dead min_a parameter from SolarOnly.step() ([#519](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/519)) ([8644666](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/8644666fc5723a1fb32499abb82094ac048967ec)), closes [#501](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/501)
* resolve active-SOC-limit sensor id through the Store, not a hardcoded literal ([#593](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/593)) ([24bd8b5](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/24bd8b5c66047dafcead890d66b69ff7e3b97038)), closes [#562](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/562)
* restore _role_readings caching lost in _resolve_deadline_and_reserve extraction ([#634](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/634)) ([ecd1493](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/ecd14939cbff2fb4db23e6b9ad8b90fac00d5648))
* seed monthly-peak restore through PeakDemandState, not private fields ([#512](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/512)) ([bd0b888](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/bd0b888afbe4f0cbb2982addebd1236c582d9306)), closes [#496](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/496)
* type progressively-filled CycleContext fields as None, not a plausible default ([#664](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/664)) ([0176241](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/01762413672761af404352015a2445b0dd8369bc))
* validate mode membership in set_active_mode; correct stale docstrings ([#641](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/641)) ([a952906](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/a95290691d498555e695c9acb46cbcede58ef570)), closes [#569](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/569)

## [0.2.1](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.0...v0.2.1) (2026-07-20)


### Bug Fixes

* **ci:** let release-please own tagging + Release creation ([#184](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/184)) ([#185](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/185)) ([b3ff5e9](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/b3ff5e96296776a9307c126bf132555def62b8f6))

## [0.2.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.1.0...v0.2.0) (2026-07-20)


### Features

* add Power mode engine (E1 slice) with status gating ([#163](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/163)) ([037d6f8](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/037d6f809d34a2f93e82527f86ba7e5826f5a4c9)), closes [#101](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/101)
* add Signal-Conditioning engine (E7) NF4 voltage fallback ([#166](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/166)) ([e0d1633](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/e0d1633f21137763480fe670cccb7c4a9926eb5d)), closes [#104](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/104)


### Bug Fixes

* bump homeassistant to 2026.7.2, fixing Dependabot alert [#1](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1) ([#180](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/180)) ([4975482](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/497548298ee07ab8f6571144270ad338ea8d4a2c))
