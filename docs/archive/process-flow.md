# Smart Charging — Process Flow

Mermaid diagrams for the coordinator control loop and each mode module.
Derived from [smart-charging.requirements.md](smart-charging.requirements.md) and [use-cases.md](use-cases.md).

---

## Coordinator Control Loop

Runs every `sc_control_interval_s` seconds.

```mermaid
flowchart TD
    A([Control cycle start]) --> B[Read raw sensors\nnet_w · solar_w · charger_w\nev_soc · charger_status]
    B --> C[Update 4-reading rolling average\nsmoothed_net_w · smoothed_solar_w]
    C --> D{charger_status\n== disconnected?}
    D -- Yes --> E[Set 0 A]
    E --> F{Plug-in reminder\nconditions met?\nUC14}
    F -- Yes --> G[Send mobile notification\nonce per plug-out cycle]
    F -- No --> H([End cycle])
    G --> H

    D -- No --> I[Resolve active SOC limit\nUC8 / R2d]
    I --> J{ev_soc >=\nactive_soc_limit?}
    J -- Yes --> K[Set 0 A\ncharging complete]
    K --> H

    J -- No --> L{sc_active_profile?}
    L -- Solar --> M[solar.py]
    L -- SolarOnly --> N[solar_only.py]
    L -- Captar --> O[captar.py]
    L -- Power --> P[power.py]
    L -- Off --> Q[Return 0 A]

    M & N & O & P & Q --> R[candidate_amps]

    R --> S{candidate_amps == 0?\nmode conditions not met}
    S -- Yes --> T{Urgency check R5\ncan car reach active_soc_limit\nby departure at current rate?}
    T -- Yes, on track --> U[Keep 0 A\nno urgency needed]
    T -- No, will miss deadline --> V[Compute required_amps\nR5 formula]
    V --> W{required_amps\n<= peak_headroom?}
    W -- Yes --> X[candidate_amps = max6, required_amps]
    W -- No, even 6A exceeds headroom --> Y[candidate_amps = 6 A\nemit deadline warning]
    X & Y --> Z[candidate_amps from urgency]

    S -- No, mode returned amps --> AA[candidate_amps from mode]

    Z & AA & U --> AB{Peak safety check\nraw: net_w + candidate_delta\n> effective_peak_limit?\nR3 · UC9}
    AB -- Yes, even 6A breaches --> AC[Set 0 A\npeak breach — stop]
    AB -- No breach --> AD{candidate_amps\nbetween 1–5 A?\nC1}
    AD -- Yes --> AE[Snap to 6 A or 0 A]
    AD -- No --> AF[Send set-point to charger]
    AE --> AF
    AC --> H
    AF --> H
    U --> H
```

---

## Active SOC Limit Resolution (UC8 / R2d)

```mermaid
flowchart TD
    A([Resolve active SOC limit]) --> B{WFH reservation active?\nsc_wfh_tomorrow = on\nAND solar forecast > 12 kWh}
    B -- Yes --> C{sun.sun\n= below_horizon?}
    C -- Yes --> D[active_soc_limit = 60%\nnight cap]
    C -- No --> E{Solar step-up\nin effect?}
    B -- No --> E
    E -- Yes --> F[active_soc_limit =\nstepped-up value]
    E -- No --> G[active_soc_limit =\nsc_active_soc\ndefault 80%]
    D & F & G --> H([Return active_soc_limit])
```

---

## Solar Mode (`flow/solar.py`)

**State machine:** `IDLE` → `COOLDOWN` → `CHARGING` → `HOLD` → `COOLDOWN` → …

- **Start threshold:** smoothed surplus ≥ 150 W (first start or after cooldown)
- **Restart threshold:** smoothed surplus ≥ 230 W sustained for the full 2-min cooldown
- **Stop trigger:** smoothed surplus = 0 W (charger fully grid-fed)
- **Hold:** 5 min at 6 A before stopping; cancelled if solar recovers during hold
- **Cooldown:** 2 min; surplus must stay ≥ 230 W throughout to qualify for restart

