# Carrier email-to-SMS gateways — study guide

A walkthrough of how the bridges work, why they were attractive to red
teams for ~15 years, and what changed.

---

## 1. What the bridge is

Every major US mobile carrier ran (and several still run) a normal SMTP
mail server that accepts inbound email and converts each message into a
mobile-terminated SMS to a subscriber on its network. The destination
address has the form:

```
<10-digit-MSISDN>@<carrier-gateway-domain>
```

The gateway domain is just a DNS-resolvable host with an MX record.
As of May 2026 the surviving major carrier gateways are all fronted by
Proofpoint's Cloudmark service:

```
$ dig +short MX tmomail.net
10 tmo-east.mx.a.cloudfilter.net.
10 tmo-west.mx.a.cloudfilter.net.

$ dig +short MX vtext.com
0  vrz-sms.mx.a.cloudfilter.net.
10 smtpin01.vzw.a.cloudfilter.net.
10 smtpin02.vzw.a.cloudfilter.net.

$ dig +short MX vzwpix.com
0  vrz-mms.mx.a.cloudfilter.net.
10 smtpin01-mms.vzw.a.cloudfilter.net.
10 smtpin02-mms.vzw.a.cloudfilter.net.
```

`cloudfilter.net` is operated by Proofpoint (SOA → `ns1.proofpoint.com`).
This is post-2017 Proofpoint-acquired Cloudmark commercial filtering.
The inbound MTA the sender sees is **Proofpoint, not the carrier**. Mail
passing Proofpoint's checks is then handed to the carrier SMSC. Mail
failing checks is silently dropped — no 5xx, no bounce.

A message sent to `2155551234@tmomail.net` is accepted by Proofpoint's
MTA, evaluated against Cloudmark's reputation and content rules, then
either forwarded to T-Mobile's SMSC or silently dropped. If forwarded,
T-Mobile strips MIME, truncates to SMS limits (~160 chars per segment),
maps the local-part of the recipient to the subscriber's MSISDN, and
injects into the SMSC the same way any mobile-originated SMS would be.

The handset has no signal that the message originated from email. It
looks like a normal SMS in the native Messages app.

The bridges were designed in the late 1990s for paging — sysadmins
wanting "server down" alerts on their Motorola flip phones. The
authentication model was "trust the public internet to be small enough
that abuse will not scale." That assumption did not survive.

---

## 2. Gateway inventory (2026 status)

This section was rewritten 2026-05-23 against empirical DNS recon — see
[`samples/recon_2026-05-23.md`](samples/recon_2026-05-23.md) for the raw
evidence. Earlier drafts of this study mirrored secondary sources that
turned out to be stale.

| Carrier        | SMS gateway              | MMS gateway              | Status (May 2026) |
|----------------|--------------------------|--------------------------|-------------------|
| AT&T           | `@txt.att.net` (dead)    | `@mms.att.net` (dead)    | **Retired.** Zones exist, zero MX records. |
| T-Mobile       | `@tmomail.net`           | `@tmomail.net`           | Alive, behind Proofpoint Cloudmark filter |
| Verizon        | `@vtext.com`             | `@vzwpix.com`            | Alive, behind Proofpoint Cloudmark filter |
| US Cellular    | `@email.uscc.net`        | `@mms.uscc.net`          | Alive, own infrastructure |
| Google Fi      | `@msg.fi.google.com`     | (same)                   | Alive, Google MX, strict SPF/DKIM |
| Cricket        | `@sms.cricketwireless.net` (dead) | `@mms.cricketwireless.net` (dead) | **Retired.** Now a CNAME to Akamai web edge |
| Boost / Metro  | `@tmomail.net`           | (same)                   | T-Mobile MVNO |
| Mint Mobile    | `@tmomail.net`           | (same)                   | T-Mobile MVNO |
| Spectrum Mobile| `@vtext.com`             | `@vzwpix.com`            | Verizon MVNO |
| Xfinity Mobile | `@vtext.com`             | `@vzwpix.com`            | Verizon MVNO |
| Sprint         | (none)                   | (none)                   | Dead since T-Mobile merger |

The 2026 picture is a consolidation story, not the simple "Verizon killed
their gateway" narrative that circulated in 2022.

