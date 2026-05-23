# Attack chain — email-to-SMS gateway smishing

How the vector fits in the broader smishing landscape, the MITRE ATT&CK
stages it covers, a concrete worked example, and detection points
available to defenders at each step.

Companion to:
- [`carrier_gateway_study.md`](carrier_gateway_study.md) — mechanism,
  inventory, spoof surface
- [`samples/recon_2026-05-23.md`](samples/recon_2026-05-23.md) — current
  empirical state of the gateways
- [`attack_vectors/`](attack_vectors/) — per-vector short writeups

---

## 1. Where this vector sits

The email-to-SMS gateway path is one entry point in a wider family of
mobile phishing techniques:

```
                          PHISHING TARGETING MOBILE
                          ─────────────────────────
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
        SMS-based                Voice-based           App-based
        (smishing)               (vishing)            (in-app)
              │
   ┌──────────┼───────────┐
   │          │           │
 Email-to-   Carrier-     iMessage /
 SMS         API SMS      RCS / OTT
 GATEWAY     (Twilio,     (requires
 (this)      Sinch,       Apple ID or
             Bandwidth)   Google account)
```

Why operators still pick this path in 2026 even though delivery rates
are worse than Twilio:

- **No KYC.** Twilio short-code campaigns now require The Campaign
  Registry vetting and $4000+ in 10DLC fees. Gateways have no equivalent.
- **No carrier account.** Twilio can shut you off on first abuse report.
  Gateway abuse reporting routes through carrier customer service or
  Whois abuse contacts — slow and rarely responsive.
- **Lookalike sender names.** Twilio surfaces a phone number. Gateways
  surface a string (`alerts`, `support`, `noreply`). The string is the
  social engineer's weapon — it lets the SMS impersonate a brand name
  rather than a phone number.
- **Anonymity.** Domain registration with privacy WHOIS plus a non-US
  VPS gives meaningfully more deniability than a Twilio account in your
  legal name.