```mermaid
flowchart TD
    A([solar.py]) --> B{State?}

    B -- IDLE --> C{smoothed_surplus\n>= 150 W?}
    C -- No --> D[Return 0 A]
    C -- Yes --> E[Transition → CHARGING\nReturn 6 A]

    B -- COOLDOWN --> F{cooldown elapsed\n>= 2 min?}
    F -- No --> G{smoothed_surplus\n>= 230 W throughout\ncooldown so far?}
    G -- No --> H[Reset cooldown timer\nReturn 0 A]
    G -- Yes → still waiting --> D2[Return 0 A]
    F -- Yes AND surplus sustained --> I[Transition → CHARGING\nReturn 6 A]
    F -- Yes BUT surplus dropped --> J[Transition → IDLE\nReturn 0 A]

    B -- CHARGING --> K[proposed_amps =\ncurrent_amps + floor−smoothed_net_w ÷ 230\nclamp to 6–32 A]
    K --> L{smoothed_surplus\n= 0 W?}
    L -- Yes → grid-fed --> M[Transition → HOLD\nstart 5-min timer\nReturn 6 A]
    L -- No --> N[Return proposed_amps]

    B -- HOLD --> O{smoothed_surplus\n> 0 W?}
    O -- Yes → solar returned --> P[Cancel hold\nTransition → CHARGING\nproposed_amps as above]
    O -- No --> Q{hold elapsed\n>= 5 min?}
    Q -- No --> R[Return 6 A\nstill holding]
    Q -- Yes --> S[Transition → COOLDOWN\nstart 2-min timer\nReturn 0 A]

    D & D2 & E & H & I & J & M & N & P & R & S --> T([candidate_amps])
```

---

## SolarOnly Mode (`flow/solar_only.py`)

**State machine:** `IDLE` → `COOLDOWN` → `CHARGING` → `COOLDOWN` → …

- **Start threshold:** smoothed surplus ≥ 1300 W
- **Restart threshold:** smoothed surplus ≥ 1300 W sustained for the full 2-min cooldown
- **Stop trigger:** smoothed surplus < 1300 W — immediate stop, no hold
- **No grid fallback** — never charges below 1300 W surplus regardless of minimum current

```mermaid
flowchart TD
    A([solar_only.py]) --> B{State?}

    B -- IDLE --> C{smoothed_surplus\n>= 1300 W?}
    C -- No --> D[Return 0 A]
    C -- Yes --> E[Transition → CHARGING\nReturn 6 A]

    B -- COOLDOWN --> F{cooldown elapsed\n>= 2 min?}
    F -- No --> G{smoothed_surplus\n>= 1300 W throughout\ncooldown so far?}
    G -- No --> H[Reset cooldown timer\nReturn 0 A]
    G -- Yes → still waiting --> D2[Return 0 A]
    F -- Yes AND surplus sustained --> I[Transition → CHARGING\nReturn 6 A]
    F -- Yes BUT surplus dropped --> J[Transition → IDLE\nReturn 0 A]

    B -- CHARGING --> K{smoothed_surplus\n>= 1300 W?}
    K -- No → stop immediately --> L[Transition → COOLDOWN\nstart 2-min timer\nReturn 0 A]
    K -- Yes --> M[proposed_amps =\ncurrent_amps + floor−smoothed_net_w ÷ 230\nclamp to 6–32 A\nReturn proposed_amps]

    D & D2 & E & H & I & J & L & M --> N([candidate_amps])
```

---

## Captar Mode (`flow/captar.py`)

**State machine:** `IDLE` → `COOLDOWN` → `CHARGING` → `COOLDOWN` → …

- **Charging gate:** cheap-tariff window (weekdays 22:00–07:00, weekends all day) OR urgency
- **WFH suppression:** if WFH reservation active AND sun below horizon → treat as outside tariff window (urgency can still override)
- **Current:** max available under peak limit each cycle: `floor((peak_limit_W − raw_net_w) / 230)`, clamped 6–32 A
- **Stop triggers:** (1) peak headroom breach even at 6A, (2) tariff window ends with no urgency — both start 10-min cooldown
- **Cooldown:** 10 min after any stop; restarts only when cooldown done AND gate condition met

