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

Updated 2026-05-23 against empirical DNS recon — see
[`samples/recon_2026-05-23.md`](../samples/recon_2026-05-23.md) for raw
DoH evidence.

| Live (and how) | Dead / removed |
|----------------|----------------|
| `tmomail.net` — fronted by Proofpoint Cloudmark (`tmo-{east,west}.mx.a.cloudfilter.net`) | `txt.att.net` (zone exists, zero MX) |
| `vtext.com` — Proofpoint Cloudmark (`vrz-sms.mx.a.cloudfilter.net`); NOT killed in 2022 as widely reported | `mms.att.net` (zone exists, zero MX) |
| `vzwpix.com` — Proofpoint Cloudmark (`vrz-mms.mx.a.cloudfilter.net`) | `sms.cricketwireless.net` (CNAME to Akamai web edge) |
| `email.uscc.net`, `mms.uscc.net` — US Cellular own infra (`av*/sc*.mx.uscc.net`), not Proofpoint | `messaging.sprintpcs.com` (Sprint, dead post-T-Mobile merger) |
| `msg.fi.google.com` — Google MX (`gmr-smtp-in.l.google.com`) | `messaging.nextel.com` (Nextel, dead) |

Three big things changed from the 2022 narrative:

1. **AT&T and Cricket retired entirely.** Earlier drafts of this study
   treated AT&T's `txt.att.net` as the canonical operator target. That
   is wrong as of 2026 — both `txt.att.net` and `mms.att.net` publish
   SOA but zero MX records. AT&T explicitly removed the mail records.
   Cricket re-pointed their hostname to an Akamai edge redirect.

2. **Verizon's `vtext.com` did not actually die.** The "Verizon killed
   vtext in 2022" claim is everywhere in third-party documentation, but
   the zone still publishes live MX records to Proofpoint's Cloudmark.
   What was killed was permissive delivery, not the bridge.

3. **The big three surviving gateways all use Proofpoint.** T-Mobile,
   Verizon SMS, and Verizon MMS resolve to `*.cloudfilter.net`, which
   is operated by Proofpoint (SOA → `ns1.proofpoint.com`). The carriers
   no longer run their own anti-spam front-ends.

## Mitigation

Operator side: keep your gateway list refreshed against MX recon, not
secondary sources. Several widely-cited writeups still list
`txt.att.net` as the canonical target; sending there in 2026 is silent
failure since the MX is gone. Build the gateway directory from `dig MX`
or DoH lookups against `1.1.1.1`, not from blog posts.

Defender side: this stage is silent — no observable signal until the
operator sends real traffic. The one defender-visible indicator at recon
stage is brand monitoring: typosquat domain registrations precede a
campaign by hours to days, visible in CT logs and passive DNS.