The trade-off in 2026 is **delivery rate is low and decreasing** as
Proofpoint Cloudmark filters tighten — see
[`carrier_gateway_study.md`](carrier_gateway_study.md#7-why-the-vector-is-dying-and-where-it-isnt).

---

## 2. MITRE ATT&CK mapping

The full chain typically touches:

| Technique     | Name                                              | Stage           |
|---------------|---------------------------------------------------|-----------------|
| T1598         | Phishing for Information                          | Reconnaissance  |
| T1595         | Active Scanning (HLR/carrier lookup)              | Reconnaissance  |
| T1583.001     | Acquire Infrastructure: Domains (typosquat)       | Resource Dev    |
| T1583.004     | Acquire Infrastructure: Server (sending VPS)      | Resource Dev    |
| T1585.002     | Establish Accounts: Email Accounts                | Resource Dev    |
| T1660         | Phishing (mobile)                                 | Initial Access  |
| T1566.003     | Phishing: Spearphishing via Service               | Initial Access  |
| T1204.001     | User Execution: Malicious Link                    | Execution       |
| T1056.003     | Web Portal Capture (phish kit)                    | Credential Acc. |
| T1539         | Steal Web Session Cookie (real-time MFA relay)    | Credential Acc. |
| T1078.001     | Valid Accounts: Default Accounts (post-takeover)  | Persistence     |

ATT&CK Mobile sub-techniques:
- `T1660` — Phishing (mobile-specific)
- `T1456` — Drive-By Compromise (Mobile)

---

## 3. Kill chain — seven stages

Each stage with what an operator does, what it costs, and what
defenders can intervene on.

### Stage 1 — Reconnaissance

**Operator actions**
- HLR carrier lookup on target number (`tools/carrier_lookup.py`)
- OSINT on the target — employer, bank, recent online activity, name,
  geographic region. Builds the pretext anchor.
- Brand identification: their bank, their employer's IT, their package
  carrier, their employer's payroll provider.

**Output**: target carrier (→ gateway domain) + pretext brand

**Cost**: ~$0.005/lookup + free OSINT

**Defender visibility**: low. HLR lookups are provider-side, OSINT is
public records. No corp signal.

### Stage 2 — Resource development

**Operator actions**
- Register typosquat or lookalike domain (privacy WHOIS, low-attribution
  registrar)
- Provision VPS with rDNS control on a non-residential, non-blocklisted
  IP range
- Publish SPF (authorizing sender IP), DKIM (selector + private key),
  DMARC (`p=quarantine` typical — `p=reject` risks self-bouncing)
- Configure rDNS so the sending IP resolves to a hostname matching the
  HELO
- Install postfix or `swaks`; opendkim for signing
- Stand up phish kit on the domain (Evilginx2, Modlishka, GoPhish + custom)

**Cost**: ~$1-12 domain + $5/mo VPS + 2 hours one-time setup

**Defender visibility**: medium. Certificate Transparency logs catch
TLS issuance, passive DNS catches the new domain, brand-monitoring SOCs
flag lookalike registrations. This is the **earliest reliable detection
window** — hours to days before campaign launch.

### Stage 3 — Pretext crafting

**Operator actions**
- 160-character SMS body that fits in one segment (no fragmentation =
  better delivery)
- Subject line for MMS gateway path — surfaces above body on iPhone
- URL choice: shortener (`bit.ly`) raises Cloudmark flags; better to use
  a path on the owned typosquat (`brand-secure.com/v`)
- Pretext anchor: time-sensitive (account locked, 2FA needed, delivery
  failure) + plausible action (tap to verify)

**Cost**: zero, just time

**Defender visibility**: none

### Stage 4 — Delivery

**Operator actions**
- Direct-to-MX SMTP from sending VPS to carrier MX
- HELO with matching hostname, MAIL FROM with typosquat domain, RCPT TO
  with `<number>@<gateway>`
- See [`pocs/02_direct_to_mx.py`](pocs/02_direct_to_mx.py) for the
  envelope

**At the carrier gateway** (Proofpoint Cloudmark for T-Mobile / Verizon
in 2026):
- SPF check against sending IP
- DKIM signature verify
- DMARC alignment (`From:` domain vs SPF/DKIM result)
- Sending IP reputation (Cloudmark commercial feeds + Spamhaus +
  proprietary)
- Content signature match
- URL reputation against threat-intel feeds

Pass all → SMSC injection → SMS on handset.
Fail any → silent drop. No bounce, no notification.

**Defender visibility**: low. The carrier MTA logs everything, but
those logs are only available via legal process (subpoena to the carrier
or to Proofpoint).

### Stage 5 — Initial access (SMS arrival)

**On the handset**:
- Lands in iOS Messages app as native SMS / MMS
- Sender renders as From: local-part or display name (carrier-specific —
  see [`attack_vectors/02_sender_spoofing.md`](attack_vectors/02_sender_spoofing.md))
- No "from unknown app" warning, no email-origin indicator on iOS 16
  and below

**Target action**: read, decide whether to tap

**Defender visibility**: only via user report. The SMS itself doesn't
traverse any corp-controlled network.

### Stage 6 — Execution and credential capture

**Target taps link** → arrives at phish kit hosted on the typosquat
domain.

**Phish kit** (Evilginx2 is the 2026 standard):
- Real-time reverse proxy to the real brand login page
- Captures username + password as the user types them
- Captures MFA cookie when the user completes auth on the real backend
- The user's session is hijacked — operator gets the same `.AspNet.Cookies`
  or equivalent that the real backend issued

**Variants**:
- "Enter the SMS code we just sent you" — captures SMS OTP separately
- OAuth consent harvest — user grants attacker app access to their
  account without typing a password
- Drive-by mobile malware drop — declining post-iOS hardening, still
  works on outdated Android

**Defender visibility**:
- DNS lookups for the typosquat domain visible on corp networks
- IdP shows the real backend auth from an anomalous IP (the proxy)
- Browser SmartScreen / Safari Fraudulent Site Warning if the domain is
  already known-bad
- Post-auth: account activity from a new device / location

### Stage 7 — Account takeover and pivot

**Operator actions** within the MFA window (typically 5–15 minutes):
- Initiate wire transfer, add payee (banking targets)
- Set email forwarding rule, OAuth grant for persistence (email targets)
- Lateral movement via SSO into corporate apps (employer SSO targets)
- Drain wallet (crypto targets)
- Submit invoice payment redirect (B2B finance targets)

**Defender visibility**:
- IdP risk-based auth flags anomalous device/location
- Transaction monitoring at the bank for unusual payee additions
- Email rule auditing (rules forwarding to external domains)
- Behavioral analytics on logged-in sessions

This is the **why** of the smish. The SMS is the delivery vehicle, not
the goal.

---

## 4. Worked example (sanitized)

Target: an employee at a US enterprise, on a T-Mobile line, banks at
`examplebank.com`.

```
RECON
  $ python tools/carrier_lookup.py 5551234567 --backend twilio
    → carrier_name: T-Mobile USA, line_type: mobile, gateway: tmomail.net
  OSINT (LinkedIn, breach data, public records):
    → employer: example-corp.com, role: finance ops, likely customer of
      examplebank.com per old data-breach combolist match

RESOURCE
  Register: examplebank-secure.com  ($12, Porkbun, privacy WHOIS)
  VPS:      Hetzner cx22 EU         ($4/mo, clean /24, EU jurisdiction)
  DNS:      A    mail.examplebank-secure.com  → <vps-ip>
            MX   examplebank-secure.com       → mail.examplebank-secure.com
            TXT  v=spf1 ip4:<vps-ip> -all
            TXT  selector1._domainkey         → DKIM pubkey
            TXT  _dmarc                        → v=DMARC1; p=quarantine; rua=...
  rDNS:     PTR <vps-ip> → mail.examplebank-secure.com
  MTA:      postfix + opendkim signing with selector1
  Phish kit: Evilginx2 with examplebank phishlet on
             examplebank-secure.com/v/<token>

PRETEXT
  Subject: (empty, T-Mobile shows From: not Subject prominently)
  Body:    "Example Bank Alert: Sign-in from new device.
            If this wasn't you, verify now:
            https://examplebank-secure.com/v/9k3p"

DELIVERY (direct-to-MX, not via consumer SMTP)
  python pocs/02_direct_to_mx.py \
      --to 5551234567 --carrier tmobile \
      --from-addr alerts@examplebank-secure.com \
      --helo mail.examplebank-secure.com \
      --body "<above>"

RESULT IF IT LANDS
  iOS Messages: thread from "alerts@examplebank-secure.com"
  Target taps link → Evilginx2 proxy shows pixel-perfect login
  Captures:    username, password, MFA cookie
  Operator:    uses MFA cookie to log into real examplebank.com from
               the proxy IP (same IP that completed MFA), proceeds with
               wire transfer to a money mule

CAMPAIGN ENDS WHEN
  - User notices login alert email from real examplebank.com
  - Bank's fraud detection flags the unusual wire
  - Or operator extracts funds and abandons the infrastructure
```

Where it realistically fails:
- Cloudmark drops the SMTP delivery silently (typosquat domain on a
  fresh IP carries low reputation)
- iOS 17+ "Filter Unknown Senders" buries the SMS in the secondary
  inbox
- Target reads `alerts@examplebank-secure.com` and pauses on the
  hyphenated domain
- Bank's risk engine challenges with a phone-call MFA instead of SMS
- Phishing-resistant MFA (FIDO2 hardware token) breaks the whole chain
  at credential capture — **the only control that defeats this attack
  outright**

Success rate against a security-aware target: ~5–15%.
Success rate against a non-security-aware target: ~30–50% historically,
declining in 2026 with broader Cloudmark filtering and iOS 17+
unknown-sender handling.

---

## 5. Vector comparison

| Vector                                | Setup cost     | Setup time  | Attribution           | 2026 delivery rate |
|---------------------------------------|----------------|-------------|-----------------------|--------------------|
| **Email-to-SMS gateway (this repo)**  | $15 + $5/mo    | 2 hours     | Domain → operator     | Low                |
| Twilio / Sinch / Bandwidth A2P        | $1/mo + ~$0.008/SMS | 30 min, KYC | Strong (KYC linked) | High               |
| Carrier SMSC compromise / SS7 access  | Criminal infra | Days        | Hard                  | High               |
| iMessage spam (Apple ID burner)       | Free + Apple ID| 5 min       | Apple ID → operator   | High, rate-limited |
| Sideloaded Android SMS app + SIM      | $100+          | 1 hour      | Burner SIM only       | Medium, SIM-flagged|
| Compromised legitimate SMS aggregator | High           | Days        | Aggregator account    | High while it lasts|

---

## 6. Threat actor mapping

Public reporting (Microsoft, Mandiant, CrowdStrike, US Secret Service)
attributes the bulk of US email-to-SMS gateway smishing in 2024–2026
to:

- **Storm-0539 / "Atlas Lion"** — financially motivated, US retail gift
  card fraud. Uses gateway smishing heavily.
- **Octo Tempest (formerly Scattered Spider, UNC3944)** — financially
  motivated, hospitality and SaaS targeting. Mixed gateway + voice +
  in-person social engineering.
- **Various solo / low-skill operators** — primary user base
  2010–2020, mostly priced out by Cloudmark filtering and 10DLC
  enforcement.
- **Nation-state initial access brokers** — secondary use; prefer
  spear-phishing email over SMS gateways for higher reliability and
  better targeting metadata.

---

## 7. Detection points across the chain

Defender leverage by stage:

| Stage          | Defender artifact                                        | Control                                        |
|----------------|----------------------------------------------------------|------------------------------------------------|
| Recon          | None (provider logs not user-visible)                    | None at user side                              |
| Domain register | CT log, passive DNS, brand-monitoring feed              | Brand-monitoring SOC tooling                   |
| MTA standup    | SPF / DKIM DNS publication, fresh IP reputation         | Spamhaus / Talos reputation feeds              |
| Pretext        | None                                                     | None                                           |
| SMTP delivery  | Carrier MTA logs (legal process only)                    | Proofpoint Cloudmark (active defense at gateway)|
| SMS receipt    | User's handset, no SOC visibility                        | User training, MDM email-sender flagging       |
| Tap-through    | Corp DNS sinkhole, browser SmartScreen / Safari warning | DNS RPZ + browser warning lists                |
| Credential cap | Phish kit on attacker infra                              | Phishing-resistant MFA (FIDO2 hardware) — the only break in the chain |
| MFA relay      | IdP logs, anomalous device / location                   | Risk-based auth, conditional access            |
| Account access | Account activity, transaction logs                       | Behavioral detection, transaction risk scoring |

Defender priority order (highest leverage first):

1. **Phishing-resistant MFA (FIDO2 / hardware token).** The only
   control that breaks the chain. SMS OTP and TOTP both fall to
   Evilginx2-style real-time relay.
2. **DMARC `p=reject` on every owned domain**, including parked
   domains. Kills domain-aligned impersonation at the carrier MTA.
3. **Brand monitoring** for typosquat registrations. CT log feeds
   (`crt.sh` API, free) give you hours-to-days lead time before
   campaign launch.
4. **One-tap user reporting flow** (e.g. corporate "Report Phish"
   shortcut that forwards SMS metadata to SOC). Generates the forensic
   input needed for stage-3 detection going forward.
5. **DNS RPZ** sinkholing of known typosquat domains. Effective only on
   corporate-managed networks (off-network users on personal WiFi
   bypass).
6. **User training** on email-sourced SMS: "sender is a word, not a
   number" is the simplest tell.

---

## 8. Why this vector persists in 2026

Despite Proofpoint Cloudmark consolidation, AT&T retiring their gateway
entirely, and 10DLC enforcement closing off A2P abuse — the email-to-SMS
gateway path is still in active use. Reasons:

- **Setup cost remains low.** Two hours and $20 buys campaign
  infrastructure.
- **Anonymity is meaningfully better** than legitimate A2P APIs.
- **The remaining surviving gateways cover ~70% of US mobile lines**
  (T-Mobile + Verizon + their MVNOs).
- **The vector's downstream payload — MFA-relay phish kits — remains
  highly effective** against SMS OTP and TOTP MFA. The weakness is not
  the SMS, it's the auth factor on the other side.
- **Detection lag is high.** A campaign can run for 6-72 hours before
  brand monitoring + abuse reports + carrier-side reputation feedback
  catch up.

What would close the vector entirely:
- All US carriers retire their email-to-SMS gateways. AT&T set the
  precedent in 2026; T-Mobile and Verizon are likely to follow within
  3-5 years as Proofpoint's value vs maintenance cost crosses zero.
- Phishing-resistant MFA reaches consumer banking. Currently
  patchy — most US banks still default to SMS OTP.
- iOS / Android render email-sourced SMS with an unmissable visual
  marker. Apple has been tightening this in iOS 17–18.

Until then, the vector remains a low-cost / medium-skill entry to high-
value targets via SMS-OTP-bypass auth, and red teams should expect to
encounter it on engagements through at least the late 2020s.