```mermaid
flowchart TD
    A([captar.py]) --> B{10-min cooldown\nactive?}
    B -- Yes --> C[Return 0 A]

    B -- No --> D{In cheap-tariff window?}
    D -- No --> E{Urgency?\nwill miss deadline\nat current rate}
    E -- No --> F[Return 0 A\nnot charging — idle, no cooldown]
    E -- Yes → urgency --> G[Compute required_amps\nR5 formula]

    D -- Yes --> H{WFH reservation active\nAND sun below horizon?}
    H -- Yes → suppressed --> I{Urgency?}
    I -- No --> F
    I -- Yes --> G

    H -- No → open window --> J[Compute headroom_amps\nfloor peak_limit_W − raw_net_w ÷ 230]

    G --> K[candidate = max6, required_amps\ncapped to headroom_amps]
    J --> L[candidate = headroom_amps]

    K & L --> M{State == CHARGING\nAND tariff window just ended\nAND no urgency?}
    M -- Yes --> N[Transition → COOLDOWN\nstart 10-min timer\nReturn 0 A]

    M -- No --> O{candidate < 6?\npeak breach at minimum}
    O -- Yes --> P[Transition → COOLDOWN\nstart 10-min timer\nReturn 0 A]
    O -- No --> Q[Transition → CHARGING\nReturn candidate_amps]

    C & F & N & P & Q --> R([candidate_amps])
```

---

## Power Mode (`flow/power.py`)

```mermaid
flowchart TD
    A([power.py]) --> B[Read sc_power_mode_amps\nrange 6–32 A]
    B --> C[Return sc_power_mode_amps\nno solar or peak logic here\ncoordinator peak-check still applies]
    C --> D([candidate_amps])
```

---

## Solar SOC Step-Up (UC6 / R2b)

Runs as a side-effect check within each Solar / SolarOnly cycle, after the main amps calculation.

```mermaid
flowchart TD
    A([SOC step-up check]) --> B{Active profile\n= Solar or SolarOnly?}
    B -- No --> Z([No-op])
    B -- Yes --> C{10-min step-up\ncooldown active?}
    C -- Yes --> Z
    C -- No --> D{ev_soc >=\ncurrent_charge_limit − 2%?}
    D -- No --> Z
    D -- Yes --> E{current_charge_limit\n+ 5% > sc_max_solar_soc?}
    E -- Yes --> F[Set charge limit =\nsc_max_solar_soc]
    E -- No --> G[Set charge limit =\ncurrent + 5%]
    F & G --> H[Start 10-min cooldown]
    H --> I{ev_soc >=\nsc_max_solar_soc?}
    I -- Yes --> J[Set 0 A\nmax SOC reached — stop]
    I -- No --> Z
```

---

## Plug-In Reminder (UC14 / R8)

Checked at the end of each coordinator cycle when `charger_status = disconnected`.

```mermaid
flowchart TD
    A([Plug-in reminder check]) --> B{Car at home?\ndevice_tracker = home}
    B -- No --> Z([No-op])
    B -- Yes --> C{ev_soc <\nactive_soc_limit?}
    C -- No --> Z
    C -- Yes --> D{now >= departure_time − 8h?}
    D -- No --> Z
    D -- Yes --> E{Notification already\nsent this plug-out cycle?}
    E -- Yes --> Z
    E -- No --> F[Send mobile notification\nmark sent for this cycle]
    F --> Z
```

---

## WFH Evening Notification (UC15 / R2c)

Time-triggered automation — not part of the coordinator loop.

```mermaid
flowchart TD
    A([18:00 daily trigger]) --> B[Send actionable\nmobile notification\nWFH tomorrow?]
    B --> C{User responds\nbefore 20:00?}
    C -- Yes → Yes --> D[sc_wfh_tomorrow = on]
    C -- Yes → No --> E[sc_wfh_tomorrow = off]
    C -- No response --> E
    D & E --> F([End])

    G([00:00 daily trigger]) --> H[sc_wfh_tomorrow = off\nreset for next evening]
    H --> F
```
