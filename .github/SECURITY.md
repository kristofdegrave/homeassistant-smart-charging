# Security Policy

## Supported versions

Smart Charging is in pre-1.0 development (Power-mode MVP). Only the **latest
release** receives security fixes — please update to the newest version before
reporting an issue.

| Version        | Supported |
| -------------- | --------- |
| Latest release | ✅        |
| Older releases | ❌        |

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, use GitHub's private vulnerability reporting:

1. Go to the repository's [Security tab](https://github.com/kristofdegrave/homeassistant-smart-charging/security).
2. Click **Report a vulnerability** and fill in the advisory form.

Please include:

- A description of the vulnerability and its impact.
- Steps to reproduce (Home Assistant version, integration version, configuration).
- Any suggested fix, if you have one.

You can expect an acknowledgement within **7 days**. Once confirmed, a fix is
developed privately and released before the advisory is published.

## Scope

This is a Home Assistant custom integration that controls EV charging
hardware. Reports of particular interest:

- Anything allowing **unauthorized control of a charger** (start/stop charging,
  current changes) beyond what Home Assistant's own access control permits.
- Leaking of credentials, tokens, or other secrets from the config entry or logs.
- Code execution or injection via configuration values or entity states.

Issues in Home Assistant itself should be reported to the
[Home Assistant security policy](https://www.home-assistant.io/security/),
and issues in third-party dependencies to their respective projects.
