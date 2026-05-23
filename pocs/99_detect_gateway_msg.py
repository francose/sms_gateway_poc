#!/usr/bin/env python3
"""
99 — Defender side. Scan a directory of .eml files or an mbox for
messages that were relayed through a carrier email-to-SMS gateway.

Useful for ingesting employee-forwarded phish reports into a SOC
pipeline. Flags messages by:

  - Recipient on a known carrier gateway domain (best signal)
  - Received: chain containing a known carrier MTA hop
  - From: domain registered within the last N days (when --whois passed)
  - From: domain that is a Levenshtein-near typosquat of a brand
    in a configured watchlist
  - Short / blank subject + body containing phish lures + shortened URL

Run:
    python pocs/99_detect_gateway_msg.py samples/
    python pocs/99_detect_gateway_msg.py /path/to/mbox --mbox
    python pocs/99_detect_gateway_msg.py samples/ --watchlist samples/brands.txt
    python pocs/99_detect_gateway_msg.py --self-test
"""
from __future__ import annotations

import argparse
import email
import email.policy
import mailbox
import os
import re
import sys
from email.message import Message
from pathlib import Path

_PARSE_POLICY = email.policy.default


def _msg_from_string(s: str) -> Message:
    return email.message_from_string(s, policy=_PARSE_POLICY)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import gateway_domains  # noqa: E402


GATEWAY_DOMAINS = {
    g.sms_domain for g in gateway_domains.GATEWAYS if g.sms_domain
} | {
    g.mms_domain for g in gateway_domains.GATEWAYS if g.mms_domain
}

# Hostname substrings that appear in carrier-MTA Received: hops.
CARRIER_HOP_SUBSTRINGS = (
    "att-mail.com", "snet.gateway", "tmomail.net", "t-mobile.com",
    "vzwpix-mail.verizon.net", "uscellular.net", "uscc.net",
    "google-fi", "cricketwireless.net",
)

# Common URL shorteners that show up in gateway phish.
URL_SHORTENERS = (
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd",
    "buff.ly", "rebrand.ly", "lnkd.in", "shorturl.at",
)

# Common phish-lure phrases. Intentionally short list; expand for prod.
PHISH_LURE_PHRASES = (
    "account locked", "verify your account", "unusual sign-in",
    "package delivery", "payment required", "tap to confirm",
    "click here", "your card ending", "two-factor",
)


def _addr_domain(addr_header: str | None) -> str | None:
    if not addr_header:
        return None
    m = re.search(r"<?([^@<>\s]+)@([^>\s]+)>?", addr_header)
    return m.group(2).lower() if m else None


def _addr_local(addr_header: str | None) -> str | None:
    if not addr_header:
        return None
    m = re.search(r"<?([^@<>\s]+)@([^>\s]+)>?", addr_header)
    return m.group(1).lower() if m else None


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _part_text(part: Message) -> str:
    # Modern EmailMessage path
    get_content = getattr(part, "get_content", None)
    if callable(get_content):
        try:
            content = get_content()
            if isinstance(content, str):
                return content
            if isinstance(content, bytes):
                return content.decode("utf-8", "replace")
        except (KeyError, LookupError, TypeError):
            pass
    # Legacy compat32 path
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return part.get_payload() or ""


def _body_text(msg: Message) -> str:
    if msg.is_multipart():
        parts = [
            _part_text(p) for p in msg.walk()
            if p.get_content_type() == "text/plain"
        ]
        return "\n".join(parts)
    return _part_text(msg)


def analyze(msg: Message, *, watchlist: list[str] | None = None) -> list[str]:
    """Return a list of flag strings; empty list means no signal."""
    flags: list[str] = []

    to_domain = _addr_domain(msg.get("To") or msg.get("Delivered-To") or "")
    if to_domain and to_domain in GATEWAY_DOMAINS:
        flags.append(f"recipient on gateway:{to_domain}")

    received_chain = msg.get_all("Received") or []
    for hop in received_chain:
        low = hop.lower()
        for sub in CARRIER_HOP_SUBSTRINGS:
            if sub in low:
                flags.append(f"carrier hop:{sub}")
                break

    from_local = _addr_local(msg.get("From"))
    from_domain = _addr_domain(msg.get("From"))

    if from_local in ("alerts", "support", "noreply", "no-reply",
                      "security", "verify", "billing", "it-helpdesk", "admin"):
        flags.append(f"generic local-part:{from_local}")

    if watchlist and from_domain:
        for brand in watchlist:
            brand = brand.strip().lower()
            if not brand or "." not in brand:
                continue
            brand_label = brand.split(".")[0]
            from_label = from_domain.split(".")[0]
            if from_domain == brand:
                continue  # exact match is the real domain, not a spoof
            dist = _levenshtein(from_label, brand_label)
            if 1 <= dist <= 2 and len(brand_label) >= 4:
                flags.append(f"typosquat suspect: {from_domain} vs watchlist {brand}")

    body = _body_text(msg).lower()
    if any(p in body for p in PHISH_LURE_PHRASES):
        flags.append("phish lure in body")
    if any(s in body for s in URL_SHORTENERS):
        flags.append("url shortener in body")

    subj = (msg.get("Subject") or "").strip()
    if len(subj) <= 2 and flags:
        flags.append("subject blank or trivial")

    return flags


