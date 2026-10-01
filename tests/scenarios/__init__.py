"""Scenario/timeline test tier (ADR-0037, epic #996).

Mirrors no product package (ADR-0037's Consequences leave this directory's placement to the
paired implementation spec): every engine live and binding, over a timeline of many
consecutive cycles, against readings a test-only plant simulator derives -- including its
configured charger-power-reading lag -- rather than hand-seeded, self-consistent values.

``plant.py`` is the world (household load, the charger's true draw and its lagging power
reading, the meter's derived net import); ``runner.py`` drives it through real
``async_setup`` + ``coordinator.async_refresh()`` cycles, one plant step per cycle, via the
same ``tests/helpers.py`` seeding path (``seed_charger_states``/
``capture_charger_current_writes``) the existing HA-harness suites use. Product code takes no
dependency on either module (ADR-0037).
"""
