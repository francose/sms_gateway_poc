#!/usr/bin/env python3
"""
Carrier lookup helpers.

Wraps a few free + paid carrier-lookup APIs and maps the returned
carrier name to the gateway domain. Use during recon before sending.

Supported backends:
  - numverify       (free tier, 100 req/mo, env: NUMVERIFY_KEY)
  - twilio          (paid, very accurate, env: TWILIO_SID + TWILIO_TOKEN)
  - free-lookup     (no key, unreliable, scrapes a public HTML page)

Usage:
    python tools/carrier_lookup.py 12155551234
    python tools/carrier_lookup.py 12155551234 --backend twilio
    python tools/carrier_lookup.py 12155551234 --backend free-lookup
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Path hack so we can import sibling module without packaging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gateway_domains  # noqa: E402


CARRIER_NAME_TO_KEY = {
    # Map vendor-returned strings to our gateway_domains keys.
    "at&t":                   "att",
    "at&t mobility":          "att",
    "at&t wireless":          "att",
    "t-mobile":               "tmobile",
    "t-mobile usa":           "tmobile",
    "t-mobile us inc.":       "tmobile",
    "verizon":                "verizon",
    "verizon wireless":       "verizon",
    "cellco partnership dba verizon wireless": "verizon",
    "us cellular":            "uscellular",
    "united states cellular": "uscellular",
    "google fi":              "googlefi",
    "google":                 "googlefi",
    "cricket":                "cricket",
    "cricket communications": "cricket",
    "boost mobile":           "boost",
    "metropcs":               "metro",
    "metro by t-mobile":      "metro",
    "mint mobile":            "mint",
    "spectrum mobile":        "spectrum",
    "xfinity mobile":         "xfinity",
}


def _normalize(num: str) -> str:
    digits = re.sub(r"\D", "", num)
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    if len(digits) == 10:
        return digits
    raise ValueError(f"could not normalize {num!r} to a 10-digit US number")


def _map_to_gateway(carrier_name: str) -> Optional[gateway_domains.Gateway]:
    key = CARRIER_NAME_TO_KEY.get(carrier_name.lower().strip())
    if not key:
        return None
    return gateway_domains.by_carrier(key)


def lookup_numverify(number: str) -> Optional[dict]:
    key = os.environ.get("NUMVERIFY_KEY")
    if not key:
        raise SystemExit("NUMVERIFY_KEY not set in environment")
    url = "http://apilayer.net/api/validate?" + urllib.parse.urlencode({
        "access_key": key,
        "number": number,
        "country_code": "US",
    })
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def lookup_twilio(number: str) -> Optional[dict]:
    sid = os.environ.get("TWILIO_SID")
    tok = os.environ.get("TWILIO_TOKEN")
    if not (sid and tok):
        raise SystemExit("TWILIO_SID and TWILIO_TOKEN required for twilio backend")
    e164 = "+1" + _normalize(number)
    url = f"https://lookups.twilio.com/v2/PhoneNumbers/{e164}?Fields=line_type_intelligence"
    import base64
    auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def lookup_free(number: str) -> Optional[dict]:
    """Scrapes a public lookup page. Unreliable, breaks when the page
    changes. Included for stdlib-only no-key recon."""
    e10 = _normalize(number)
    url = f"https://www.freecarrierlookup.com/index.php"
    body = urllib.parse.urlencode({
        "cnam": "", "phonenum": e10, "submit": "Submit"
    }).encode()
    req = urllib.request.Request(url, data=body)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return {"error": f"http {e.code}"}
    m = re.search(r"Carrier:\s*</strong>\s*([^<\n]+)", html, re.I)
    if not m:
        return {"error": "carrier not in response (page likely changed)"}
    return {"carrier": m.group(1).strip()}


def carrier_to_gateway(carrier_name: str) -> str:
    g = _map_to_gateway(carrier_name)
    if not g:
        return f"(no gateway mapping for carrier {carrier_name!r})"
    return f"sms:{g.sms_domain or '(none)'}  mms:{g.mms_domain or '(none)'}  status:{g.status}"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Lookup carrier + gateway for a US number.")
    p.add_argument("number", help="10 or 11 digit US number, any format")
    p.add_argument("--backend", choices=("numverify", "twilio", "free-lookup"),
                   default="numverify")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    try:
        normalized = _normalize(args.number)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    result: dict = {}
    if args.backend == "numverify":
        result = lookup_numverify(normalized) or {}
        carrier_name = result.get("carrier", "")
    elif args.backend == "twilio":
        result = lookup_twilio(normalized) or {}
        carrier_name = (result.get("line_type_intelligence") or {}).get("carrier_name", "")
    else:
        result = lookup_free(normalized) or {}
        carrier_name = result.get("carrier", "")

    if args.json:
        print(json.dumps({
            "number": normalized,
            "backend": args.backend,
            "raw": result,
            "carrier_name": carrier_name,
            "gateway": carrier_to_gateway(carrier_name),
        }, indent=2))
    else:
        print(f"number:       {normalized}")
        print(f"backend:      {args.backend}")
        print(f"carrier_name: {carrier_name or '(unknown)'}")
        print(f"gateway:      {carrier_to_gateway(carrier_name)}")
        if "error" in result:
            print(f"error:        {result['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
