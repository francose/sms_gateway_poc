# 02 — Sender spoofing via the From: header

## What

The carrier MTA derives the SMS sender field on the recipient handset
from the email `From:` header, not from a real MSISDN. The exact
rendering rule differs per carrier. This is the spoof surface.

## Carrier rendering rules

| Carrier        | What the handset shows                                   | Spoof difficulty |
|----------------|----------------------------------------------------------|------------------|
| AT&T (retired 2026) | Display name + local-part of From:, e.g. `support` (historical) | Was easy on a DMARC-aligned owned domain; gateway now dead |
| T-Mobile       | Full From: address, truncated                            | Hard to impersonate identity, easy to make look like an alert |
| Google Fi      | Full From: address                                       | Very hard, strict SPF/DKIM |
| US Cellular    | Local-part only                                          | Easy, weak filtering |

## The classic flow (AT&T, historical — gateway retired 2026)

1. Register a typosquat domain: `bank0famerica.com`, `secure-chase.net`,
   `it-helpdesk.<companyname>.co`.
2. Publish SPF, DKIM, DMARC for it from your sending IP.
3. Send `From: alerts@bank0famerica.com` to `<target>@txt.att.net`.
4. Target's iPhone shows an SMS with sender "alerts" and the lure body.

## Why it works on iOS

iOS renders SMS-from-email in a way that hides most of the email-origin
tells. The sender field reads as a plain word, identical to how a
business-class A2P short-name sender renders. The user cannot
distinguish without inspecting the message metadata, which iOS does not
expose in the default Messages UI.

## DMARC's effect

In 2026 the carrier gateways check inbound SPF and DKIM. Many also
evaluate DMARC alignment. If the From: domain publishes DMARC
`p=reject`, the gateway will reject impersonation attempts from
unauthorized senders. This is why typosquat domains (which the attacker
owns and can publish correct DNS for) are still the dominant path —
the spoof is the *name*, not the domain authentication.

## Detection

Defender side:

- `From:` header in any retained mail logs at the carrier or at upstream
  hops shows the typosquat domain.
- CT logs catch the lookalike-domain registration if certs are issued.
- Passive DNS shows the domain pointing at a fresh VPS.
- Brand monitoring services (PhishLabs, ZeroFox, IronTraq) flag the
  lookalike during routine sweeps.

## Mitigation

Operator side: don't use a `gmail.com` From: address — gmail's outbound
DMARC and the carrier's inbound check will both block. Use your own
domain.

Defender side: register predictable lookalikes preemptively. Enforce
DMARC `p=reject` on every owned domain including parked ones.