- **AT&T and Cricket retired their gateways entirely.** Both zones still
  resolve to SOA but publish zero MX records. AT&T explicitly removed
  the mail records; Cricket re-pointed the hostname to an Akamai web
  redirect.
- **T-Mobile and Verizon outsourced anti-spam to Proofpoint Cloudmark.**
  Three of the remaining major gateways — `tmomail.net`, `vtext.com`,
  and `vzwpix.com` — all resolve to MX hosts under
  `*.cloudfilter.net`, which is operated by Proofpoint (whose Cloudmark
  acquisition closed in 2017). Carriers no longer run the front-end
  themselves; they pay Proofpoint to filter.
- **Verizon's `vtext.com` was not killed.** The widely-cited 2022
  "Verizon shut down vtext.com" claim turns out to be inaccurate. The
  zone still publishes MX. What was killed was permissive accept-and-
  deliver behavior — anything that doesn't pass Proofpoint's checks is
  silently dropped, which from the sender's perspective looks
  indistinguishable from a dead gateway.
- **US Cellular is the outlier.** Their `email.uscc.net` and
  `mms.uscc.net` are still hosted on their own `mx.uscc.net`
  infrastructure, not Proofpoint. Filtering posture is less
  characterized in public sources.

---

## 3. Recon — find the carrier

You cannot send blind. The gateway domain depends on the target carrier,
and post-LNP (Local Number Portability) the area code no longer tells
you the carrier reliably.

Ordered by tradecraft, not cost:

1. **HLR / Carrier lookup APIs.** Twilio Lookup, NumVerify, HLR Lookup,
   IPQualityScore. Returns current carrier, MNP status, line type
   (mobile vs landline vs VoIP). $0.005–$0.01 per query. Cleanest signal.
   Tool: `tools/carrier_lookup.py`.

2. **OSINT.** Email signatures, Calendly auto-replies, conference talk
   slides, podcast guest bios occasionally leak the device or carrier.
   LinkedIn rarely. Free, very low-signal.

3. **Multi-gateway fan-out.** Send the same message to every known
   gateway. Only one will deliver, the rest bounce or silently drop. Wide
   email trail, easy to attribute. PoC: `pocs/03_carrier_fanout.py`.

4. **Number-portability databases (NPAC, LERG).** The original carrier
   for an area-code/exchange. Wrong if the number has been ported, which
   is common. Subscription paywall.

5. **Pretexted call.** Ring the number from a burner, listen for
   carrier-branded voicemail greetings ("Welcome to T-Mobile voicemail").
   Effective but loud — the target has the call record.

---

## 4. The spoof surface

This is the part that made the vector worth using.

When the gateway MTA receives an email, it converts it to an SMS. The
sender field on the handset is **derived from the email headers**, not
from a real MSISDN. Each carrier has its own rule.

Historical and current rendering:

| Carrier                  | Sender shown on handset                              |
|--------------------------|------------------------------------------------------|
| AT&T (historical, gateway retired in 2026) | Display name + local-part of `From:`, e.g. `support` from `support@bankofamerica.com`. Was the canonical operator target until the gateway was retired. |
| T-Mobile (`tmomail.net`) | Full `From:` address, lightly truncated. Behind Proofpoint Cloudmark filtering. Hard to spoof an identity outright, easier to make look like an alert. |
| Verizon (`vtext.com`, `vzwpix.com`) | Email sender shown above body on MMS. Proofpoint Cloudmark filters aggressively — consumer-mail sources silently dropped. |
| Google Fi                | Full `From:` address. SPF/DKIM pass required. |
| US Cellular              | Local-part only. Less-filtered survivor (own infrastructure, not Proofpoint). Likely the cleanest 2026 target for authorized testing on a target whose carrier you control. |

The classic phishing flow on AT&T used to be:

1. Register a typosquat: `bank0famerica.com` or `secure-chase.net`.
2. Stand up an SMTP server with SPF/DKIM/DMARC published for that domain.
3. Send `From: alerts@bank0famerica.com` to the target's
   `@txt.att.net` address.
4. Target's iPhone shows an SMS from "alerts", body
   "Your account has been locked. Tap to verify: <short-url>".

That flow is dead. AT&T's gateway is gone. The equivalent flow against
Proofpoint-filtered carriers (T-Mobile, Verizon) in 2026 looks like:

1. Register a typosquat with **complete DNS authentication**: SPF,
   DKIM with a published selector, DMARC `p=quarantine` or `p=reject`.
2. Send from a **non-residential IP with clean rDNS** matching your
   HELO hostname. Cloudmark's reputation feeds blackhole residential
   ranges and brand-new VPS IPs aggressively.
3. **Direct-to-MX**, not via consumer SMTP. Gmail, Yahoo, Outlook
   consumer accounts cannot deliver to the Proofpoint-fronted gateways
   — empirically confirmed 2026-05-23 against `vzwpix.com`. Cloudmark's
   policy treats consumer-mail sources as untrusted and drops silently.
4. The handset rendering remains attractive: short sender, no
   "unknown number" warning, slots into Messages alongside legitimate
   SMS.

Why iPhone in particular? iOS renders SMS from email more compactly than
Android — fewer "this came from a non-mobile sender" hints. iOS 17+
added stricter unknown-sender filtering that helps, but iOS 16 and below
still hide most of the email-origin tells.

---

## 5. Three operator paths

### 5a. Authenticated SMTP (easy, traceable)

Send through a normal SMTP provider you already own — Gmail, Outlook,
SES, Mailgun. Authentication identifies you to the provider, who will
log every send and respond to subpoenas. The provider's outbound DMARC
check will also reject blatant identity spoofs.

Real-world use: red-team exercises where attribution is acceptable. Not
operational tradecraft. See `pocs/01_basic_gateway_send.py`.

### 5b. Direct-to-MX (medium, requires owned mail infra)

Skip authenticated SMTP. Resolve the carrier gateway MX, open port 25,
send your message with your own `HELO`, `MAIL FROM`, `RCPT TO`. The
gateway MTA evaluates SPF/DKIM against the `From:` domain you claim. If
you own that domain (typosquat) and have published correct DNS, you
pass.

Requires:

- Owned VPS with clean rDNS and a low-reputation-risk IP.
- Owned domain with SPF, DKIM, DMARC matching the From:.
- No mail provider in the path that might re-sign or rewrite.

See `pocs/02_direct_to_mx.py`.

### 5c. Open relay / compromised MTA (rare, opportunistic)

Find an open relay or a mail server whose SPF includes wildcards or
shared IP space (Office 365 tenants, old corporate Exchange clusters).
Send through it. The relay's authenticated reputation passes for you.

Increasingly rare in 2026 — open relays are blackholed within hours, and
M365 tenant-share abuse is the focus of Microsoft's anti-spam team. Not
documented in this repo beyond noting that it existed.

---

## 6. Defender view

What the blue team can actually observe:

- **On the corporate network**: nothing. The SMS rides from carrier MTA
  to carrier SMSC to handset, never traversing the enterprise.
- **On the user's iPhone**: the message is an SMS. The only tells are
  - Sender displays as a name or short word, not a 10-digit number or
    5-digit short code.
  - "Filter Unknown Senders" lands it in the secondary inbox if the
    sender is not in contacts.
  - On iOS 17+, a small "from email" hint appears in some renderings.
- **On the user's email**: the original SMTP message stays in nobody's
  inbox — the gateway accepts and forwards, no copy is mailed back. The
  defender's only forensic artifact is at the carrier MTA, available
  only via legal process (subpoena to the carrier).
- **If the attacker used a typosquat domain**: the defender can find the
  registration via Whois, certificate transparency logs (CT search for
  the lookalike string), and passive DNS. This is usually how
  attribution happens — not the gateway path, the domain.

Detection patterns useful when ingesting employee-reported phish:

- Sender displays as a word, not a number.
- Message body contains classic phish lures (account locked, payment
  required, click here) with a shortened URL or a long subdomain.
- Reply attempts go to a non-mobile address (some carriers preserve the
  reply-to as the original email, others reject the reply).
- Headers, if the user can capture them, show carrier gateway MTA in the
  Received chain.

See `pocs/99_detect_gateway_msg.py` for a defender-side scanner that
parses .eml / mbox dumps and flags gateway-relayed messages.

---

## 7. Why the vector is dying — and where it isn't

The "dying" framing is more nuanced than the 2022 narrative suggested.
Updated 2026-05-23 against empirical recon.

What actually happened:

