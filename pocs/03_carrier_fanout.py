#!/usr/bin/env python3
"""
03 — Multi-carrier fan-out for recon.

Sends the same message to every active carrier gateway in parallel.
Only the one matching the target's real carrier will deliver — the
rest bounce or silently drop. Useful when carrier-lookup is
unavailable and you need to discover the carrier empirically by
asking the target which message they received.

Operational caveat: this is loud. Every wrong gateway logs an SMTP
session against your sending domain. Several of the "dead" gateways
are now operated by abuse researchers as honeypots — see
attack_vectors/01_gateway_discovery.md.

Run:
    export SMTP_USER="you@gmail.com"
    export SMTP_APP_PW="xxxx xxxx xxxx xxxx"
    python pocs/03_carrier_fanout.py --to 2155551234 \\
        --body "which gateway worked? reply with the sender shown"
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gateway_domains  # noqa: E402


@dataclass
class Result:
    carrier: str
    gateway: str
    channel: str
    status: str
    detail: str = ""


def send_one(
    *, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
    from_addr: str, to_addr: str, body: str, subject: str,
) -> tuple[int, str]:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(smtp_user, smtp_pass)
        try:
            s.send_message(msg)
            return 250, "ok"
        except smtplib.SMTPRecipientsRefused as e:
            recip = next(iter(e.recipients.values()))
            return recip[0], recip[1].decode(errors="replace") \
                if isinstance(recip[1], bytes) else str(recip[1])


def fanout(
    *, to_number: str, body: str, subject: str, smtp_host: str, smtp_port: int,
    smtp_user: str, smtp_pass: str, mms: bool, max_workers: int,
) -> list[Result]:
    targets: list[tuple[gateway_domains.Gateway, str, str]] = []
    for gw in gateway_domains.GATEWAYS:
        domain = gw.mms_domain if mms else gw.sms_domain
        if not domain:
            continue
        targets.append((gw, domain, "mms" if mms else "sms"))

    results: list[Result] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_target = {}
        for gw, domain, channel in targets:
            to_addr = f"{to_number}@{domain}"
            fut = ex.submit(
                send_one,
                smtp_host=smtp_host, smtp_port=smtp_port,
                smtp_user=smtp_user, smtp_pass=smtp_pass,
                from_addr=smtp_user, to_addr=to_addr,
                body=body, subject=subject,
            )
            future_to_target[fut] = (gw, domain, channel)
        for fut in concurrent.futures.as_completed(future_to_target):
            gw, domain, channel = future_to_target[fut]
            try:
                code, detail = fut.result()
                results.append(Result(gw.carrier, domain, channel,
                                      "accept" if 200 <= code < 400 else f"reject:{code}",
                                      detail))
            except Exception as e:
                results.append(Result(gw.carrier, domain, channel, "error", str(e)))
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fan-out send to every active carrier gateway.")
    p.add_argument("--to", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--subject", default="")
    p.add_argument("--mms", action="store_true",
                   help="Use MMS gateways instead of SMS")
    p.add_argument("--smtp-host", default="smtp.gmail.com")
    p.add_argument("--smtp-port", default=587, type=int)
    p.add_argument("--smtp-user", default=os.environ.get("SMTP_USER"))
    p.add_argument("--smtp-pass", default=os.environ.get("SMTP_APP_PW"))
    p.add_argument("--max-workers", default=6, type=int)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if not (args.smtp_user and args.smtp_pass) and not args.dry_run:
        print("SMTP_USER and SMTP_APP_PW must be set", file=sys.stderr)
        return 2

    targets = []
    for gw in gateway_domains.GATEWAYS:
        d = gw.mms_domain if args.mms else gw.sms_domain
        if d:
            targets.append((gw.carrier, d, gw.status))

    print(f"[plan]     fan-out to {len(targets)} "
          f"{'mms' if args.mms else 'sms'} gateways")
    for carrier, domain, status in targets:
        print(f"           {carrier:14s}  {domain:30s}  [{status}]")

    if args.dry_run:
        print("[dry-run]  not sending")
        return 0

    results = fanout(
        to_number=args.to, body=args.body, subject=args.subject,
        smtp_host=args.smtp_host, smtp_port=args.smtp_port,
        smtp_user=args.smtp_user, smtp_pass=args.smtp_pass,
        mms=args.mms, max_workers=args.max_workers,
    )

    print()
    print(f"[results]  {'carrier':14s}  {'gateway':30s}  {'status':14s}  detail")
    for r in sorted(results, key=lambda x: x.status):
        detail = r.detail[:60] + ("..." if len(r.detail) > 60 else "")
        print(f"           {r.carrier:14s}  {r.gateway:30s}  {r.status:14s}  {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
