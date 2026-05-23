# 05 — Defender artifacts of a gateway-relayed SMS

## What

What forensic surface is available to a defender investigating a
user-reported phish that arrived via a carrier email-to-SMS gateway.

## On the wire

Nothing. The SMS rides from the carrier MTA to the carrier SMSC to the
handset. No corporate network, no proxy, no SWG sees the traffic. Even
on a fully managed device with MDM, SMS metadata is not exfiltrated to
the EMM in most deployments.

## On the handset

Limited but useful:

- **Sender field**: a word or local-part, not a 10-digit MSISDN and not
  a 5-digit short code. This is the strongest single tell.
- **Sender groups in iOS Messages**: gateway-sourced SMS appears in a
  new thread, not in an existing thread with that contact. If the user
  has a real contact for "Bank of America" stored as an MSISDN, the
  spoof goes to a separate thread.
- **iOS 17+ "from email" hint**: a small text fragment under the sender
  on some renderings. Easily missed.
- **Long-press → Show Details** in Messages exposes the sender as an
  email-looking address rather than a phone number. Forensically useful
  if the user reports.

## On the email side

The carrier MTA accepts and forwards. No copy persists on email servers
the defender can reach. The only retained record is:

- **At the carrier**: their inbound MTA logs the SMTP session — source
  IP, From: domain, time, RCPT TO:, message-id. Available only via
  legal process.
- **At any upstream relay**: if the attacker sent through an
  intermediate provider (Gmail, SES, Mailgun), that provider has logs.
  Again, legal process only.

## Domain side (the real attribution path)

The typosquat or owned domain is where investigations actually move:

- **Whois**: usually privacy-protected but historical records survive
  via DomainTools, RiskIQ, archive.org of Whois lookups.
- **Certificate Transparency**: search `crt.sh` for the lookalike
  string. Cert issuance timestamps narrow the operator window.
- **Passive DNS**: PassiveTotal, Farsight DNSDB, SecurityTrails. Maps
  the domain to A/AAAA records over time, links to other domains on the
  same IP.
- **SPF/DKIM records**: the operator's published DNS leaks their
  sending infrastructure. SPF `include:` chains and DKIM selector
  hostnames often reveal the SMTP provider or VPS host.

## Header recovery

If the user reports a gateway-relayed SMS, ask them to:

1. Long-press the message → More → Forward → enter your reporting
   address.
2. The forwarded MMS includes the original `From:` header as part of
   the carrier's gateway envelope. SMS forwards lose almost all
   metadata, MMS forwards preserve more.
3. On Android, third-party SMS apps with backup export preserve full
   headers in some cases.

Most users won't do this. The realistic input is "the sender said
'support' and the body said 'click here'." Defender works backward from
the URL.

## Detection rules

Useful patterns for ingesting reported phish into a SOC pipeline:

- `From:` local-part is a generic word (`alerts`, `support`, `noreply`,
  `it-helpdesk`) and the From: domain is a registered-in-last-30-days
  domain.
- The Received: chain (when recoverable) shows
  `*.att-mail.com`, `*.t-mobile.com`, `*.tmomail.net`,
  `vzwpix-mail.verizon.net`, or `*.uscellular.net` as the last hop
  before the user.
- Subject is blank or short and the body contains URL-shortener
  patterns or punycode in URLs.
- Body references a service the user does business with, with first-
  name personalization scraped from LinkedIn or breach data.

`pocs/99_detect_gateway_msg.py` implements a scanner that walks a
directory of `.eml` files (or a single mbox) and flags messages
matching these patterns.

## What the carrier can do

Carrier-side defenses available to the gateway operator:

- DMARC enforcement on inbound to the gateway. (AT&T, Google Fi do.)
- Rate limiting per source IP, per From: domain, per RCPT TO: domain.
- Reputation feeds (Spamhaus, Spamcop, Talos) consulted at HELO time.
- Killing the bridge entirely. (Verizon 2022.)

There's no public API for end users or defenders to report gateway
abuse directly. Reports route through carrier customer service or
through abuse contacts on the gateway domain's Whois — generally slow
and unresponsive.
