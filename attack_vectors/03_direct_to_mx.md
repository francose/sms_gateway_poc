# 03 — Direct-to-MX delivery

## What

Skip authenticated SMTP. Resolve the carrier gateway's MX record and
talk port 25 directly from your own mail server. The gateway evaluates
authentication against the domain you claim in `MAIL FROM` and `From:`.
If you own that domain and have published correct DNS, you pass.

## Why operators do this

Authenticated SMTP through a provider (Gmail, SES, Mailgun) carries two
liabilities:

1. **Outbound DMARC enforcement.** The provider rejects mail where the
   From: domain isn't yours.
2. **Provider logs.** Every send is attributable. Subpoena-friendly.

Direct-to-MX removes both. The trade-off is that you carry the
operational burden — deliverability is your problem.

## Requirements

- **Owned VPS** with a static IPv4 and **clean rDNS** matching the
  HELO/EHLO hostname.
- **Owned domain** with published SPF (`v=spf1 ip4:<your-ip> -all`),
  DKIM signing on outbound, DMARC `p=quarantine` or `p=reject` to match
  what high-reputation senders look like.
- **No upstream provider in the path** that might re-sign, rewrite, or
  blackhole.

## The session

```
$ telnet alnpop41.snet.gateway.2wire.com 25
220 mxs1.eb.att-mail.com ESMTP
EHLO mail.yourdomain.tld
250-mxs1.eb.att-mail.com ESMTP at your service
MAIL FROM:<alerts@yourdomain.tld>
250 2.1.0 Sender ok
RCPT TO:<2155551234@txt.att.net>
250 2.1.5 Recipient ok
DATA
354 End data with <CR><LF>.<CR><LF>
From: alerts@yourdomain.tld
To: 2155551234@txt.att.net
Subject:

direct-to-MX POC
.
250 2.0.0 Message accepted for delivery
QUIT
```

## Failure modes

- **rDNS mismatch** → 421 reject at HELO.
- **No SPF / soft SPF** → 550 reject at MAIL FROM on stricter gateways.
- **DKIM signature fails or absent** → some gateways reject, most send to
  spam treatment which the user never sees on the handset (delivery
  silently dropped).
- **Source IP on Spamhaus / Spamcop** → instant 550. New VPS IPs are
  often pre-listed in shared blocklists; warm-up matters.
- **High send rate from new IP** → rate-limited or null-routed without
  notice.

## Detection

Defender side: nothing visible until the user reports the SMS. If the
user can recover headers from a forwarded version, the `Received:` chain
shows the sending VPS IP — useful for attribution.

## Mitigation

Operator side: this is the "professional" delivery path. Worth setting
up only for active engagements, not for one-shot tests.

Defender side: this stage cannot be blocked from the target side — the
attacker is talking to the carrier's infrastructure, not yours. Defense
is at the domain-authentication layer (DMARC on owned domains, brand
monitoring for lookalikes) and the user-awareness layer.
