#!/usr/bin/env python3
"""
Canonical list of US carrier email-to-SMS / MMS gateway domains.

Single source of truth used by the PoCs. Status field reflects the
verified state as of May 2026. Update by running:

    python tools/gateway_domains.py --probe

which resolves MX records and reports any that no longer publish one.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class Gateway:
    carrier: str
    sms_domain: Optional[str]
    mms_domain: Optional[str]
    status: str           # active | mms-only | dead
    notes: str            # filter-strictness, MVNO parent, etc.


GATEWAYS: tuple[Gateway, ...] = (
    Gateway("att",          None,                     None,                     "dead",
            "Gateway retired. As of 2026-05-23 DoH shows txt.att.net and "
            "mms.att.net publish SOA but zero MX records. AT&T removed the "
            "MX records rather than kill the zones."),
    Gateway("tmobile",      "tmomail.net",            "tmomail.net",            "active",
            "MX behind Proofpoint Cloudmark (*.cloudfilter.net). Accepts "
            "domain-aligned authenticated senders; silently drops consumer-mail "
            "sources (Gmail/Yahoo/etc.)."),
    Gateway("verizon",      "vtext.com",              "vzwpix.com",             "active",
            "Both vtext.com (SMS) and vzwpix.com (MMS) have live MX behind "
            "Proofpoint Cloudmark. Earlier reports of vtext.com being killed "
            "in 2022 are inaccurate per 2026-05-23 recon; what was killed "
            "was open delivery, not the zone."),
    Gateway("uscellular",   "email.uscc.net",         "mms.uscc.net",           "active",
            "Own infrastructure (av*/sc*.mx.uscc.net), not Proofpoint. "
            "Filtering posture less characterized in 2026."),
    Gateway("googlefi",     "msg.fi.google.com",      "msg.fi.google.com",      "active",
            "Google's own MX (gmr-smtp-in.l.google.com). Strict SPF/DKIM."),
    Gateway("cricket",      None,                     None,                     "dead",
            "sms.cricketwireless.net is now a CNAME to Akamai edge "
            "(redirects-cricketwireless.edgekey.net). No mail server. "
            "Confirmed dead 2026-05-23."),
    Gateway("boost",        "tmomail.net",            "tmomail.net",            "active",
            "T-Mobile MVNO since 2020. Same Proofpoint-fronted gateway."),
    Gateway("metro",        "tmomail.net",            "tmomail.net",            "active",
            "T-Mobile MVNO. Same Proofpoint-fronted gateway."),
    Gateway("mint",         "tmomail.net",            "tmomail.net",            "active",
            "T-Mobile MVNO. Same Proofpoint-fronted gateway."),
    Gateway("spectrum",     "vtext.com",              "vzwpix.com",             "active",
            "Verizon MVNO. Inherits the Proofpoint-fronted gateways."),
    Gateway("xfinity",      "vtext.com",              "vzwpix.com",             "active",
            "Verizon MVNO. Inherits the Proofpoint-fronted gateways. "
            "Empirical 2026-05-23 test: Gmail-originated mail to "
            "vzwpix.com silently dropped."),
    Gateway("sprint",       None,                     None,                     "dead",
            "Merged into T-Mobile. messaging.sprintpcs.com publishes no MX."),
    Gateway("nextel",       None,                     None,                     "dead",
            "Brand discontinued. messaging.nextel.com dead."),
)


def by_carrier(name: str) -> Optional[Gateway]:
    name = name.lower().strip()
    for g in GATEWAYS:
        if g.carrier == name:
            return g
    return None


def active() -> list[Gateway]:
    return [g for g in GATEWAYS if g.status in ("active", "mms-only")]


def _probe_mx(domain: str) -> bool:
    """Return True if the domain resolves to *something* on port 25.
    Uses socket.getaddrinfo as a stdlib fallback for MX absence check —
    real MX resolution needs dnspython, see _probe_mx_dns."""
    try:
        socket.getaddrinfo(domain, 25)
        return True
    except socket.gaierror:
        return False


def _probe_mx_dns(domain: str) -> Optional[str]:
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        return None
    try:
        answer = dns.resolver.resolve(domain, "MX")
        return sorted(answer, key=lambda r: r.preference)[0].exchange.to_text()
    except Exception:
        return None


def cmd_list(args: argparse.Namespace) -> int:
    rows = active() if args.active_only else list(GATEWAYS)
    if args.json:
        print(json.dumps([asdict(g) for g in rows], indent=2))
        return 0
    for g in rows:
        sms = g.sms_domain or "-"
        mms = g.mms_domain or "-"
        print(f"{g.carrier:14s}  sms:{sms:30s}  mms:{mms:30s}  [{g.status}]")
        if args.verbose:
            print(f"{'':14s}    {g.notes}")
    return 0


def cmd_carrier(args: argparse.Namespace) -> int:
    g = by_carrier(args.carrier)
    if not g:
        print(f"unknown carrier: {args.carrier}", file=sys.stderr)
        print(f"available: {', '.join(x.carrier for x in GATEWAYS)}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(g), indent=2))
    else:
        print(f"carrier:    {g.carrier}")
        print(f"sms:        {g.sms_domain or '(none)'}")
        print(f"mms:        {g.mms_domain or '(none)'}")
        print(f"status:     {g.status}")
        print(f"notes:      {g.notes}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    print(f"{'carrier':14s}  {'domain':30s}  {'status':10s}  mx")
    for g in GATEWAYS:
        for label, domain in (("sms", g.sms_domain), ("mms", g.mms_domain)):
            if not domain:
                continue
            mx = _probe_mx_dns(domain)
            alive = _probe_mx(domain)
            marker = mx if mx else ("resolves" if alive else "DEAD")
            print(f"{g.carrier:14s}  {label}:{domain:26s}  {g.status:10s}  {marker}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="US carrier email-to-SMS gateway directory.")
    sub = p.add_subparsers(dest="cmd", required=False)

    p.set_defaults(cmd_func=cmd_list, active_only=False, json=False, verbose=False)

    pl = sub.add_parser("list", help="list all gateways")
    pl.add_argument("--active-only", action="store_true")
    pl.add_argument("--json", action="store_true")
    pl.add_argument("--verbose", "-v", action="store_true")
    pl.set_defaults(cmd_func=cmd_list)

    pc = sub.add_parser("carrier", help="look up one carrier")
    pc.add_argument("carrier")
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(cmd_func=cmd_carrier)

    pp = sub.add_parser("probe", help="MX-probe every known domain (requires dnspython)")
    pp.set_defaults(cmd_func=cmd_probe)

    # Convenience flags that work without a subcommand
    p.add_argument("--list",        action="store_true", dest="_list_flag")
    p.add_argument("--carrier",     dest="_carrier_flag")
    p.add_argument("--probe",       action="store_true", dest="_probe_flag")

    args = p.parse_args(argv)

    if args._list_flag:
        return cmd_list(argparse.Namespace(active_only=False, json=False, verbose=True))
    if args._carrier_flag:
        return cmd_carrier(argparse.Namespace(carrier=args._carrier_flag, json=False))
    if args._probe_flag:
        return cmd_probe(args)

    return args.cmd_func(args)


if __name__ == "__main__":
    sys.exit(main())
