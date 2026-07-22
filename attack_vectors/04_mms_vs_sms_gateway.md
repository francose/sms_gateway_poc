# 04 — MMS gateway vs SMS gateway

## What

Carriers operate two parallel bridges. The SMS gateway (`@vtext.com`,
`@txt.att.net` historically) accepts short text only. The MMS gateway
(`@vzwpix.com`, `@mms.att.net` historically) accepts longer text, subject
lines, and binary attachments — images, audio, sometimes PDFs.

## Why operators care about the difference

| Property                      | SMS gateway              | MMS gateway              |
|-------------------------------|--------------------------|--------------------------|
| Body length                   | 160 char hard cap        | 1600+ characters typical |
| Subject line behavior         | Often discarded          | Often surfaced to user   |
| Attachments                   | Dropped                  | Delivered as MMS payload |
| Filtering                     | Stricter                 | Looser historically       |
| 2026 status                   | `vtext.com` alive (Proofpoint) | `vzwpix.com` alive (Proofpoint) |

Contrary to the widely-repeated "Verizon killed the SMS gateway in 2022"
claim, `vtext.com` is still live in 2026, behind Proofpoint Cloudmark — see
[`carrier_gateway_study.md`](../carrier_gateway_study.md#7-why-the-vector-is-dying-and-where-it-isnt).
Both Verizon bridges survive, so the SMS-vs-MMS choice is about
**capability, not survival**: reach for `vzwpix.com` when you want a subject
line, an image, or more than 160 characters.

## Attack-relevant difference: subject line

On AT&T's MMS gateway, the `Subject:` header is shown above the body on
some handsets. This gives the operator a second piece of attacker-
controlled rendering, often used to construct a fake "from" pretext:

```
From: noreply@bank.example
Subject: Bank of America

Your card ending 4521 was used for $387.22 at...
```

The user sees "Bank of America" as the message subject and the body
beneath. The actual sender field is irrelevant if the subject
masquerades as the sender identity.

## Attachment vector

The MMS gateway accepts image attachments. Attached PNGs render inline
on most handsets. Common abuse pattern:

1. Generate a fake "bank alert" image with logos, QR code linking to
   phish kit.
2. Send via `<target>@vzwpix.com` or `@mms.att.net`.
3. User sees an apparent bank notification with embedded QR. iOS Camera
   scans QR, opens browser. Phish kit collects credentials.

This bypasses URL-scanning filters because the URL is inside a PNG, not
in the message text. iOS does not OCR/scan QR codes for safety.

## Detection

Defender side: MMS PCAP at the carrier shows the attachment. End-user
reports are higher-quality on MMS than SMS because the handset surfaces
more metadata (attachment filename, MIME type, sender email if from
gateway).

## Mitigation

Operator side: prefer MMS gateway over SMS gateway for any payload that
benefits from a subject line, image, or extra body length. The
downside: MMS bounces are noisier (the recipient's MMS retrieval may
fail silently if their data is off).

Defender side: user training on QR code skepticism. MDM that flags
MMS-with-image from unknown senders. Apple has been adding QR
verification surfaces in iOS 18+ — adoption is the question.
