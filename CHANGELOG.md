# Changelog

## [0.3.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.1...v0.3.0) (2026-07-23)


### Features

* add Captar mode engine (E1) state machine per UC03 ([#254](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/254)) ([c888f19](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c888f195a8c4be800a9cdfaf04c421b7d69e7699)), closes [#222](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/222)
* add config keys for battery capacity, solar step-up, and solar-reserve cap (R8/R9/R15) ([#343](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/343)) ([d6f0bfb](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/d6f0bfb49abf91cd4a53c3bce7677e6db1ad816c))
* add config keys for CapTar-available toggle + peak protection + Captar cooldown + R17 opt-out ([#260](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/260)) ([5173dda](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/5173dda18bd5bf92463188286545aafe5e06793e)), closes [#224](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/224)
* add Deadline engine -- departure-deadline resolution (E4, R14) ([#347](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/347)) ([c02ef4d](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/c02ef4d4aca451c4d1dba767346c705e56d206d8))

## [0.2.1](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.2.0...v0.2.1) (2026-07-20)


### Bug Fixes

* **ci:** let release-please own tagging + Release creation ([#184](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/184)) ([#185](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/185)) ([b3ff5e9](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/b3ff5e96296776a9307c126bf132555def62b8f6))

## [0.2.0](https://github.com/kristofdegrave/homeassistant-smart-charging/compare/v0.1.0...v0.2.0) (2026-07-20)


### Features

* add Power mode engine (E1 slice) with status gating ([#163](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/163)) ([037d6f8](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/037d6f809d34a2f93e82527f86ba7e5826f5a4c9)), closes [#101](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/101)
* add Signal-Conditioning engine (E7) NF4 voltage fallback ([#166](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/166)) ([e0d1633](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/e0d1633f21137763480fe670cccb7c4a9926eb5d)), closes [#104](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/104)


### Bug Fixes

* bump homeassistant to 2026.7.2, fixing Dependabot alert [#1](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/1) ([#180](https://github.com/kristofdegrave/homeassistant-smart-charging/issues/180)) ([4975482](https://github.com/kristofdegrave/homeassistant-smart-charging/commit/497548298ee07ab8f6571144270ad338ea8d4a2c))
