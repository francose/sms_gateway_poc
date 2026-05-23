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

For the **full kill chain** — MITRE ATT&CK mapping, a sanitized worked
example, vector comparison against Twilio / SS7 / iMessage, threat-actor
attribution, and defender leverage points per stage — see
[`attack_chain.md`](attack_chain.md).

Headline vector: **sender spoofing via domain-aligned From: headers on
carriers that surface the local-part of the email address as the SMS
sender**. AT&T was the canonical target for years but **retired their
gateway entirely by 2026** (zone exists, zero MX records). The three
big surviving gateways — T-Mobile's `tmomail.net`, Verizon's
`vtext.com`, and Verizon's `vzwpix.com` — are all now fronted by
**Proofpoint Cloudmark** (`*.cloudfilter.net`). Empirical 2026-05-23
recon in [`samples/recon_2026-05-23.md`](samples/recon_2026-05-23.md)
documents the current state.

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
  defender view, why the vector is consolidating.
- [`attack_chain.md`](attack_chain.md) — full kill chain. Where this
  vector sits in the broader smishing landscape, MITRE ATT&CK
  mapping per stage, sanitized worked example, vector comparison,
  threat actor attribution, defender leverage points.
- [`attack_vectors/`](attack_vectors/) — one short markdown per vector
  for quick lookup or linking from issues / PRs:
  - `01_gateway_discovery.md`
  - `02_sender_spoofing.md`
  - `03_direct_to_mx.md`
  - `04_mms_vs_sms_gateway.md`
  - `05_defender_artifacts.md`
- [`samples/recon_2026-05-23.md`](samples/recon_2026-05-23.md) — raw
  DoH + dig evidence behind the 2026 inventory. Reproduction commands
  inline. Refreshed any time the inventory changes.

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

## Where this fits in the broader smishing landscape

This is **one entry point** into mobile phishing kill chains. The full
walkthrough — including the MITRE mapping, threat-actor attribution,
and the seven-stage breakdown from recon to account takeover — lives in
[`attack_chain.md`](attack_chain.md). A short summary:

- **MITRE ATT&CK coverage**: T1598, T1583.001, T1583.004, T1660,
  T1566.003, T1204.001, T1056.003, T1539, T1078.001.
- **Why operators still pick this path in 2026**: no KYC, no
  10DLC fees, lookalike sender names, better attribution-deniability
  than Twilio.
- **The only control that defeats the chain**: phishing-resistant MFA
  (FIDO2 / hardware tokens). SMS OTP and TOTP both fall to Evilginx2-
  style real-time MFA relay.

## Why this matters in 2026

Carrier email-to-SMS gateways have been around since the late 1990s as a
free paging channel for sysadmins. Red teams discovered fast that:

- They cost nothing and need no number to send.
- The sender rendering on the handset is partially attacker-controlled.
- The message arrives as a native SMS, not a "from unknown app" warning.

The defensive side has consolidated since 2022 (rewritten 2026-05-23
against empirical recon):

- **AT&T retired their gateway entirely.** `txt.att.net` and
  `mms.att.net` zones exist but publish zero MX records. No mail is
  accepted. Cricket (AT&T MVNO) followed and now resolves to an Akamai
  web redirect.
- **Verizon did not kill `vtext.com`** despite the widely-cited 2022
  shutdown claim. The zone still publishes MX records pointing at
  Proofpoint Cloudmark. What was killed was permissive delivery — the
  bridge persists for authenticated, properly-aligned business senders.
- **T-Mobile, Verizon SMS, and Verizon MMS all sit behind Proofpoint
  Cloudmark** (`*.cloudfilter.net`). The carriers outsourced anti-spam
  to a single commercial vendor. Consumer-mail sources (Gmail, Yahoo,
  Outlook) are silently dropped at the Proofpoint layer in 2026.
- **US Cellular kept their own infrastructure** (`mx.uscc.net`) and is
  the least-filtered surviving gateway.
- **Google Fi** requires strict SPF/DKIM pass — hard target for spoofing.

The realistic abuse pattern in 2026 is **low-volume spear-phishing
against employees of companies whose owned domains lack DMARC
`p=reject`**, sent from a fully authenticated typosquat domain on a
non-residential IP, delivered **direct-to-MX** (not via consumer SMTP)
to a T-Mobile, Verizon, or US Cellular target. Spray and pray is dead —
Proofpoint reputation feeds, carrier RBLs, and CAN-SPAM enforcement
closed it.

---

## Authorized testing only

Run these PoCs against your own phone or a phone you have written
permission to test. Sending unsolicited SMS to anyone else's number is
illegal under TCPA and CAN-SPAM in the United States and similar statutes
elsewhere. This repo is a study aid, not a phishing kit.
