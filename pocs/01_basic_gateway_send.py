#!/usr/bin/env python3
"""
01 — Basic auth-SMTP send through a carrier email-to-SMS gateway.

The simplest possible delivery path. You authenticate to your own
SMTP provider (Gmail with an App Password is the standard test rig),
the provider relays to the carrier gateway, the gateway pushes an SMS
to your handset.

Use against your own phone. See README for the legal disclaimer.

Setup once:
    1. Create a Gmail App Password (Google account → Security → App passwords).
    2. export SMTP_USER="you@gmail.com"
       export SMTP_APP_PW="xxxx xxxx xxxx xxxx"

Run:
    python pocs/01_basic_gateway_send.py \\
        --to 2155551234 --carrier tmobile --body "POC inbound"

    # With a different SMTP provider:
    python pocs/01_basic_gateway_send.py \\
        --to 2155551234 --carrier att \\
        --smtp-host smtp.fastmail.com --smtp-port 587 \\
        --body "from fastmail"
"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from email.message import EmailMessage

# Make sibling tools importable without packaging.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gateway_domains  # noqa: E402


def build_message(
    *, from_addr: str, from_name: str, to_addr: str, subject: str, body: str,
) -> EmailMessage:
    msg = EmailMessage()
    if from_name:
        msg["From"] = f"{from_name} <{from_addr}>"
    else:
        msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject  # empty subject avoids prefixing the SMS body on some gateways
    msg.set_content(body)
    return msg


def send(
    *, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
    msg: EmailMessage, starttls: bool = True, verbose: bool = False,
) -> None:
    smtplib_class = smtplib.SMTP if starttls else smtplib.SMTP_SSL
    with smtplib_class(smtp_host, smtp_port) as s:
        if verbose:
            s.set_debuglevel(1)
        s.ehlo()
        if starttls:
            s.starttls()
            s.ehlo()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Send an SMS via a carrier email-to-SMS gateway.")
    p.add_argument("--to", required=True,
                   help="Recipient 10-digit US number, digits only")
    p.add_argument("--carrier", required=True,
                   help=f"Carrier key. One of: "
                        f"{', '.join(g.carrier for g in gateway_domains.GATEWAYS)}")
    p.add_argument("--body", required=True, help="SMS body (will be truncated to ~160 chars)")
    p.add_argument("--subject", default="", help="Empty by default to avoid body prefix")
    p.add_argument("--from-name", default="", help="Display name shown next to From: address")
    p.add_argument("--mms", action="store_true",
                   help="Use the carrier's MMS gateway (longer body, attachments survive)")
    p.add_argument("--smtp-host", default="smtp.gmail.com")
    p.add_argument("--smtp-port", default=587, type=int)
    p.add_argument("--smtp-ssl", action="store_true",
                   help="Use implicit SSL (port 465) instead of STARTTLS")
    p.add_argument("--smtp-user", default=os.environ.get("SMTP_USER"),
                   help="Defaults to $SMTP_USER")
    p.add_argument("--smtp-pass", default=os.environ.get("SMTP_APP_PW"),
                   help="Defaults to $SMTP_APP_PW")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the envelope and body, do not send")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    gw = gateway_domains.by_carrier(args.carrier)
    if not gw:
        print(f"unknown carrier: {args.carrier}", file=sys.stderr)
        return 2

    domain = gw.mms_domain if args.mms else gw.sms_domain
    if not domain:
        print(f"carrier {args.carrier!r} has no "
              f"{'mms' if args.mms else 'sms'} gateway "
              f"(status: {gw.status})", file=sys.stderr)
        return 3

    to_addr = f"{args.to}@{domain}"

    if not (args.smtp_user and args.smtp_pass) and not args.dry_run:
        print("SMTP_USER and SMTP_APP_PW must be set (or --smtp-user / --smtp-pass)",
              file=sys.stderr)
        return 4

    from_addr = args.smtp_user or "noreply@example.invalid"
    msg = build_message(
        from_addr=from_addr,
        from_name=args.from_name,
        to_addr=to_addr,
        subject=args.subject,
        body=args.body,
    )

    print(f"[envelope] from: {msg['From']}")
    print(f"[envelope] to:   {msg['To']}")
    print(f"[envelope] subj: {msg['Subject']!r}")
    print(f"[gateway]  carrier={gw.carrier} "
          f"channel={'mms' if args.mms else 'sms'} status={gw.status}")
    print(f"[body]     {args.body[:160]!r}")
    if len(args.body) > 160 and not args.mms:
        print(f"[warn]     body > 160 chars, SMS gateway will fragment or truncate")

    if args.dry_run:
        print("[dry-run]  not sending")
        return 0

    try:
        send(
            smtp_host=args.smtp_host,
            smtp_port=args.smtp_port,
            smtp_user=args.smtp_user,
            smtp_pass=args.smtp_pass,
            msg=msg,
            starttls=not args.smtp_ssl,
            verbose=args.verbose,
        )
    except smtplib.SMTPException as e:
        print(f"[fail]     SMTP error: {e}", file=sys.stderr)
        return 5

    print(f"[ok]       handed off to {args.smtp_host}:{args.smtp_port}, "
          f"check handset for delivery (typical < 30s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