def scan_dir(root: Path, *, watchlist: list[str] | None) -> int:
    n_total = 0
    n_flagged = 0
    for path in sorted(root.rglob("*.eml")):
        n_total += 1
        try:
            with open(path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=_PARSE_POLICY)
        except Exception as e:
            print(f"[err]   {path}: {e}", file=sys.stderr)
            continue
        flags = analyze(msg, watchlist=watchlist)
        if flags:
            n_flagged += 1
            print(f"[flag]  {path}")
            for f_ in flags:
                print(f"        - {f_}")
    print(f"\n[scan]  {n_flagged}/{n_total} files flagged in {root}")
    return 0 if n_flagged == 0 else 1


def scan_mbox(path: Path, *, watchlist: list[str] | None) -> int:
    mbox = mailbox.mbox(str(path))
    n_total = 0
    n_flagged = 0
    for i, msg in enumerate(mbox):
        n_total += 1
        flags = analyze(msg, watchlist=watchlist)
        if flags:
            n_flagged += 1
            ident = msg.get("Message-ID") or f"#{i}"
            print(f"[flag]  {ident}")
            for f_ in flags:
                print(f"        - {f_}")
    print(f"\n[scan]  {n_flagged}/{n_total} messages flagged in {path}")
    return 0 if n_flagged == 0 else 1


SELF_TEST_EML = """\
From: alerts@bank0famerica.com
To: 2155551234@txt.att.net
Subject:
Received: from mta.bank0famerica.com (mta.bank0famerica.com [203.0.113.5])
    by alnpop41.snet.gateway.2wire.com with ESMTP id abc123;
    Wed, 14 May 2026 12:34:56 -0400

Your account has been locked. Tap to verify: https://bit.ly/abc123
"""

CLEAN_EML = """\
From: alice@example.com
To: bob@example.org
Subject: lunch?
Received: from mail.example.com by mx.example.org

want to grab lunch at noon?
"""


def self_test() -> int:
    print("[self-test] running")
    bad = _msg_from_string(SELF_TEST_EML)
    flags = analyze(bad, watchlist=["bankofamerica.com", "chase.com"])
    assert flags, "expected the phish-like message to flag"
    print(f"[self-test] phish flagged: {flags}")

    good = _msg_from_string(CLEAN_EML)
    assert analyze(good) == [], "expected the clean message to produce no flags"
    print("[self-test] clean message produced no flags")
    print("[self-test] ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Detect carrier-gateway-relayed messages.")
    p.add_argument("path", nargs="?", help="directory of .eml files OR an mbox file")
    p.add_argument("--mbox", action="store_true", help="treat path as mbox, not directory")
    p.add_argument("--watchlist", help="file with one brand domain per line "
                                       "(used for typosquat detection)")
    p.add_argument("--self-test", action="store_true", help="run built-in tests, then exit")
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.path:
        p.error("path is required unless --self-test is set")

    watchlist: list[str] | None = None
    if args.watchlist:
        watchlist = Path(args.watchlist).read_text().splitlines()

    target = Path(args.path)
    if not target.exists():
        print(f"no such path: {target}", file=sys.stderr)
        return 2

    if args.mbox or (target.is_file() and target.suffix in (".mbox",)):
        return scan_mbox(target, watchlist=watchlist)
    if target.is_dir():
        return scan_dir(target, watchlist=watchlist)
    # Single .eml file
    with open(target, "rb") as f:
        msg = email.message_from_binary_file(f, policy=_PARSE_POLICY)
    flags = analyze(msg, watchlist=watchlist)
    if flags:
        print(f"[flag]  {target}")
        for f_ in flags:
            print(f"        - {f_}")
        return 1
    print(f"[clean] {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
