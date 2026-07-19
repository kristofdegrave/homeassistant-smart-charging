"""Constants for the Smart Charging integration."""

DOMAIN = "smart_charging"

# Canonical charger states (ADR-0003 / glossary). Never add a fourth without a glossary change.
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTED = "connected"
STATE_CHARGING = "charging"

# The canonical states in which commanding current is appropriate.
CHARGEABLE_STATES = (STATE_CONNECTED, STATE_CHARGING)

# Defaults
DEFAULT_NOMINAL_VOLTAGE = 230.0
DEFAULT_CONTROL_INTERVAL_S = 10