- **AT&T retired the gateway entirely** sometime between 2024 and 2026.
  `txt.att.net` and `mms.att.net` zones exist but publish zero MX
  records. No mail accepted at all.
- **Cricket followed AT&T**. `sms.cricketwireless.net` is now a CNAME
  to an Akamai web edge — the hostname redirects to a support page.
- **Verizon did not kill `vtext.com`** despite the widely cited 2022
  reports. The zone still publishes MX. What Verizon did was outsource
  the inbound filtering to Proofpoint's Cloudmark service. The bridge
  persists for authenticated business senders; consumer-source mail is
  silently dropped, which from the sender's perspective is
  indistinguishable from a dead gateway.
- **T-Mobile sits on the same Proofpoint Cloudmark infrastructure.**
  All three of the major surviving carrier gateways
  (`tmomail.net`, `vtext.com`, `vzwpix.com`) now resolve under
  `*.cloudfilter.net`.
- **US Cellular kept their own infrastructure** and remains the least
  filtered survivor.
- **Google Fi** never tolerated unauthenticated senders to begin with.
- **RCS Business Messaging** and **Twilio / Sinch / Bandwidth** A2P APIs
  are the legitimate replacement for the paging use case, with KYC and
  number assignment. Carriers push business customers toward them.
- **CAN-SPAM and TCPA enforcement** expanded to cover SMS with
  per-message statutory damages ($500–$1,500). The economics now favor
  spear-phishing over volume.

What this means for red teams in 2026:

- **The vector is not "dead". It has been consolidated** behind
  Proofpoint Cloudmark on T-Mobile and Verizon, and behind US Cellular's
  own MTAs. The shape of a working delivery has changed.
- **Consumer-mail sources cannot deliver** to T-Mobile or Verizon
  gateways. Gmail, Yahoo, Outlook accounts are silently dropped at the
  Cloudmark layer. This is the empirical finding from the
  2026-05-23 recon (`samples/recon_2026-05-23.md`).
- **What still works**: a domain-aligned authenticated sender
  (registered typosquat with full SPF / DKIM / DMARC) on a
  non-residential IP with clean rDNS, delivering direct-to-MX. That
  setup costs ~$15–30/mo in domain + VPS and still gets past Cloudmark
  for low-volume sends.
- **What works easiest**: US Cellular subscribers, because the gateway
  is on the carrier's own infrastructure with lighter filtering than
  Proofpoint's commercial offering.
- For pentests, the value remains mostly in **demonstrating the spoofing
  surface and recommending defensive controls** (DMARC `p=reject` on
  owned and parked domains, end-user training on "sender is a word not
  a number", MDM that flags email-sourced SMS, brand monitoring for
  typosquat registrations).

---

## 8. Recommended defensive controls

For an organization wanting to harden against this:

1. **DMARC `p=reject`** on every owned domain, including parked ones.
   Kills domain-aligned typosquat sender spoofing at the gateway MTA.
2. **Register lookalike domains preemptively** or monitor CT logs for
   them.
3. **End-user training** on email-sourced SMS: the "sender is a word,
   not a number" tell.
4. **MDM / EMM** policies that prefer or enforce **iMessage / RCS** for
   inter-employee contact, where the sender is a verified identity.
5. **Phishing simulation** that includes carrier-gateway delivery as a
   vector, not just classic email.

For an individual:

1. Turn on **Filter Unknown Senders** (iOS Settings → Messages).
2. Add your bank, employer, and frequent senders to Contacts so the
   "unknown" filter actually triggers on suspicious senders.
3. Treat any SMS where the sender is a name not a number as untrusted
   until verified out-of-band.

---

## Study questions

1. Why did the bridges exist in the first place? What was the original
   threat model and where did it break?
2. Why did Verizon choose to kill `vtext.com` rather than tighten filters
   like AT&T did?
3. If a target has a ported number (formerly Verizon, now T-Mobile),
   which gateway domain works? Why?
4. SPF passes on a typosquat domain — does that guarantee delivery
   through the gateway? What about DKIM? DMARC?
5. The defender finds an employee phish report with sender "support" and
   body containing a shortened URL. The user cannot recover headers.
   What forensic actions are still available?
6. What is the realistic blast radius of this vector in 2027? Project
   forward from current trends.
