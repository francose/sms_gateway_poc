#!/usr/bin/env python3
"""
02 — Direct-to-MX delivery (no auth SMTP).

Resolves the carrier gateway's MX record and connects to port 25
directly with your own EHLO. Bypasses any provider-side DMARC
enforcement on outbound. Requires that you control:

  - The sending IP (clean rDNS matching your HELO hostname)
  - The From: domain (SPF / DKIM / DMARC published correctly)

Without those, the carrier MTA will reject or silently drop. This PoC
prints the SMTP transcript so you can see exactly which check failed.

Requires `dnspython` for MX resolution:
    pip install dnspython

Run:
    python pocs/02_direct_to_mx.py \\
        --to 2155551234 --carrier tmobile \\
        --from-addr alerts@yourdomain.tld \\
        --helo mail.yourdomain.tld \\
        --body "direct MX path"
"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gateway_domains  # noqa: E402


def resolve_mx(domain: str) -> list[str]:
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        raise SystemExit("this PoC needs dnspython: pip install dnspython")
    answer = dns.resolver.resolve(domain, "MX")
    return [rdata.exchange.to_text().rstrip(".")
            for rdata in sorted(answer, key=lambda r: r.preference)]


def build_message(*, from_addr: str, to_addr: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_direct(
    *, mx_host: str, helo: str, from_addr: str, to_addr: str,
    msg: EmailMessage, port: int = 25, verbose: bool = False,
) -> tuple[int, str]:
    s = smtplib.SMTP(mx_host, port, local_hostname=helo, timeout=30)
    if verbose:
        s.set_debuglevel(1)
    try:
        s.ehlo(helo)
        code, resp = s.mail(from_addr)
        if code >= 400:
            return code, f"MAIL FROM rejected: {resp!r}"
        code, resp = s.rcpt(to_addr)
        if code >= 400:
            return code, f"RCPT TO rejected: {resp!r}"
        code, resp = s.data(msg.as_string())
        return code, resp.decode(errors="replace") if isinstance(resp, bytes) else str(resp)
    finally:
        try:
            s.quit()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Direct-to-MX SMTP delivery to a carrier gateway.")
    p.add_argument("--to", required=True, help="Recipient 10-digit US number")
    p.add_argument("--carrier", required=True,
                   help=f"Carrier key: {', '.join(g.carrier for g in gateway_domains.GATEWAYS)}")
    p.add_argument("--from-addr", required=True,
                   help="From: address on a domain you control (SPF/DKIM/DMARC published)")
    p.add_argument("--helo", required=True,
                   help="HELO/EHLO hostname (must have rDNS matching your sending IP)")
    p.add_argument("--body", required=True)
    p.add_argument("--subject", default="")
    p.add_argument("--mms", action="store_true",
                   help="Target the MMS gateway instead of SMS")
    p.add_argument("--port", default=25, type=int)
    p.add_argument("--mx-host", default=None,
                   help="Override MX resolution (e.g. pin a specific gateway MTA)")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    gw = gateway_domains.by_carrier(args.carrier)
    if not gw:
        print(f"unknown carrier: {args.carrier}", file=sys.stderr)
        return 2
    domain = gw.mms_domain if args.mms else gw.sms_domain
    if not domain:
        print(f"carrier {args.carrier!r} has no "
              f"{'mms' if args.mms else 'sms'} gateway", file=sys.stderr)
        return 3
    to_addr = f"{args.to}@{domain}"

    if args.mx_host:
        mx_hosts = [args.mx_host]
    else:
        mx_hosts = resolve_mx(domain)
        if not mx_hosts:
            print(f"no MX records for {domain}", file=sys.stderr)
            return 4

    msg = build_message(from_addr=args.from_addr, to_addr=to_addr,
                        subject=args.subject, body=args.body)

    print(f"[gateway]  {gw.carrier} {'mms' if args.mms else 'sms'} → {domain}")
    print(f"[mx]       candidates: {mx_hosts}")
    print(f"[envelope] from={args.from_addr}  to={to_addr}")
    print(f"[helo]     {args.helo}")
    print(f"[body]     {args.body[:160]!r}")

    if args.dry_run:
        print("[dry-run]  not connecting")
        return 0

    last_err = None
    for host in mx_hosts:
        print(f"[connect]  {host}:{args.port}")
        try:
            code, resp = send_direct(
                mx_host=host, helo=args.helo,
                from_addr=args.from_addr, to_addr=to_addr,
                msg=msg, port=args.port, verbose=args.verbose,
            )
        except (smtplib.SMTPException, OSError) as e:
            print(f"[err]      {host}: {e}")
            last_err = e
            continue
        print(f"[reply]    {code} {resp!r}")
        if 200 <= code < 400:
            print(f"[ok]       accepted by {host}")
            return 0
    print(f"[fail]     no MX accepted the message"
          f"{f' (last error: {last_err})' if last_err else ''}",
          file=sys.stderr)
    return 5


if __name__ == "__main__":
    sys.exit(main())
