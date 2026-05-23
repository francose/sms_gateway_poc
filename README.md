# Carrier email-to-SMS gateways — study + runnable PoCs

A reference repo on legacy SMTP-to-SMS bridges run by US mobile carriers,
how red teams abuse them for spear-phishing, and what defenders see on the
other side. Every vector has:

1. A markdown writeup in [`attack_vectors/`](attack_vectors/) — mechanism,
   spoof surface, real-world examples, mitigation.
2. A self-contained runnable PoC in [`pocs/`](pocs/) that talks to a real
   gateway and shows what arrives on the handset.
3. A defender script ([`pocs/99_detect_gateway_msg.py`](pocs/99_detect_gateway_msg.py))
   that scans IMAP/.eml dumps for the artifacts gateway-relayed SMS leaves
   behind.

Headline vector: **sender spoofing via domain-aligned From: headers on
carriers that surface the local-part of the email address as the SMS
sender**. AT&T was the canonical target for years; Verizon killed their
gateway in 2022; T-Mobile still works in 2026 with stricter filtering.

---

## Quick start

```bash
git clone https://github.com/francose/sms_gateway_poc.git
cd sms_gateway_poc

# Send a hello-world to your own phone via Gmail SMTP
export SMTP_USER="you@gmail.com"
export SMTP_APP_PW="xxxx xxxx xxxx xxxx"
python pocs/01_basic_gateway_send.py --to 2155551234 --carrier tmobile \
    --body "POC inbound, check the sender field"

# Direct-to-MX (no auth SMTP, your own mail server)
python pocs/02_direct_to_mx.py --to 2155551234 --carrier att \
    --from-domain yourdomain.tld --body "direct MX path"

# Fan out to every gateway when carrier is unknown (recon)
python pocs/03_carrier_fanout.py --to 2155551234 --body "which one lands?"

# Defender: scan an mbox / .eml dump for gateway-relayed SMS artifacts
python pocs/99_detect_gateway_msg.py samples/

# Look up the carrier domains list
python tools/gateway_domains.py --list
python tools/gateway_domains.py --carrier att
```

No external dependencies — Python 3.10+ stdlib only (`smtplib`, `email`,
`dnspython` only for the direct-MX PoC, optional).

---

## What's in the box

### Study guide

- [`carrier_gateway_study.md`](carrier_gateway_study.md) — the top-level
  reference: how the gateways work, why they exist, recon, spoofing,
  defender view, why the vector is dying.
- [`attack_vectors/`](attack_vectors/) — one short markdown per vector
  for quick lookup or linking from issues / PRs:
  - `01_gateway_discovery.md`
  - `02_sender_spoofing.md`
  - `03_direct_to_mx.md`
  - `04_mms_vs_sms_gateway.md`
  - `05_defender_artifacts.md`

### Operator tools (red-team / authorized testing)

| Script | Output |
|--------|--------|
| `tools/gateway_domains.py` | Canonical list of US carrier email-to-SMS gateways (SMS + MMS variants), with status notes (`active`, `mms-only`, `dead`). Pipe-friendly. |
| `tools/carrier_lookup.py`  | Free / paid carrier lookup helpers — wraps `numverify`, `twilio-lookup`, and a fallback HTTP scraper. Returns carrier name + likely gateway domain. |

### Runnable PoCs

Each script prints a labelled walkthrough — SMTP envelope, From: header
treatment, gateway response code, and (where possible) a hint on how the
message will render on the handset.

| Script | What it does |
|--------|--------------|
| `pocs/01_basic_gateway_send.py`     | Auth-SMTP submission via Gmail / any provider. Default starting point. |
| `pocs/02_direct_to_mx.py`           | Resolves carrier MX, talks port 25 from your own MTA. Bypasses provider DMARC filtering on outbound. |
| `pocs/03_carrier_fanout.py`         | Sends to every known gateway in parallel. Recon mode when carrier is unknown. |
| `pocs/04_spoofed_from_header.py`    | Demonstrates the From: local-part spoof on carriers that render it as the SMS sender. |
| `pocs/99_detect_gateway_msg.py`     | Defender side. Scans a tree of `.eml` / mbox for the headers, hops, and structural tells of a gateway-relayed SMS. |

---

## Why this matters in 2026

Carrier email-to-SMS gateways have been around since the late 1990s as a
free paging channel for sysadmins. Red teams discovered fast that:

- They cost nothing and need no number to send.
- The sender rendering on the handset is partially attacker-controlled.
- The message arrives as a native SMS, not a "from unknown app" warning.

The defensive side has caught up unevenly:

- **Verizon** killed `vtext.com` outright in 2022 after sustained abuse.
- **AT&T** now enforces SPF/DKIM/DMARC on inbound to `txt.att.net` and
  filters lookalike domains aggressively.
- **T-Mobile**, **US Cellular**, and several MVNOs still run the legacy
  bridges with looser filtering. T-Mobile's `tmomail.net` is the most
  commonly active gateway in 2026.
- **Google Fi** requires strict SPF/DKIM pass — hard target for spoofing.

The realistic abuse pattern in 2026 is **low-volume spear-phishing against
employees of companies whose owned domains lack DMARC `p=reject`**, on
T-Mobile or AT&T lines, using a typosquat of the employer's domain. Spray
and pray is dead — carrier RBLs and CAN-SPAM enforcement closed it.

---

## Authorized testing only

Run these PoCs against your own phone or a phone you have written
permission to test. Sending unsolicited SMS to anyone else's number is
illegal under TCPA and CAN-SPAM in the United States and similar statutes
elsewhere. This repo is a study aid, not a phishing kit.
