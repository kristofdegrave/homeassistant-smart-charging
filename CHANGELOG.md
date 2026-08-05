# Changelog

## [0.3.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.1...v0.3.0) (2026-08-05)


### Features

* add Captar mode engine (E1) state machine per UC03 ([#254](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/254)) ([c888f19](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c888f195a8c4be800a9cdfaf04c421b7d69e7699)), closes [#222](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/222)
* add config keys for battery capacity, solar step-up, and solar-reserve cap (R8/R9/R15) ([#343](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/343)) ([d6f0bfb](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/d6f0bfb49abf91cd4a53c3bce7677e6db1ad816c))
* add config keys for CapTar-available toggle + peak protection + Captar cooldown + R17 opt-out ([#260](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/260)) ([5173dda](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5173dda18bd5bf92463188286545aafe5e06793e)), closes [#224](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/224)
* add Deadline engine -- departure-deadline resolution (E4, R14) ([#347](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/347)) ([c02ef4d](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c02ef4d4aca451c4d1dba767346c705e56d206d8))


### Bug Fixes

* close no-magic-strings gaps for hass.data key, sensor status, config-flow error codes ([#523](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/523)) ([f902bcb](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/f902bcbdec6c907aa25b7f367bafe1787c4a9c29)), closes [#508](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/508)
* correct jq is_error gate misreading a successful AI run as errored ([#518](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/518)) ([cb07de7](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/cb07de7b9ae091bbc8d10b11d70f502fbf7d07d8)), closes [#517](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/517)
* expire NotifyAdapter answers, unsubscribe on reload, wire into factory ([#511](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/511)) ([df7200e](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/df7200ecac6fc172e5f44d94ad26005fc801962a)), closes [#498](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/498)
* guard against a second config entry for the same charger ([#513](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/513)) ([753fe50](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/753fe50e9bdb205e3d6ac50ace5f50780fa956fe)), closes [#500](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/500)
* label PR needs-approval on a clean AI review verdict ([#433](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/433)) ([8594861](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/85948619e06ac07668a49821f5bb1efb56b4ad1d))
* prefill reconfigure form with existing entity-role mappings ([#509](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/509)) ([5395d9c](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5395d9c6ff24364db29a9cfe262e683b7d78e574)), closes [#499](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/499)
* promote amp-step rounding constants to const.py, restore leaf-module boundary ([#520](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/520)) ([4a8a8f7](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/4a8a8f7cd0f386bb4ca852c779eb2731444296c2)), closes [#502](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/502)
* remove dead min_a parameter from SolarOnly.step() ([#519](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/519)) ([8644666](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/8644666fc5723a1fb32499abb82094ac048967ec)), closes [#501](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/501)
* seed monthly-peak restore through PeakDemandState, not private fields ([#512](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/512)) ([bd0b888](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/bd0b888afbe4f0cbb2982addebd1236c582d9306)), closes [#496](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/496)

## [0.2.1](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.0...v0.2.1) (2026-07-20)


### Bug Fixes

* **ci:** let release-please own tagging + Release creation ([#184](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/184)) ([#185](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/185)) ([b3ff5e9](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/b3ff5e96296776a9307c126bf132555def62b8f6))

## [0.2.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.1.0...v0.2.0) (2026-07-20)


### Features

* add Power mode engine (E1 slice) with status gating ([#163](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/163)) ([037d6f8](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/037d6f809d34a2f93e82527f86ba7e5826f5a4c9)), closes [#101](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/101)
* add Signal-Conditioning engine (E7) NF4 voltage fallback ([#166](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/166)) ([e0d1633](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/e0d1633f21137763480fe670cccb7c4a9926eb5d)), closes [#104](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/104)


### Bug Fixes

* bump homeassistant to 2026.7.2, fixing Dependabot alert [#1](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1) ([#180](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/180)) ([4975482](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/497548298ee07ab8f6571144270ad338ea8d4a2c))
