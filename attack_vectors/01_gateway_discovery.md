# 01 — Gateway discovery

## What

Carrier email-to-SMS gateways are MX-published SMTP servers run by each
mobile carrier. Address format: `<10-digit>@<gateway-domain>`.

## How to discover

1. **DNS only**: `dig MX tmomail.net`. If MX resolves and accepts mail on
   port 25, the bridge is alive. Confirms presence, not deliverability.
2. **Public lists**: every carrier has historically documented the domain
   in support pages. Lists rot — Verizon's `vtext.com` is still in many
   third-party tables despite being shut down since 2022. See
   `tools/gateway_domains.py` for the current verified set.
3. **Test send**: send to your own number on each candidate gateway. The
   one that reaches your handset is the live mapping for your carrier.
4. **MNP lookup**: real-time carrier of a number, post-portability. Free
   tier on most lookup services covers small-scale recon.

## Mechanism

The gateway MTA accepts inbound, strips MIME and most headers, maps the
local-part of the recipient address (the 10-digit number) to a subscriber
MSISDN, and injects into the carrier SMSC. No subscriber consent or
opt-in check.

## 2026 status

| Live | Dead / unreliable |
|------|-------------------|
| `txt.att.net`, `mms.att.net` | `vtext.com` (Verizon SMS, killed 2022) |
| `tmomail.net` (T-Mobile + MVNOs) | `messaging.sprintpcs.com` (Sprint, dead after T-Mobile merger) |
| `msg.fi.google.com` (Fi) | `messaging.nextel.com` (Nextel, dead) |
| `email.uscc.net` (US Cellular) | `mobile.celloneusa.com` (legacy, dead) |
| `sms.cricketwireless.net` | `myboostmobile.com` (dead since Boost moved to T-Mobile) |

## Mitigation

Operator side: keep your gateway list refreshed against test sends. A
dead gateway in a fan-out wastes envelope budget and leaves email trails
in dead MTAs (some of which now belong to spam researchers).

Defender side: this stage is silent — no observable signal until the
operator sends real traffic.
