#!/usr/bin/env python3
"""
OmniMind Billing — end-to-end test.

Tests both the offline (no Stripe key) and live (Stripe test key) paths.
Run from python/ directory:
  python test_billing.py              # offline/mock mode
  STRIPE_SECRET_KEY=sk_test_... python test_billing.py  # live Stripe test mode
"""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path

# Use a temp DB so tests don't pollute real data
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["OMNIMIND_DB"] = _tmp.name

import omnimind_billing as billing
from omnimind_warfare import Database

STRIPE_LIVE = bool(os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_"))
MODE = "LIVE (Stripe test mode)" if STRIPE_LIVE else "OFFLINE (mock/fallback mode)"

print(f"\n{'='*60}")
print(f"  OmniMind Billing Test — {MODE}")
print(f"{'='*60}\n")

# ── 1. Seed test clients ──────────────────────────────────────────────────────
print("1. Seeding test clients...")
db = Database(_tmp.name)

c1 = db.add_client("Smith & Associates Law",   "smithlaw.ca",       email="billing@smithlaw.ca",       phone="+1-416-555-0101")
c2 = db.add_client("Toronto Medical Center",   "torontomedical.ca", email="admin@torontomedical.ca",   phone="+1-416-555-0202")
c3 = db.add_client("Peak Consulting Group",    "peakconsulting.ca", email="hello@peakconsulting.ca",   phone="+1-416-555-0303")

db.upgrade_to_paid(c1, "security",    599.0)
db.upgrade_to_paid(c2, "enterprise", 1299.0)

print(f"   Added 3 clients; {c1} and {c2} set to active\n")

# ── 2. MRR dashboard ─────────────────────────────────────────────────────────
print("2. MRR Dashboard:")
billing._ensure_billing_columns()
billing.mrr_dashboard()

# ── 3. PDF invoice generation ─────────────────────────────────────────────────
print("3. Generating PDF invoice for client 1...")
try:
    pdf_bytes = billing.generate_invoice_pdf(c1)
    ext = "pdf" if billing.REPORTLAB_OK else "txt"
    out = Path(f"./test_invoice_c{c1}.{ext}")
    out.write_bytes(pdf_bytes)
    print(f"   Invoice written: {out} ({len(pdf_bytes):,} bytes)\n")
except Exception as e:
    print(f"   ERROR: {e}\n")

# ── 4. Stripe payment link ───────────────────────────────────────────────────
print("4. Stripe payment link for client 1 (setup fee):")
try:
    url = billing.create_payment_link(c1, "setup")
    print(f"   URL: {url}\n")
except Exception as e:
    print(f"   ERROR: {e}\n")

# ── 5. Monthly charge (all active) ───────────────────────────────────────────
print("5. Bill all active clients (monthly retainer):")
billing.bill_all_active()
print()

# ── 6. Verify payment logs ───────────────────────────────────────────────────
print("6. Payment log:")
with sqlite3.connect(_tmp.name) as conn:
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM payments ORDER BY id").fetchall()
        if rows:
            for r in rows:
                print(f"   client={r['client_id']} amount=${r['amount']:.2f} method={r['method']}")
        else:
            print("   (no payments logged yet)")
    except Exception:
        print("   (payments table not created — charge may not have run)")
print()

# ── 7. Stripe subscription (live mode only) ───────────────────────────────────
if STRIPE_LIVE:
    print("7. Creating Stripe subscription for client 2...")
    try:
        sub_id = billing.create_subscription(c2, "admin@torontomedical.ca")
        print(f"   Subscription ID: {sub_id}\n")
    except Exception as e:
        print(f"   ERROR: {e}\n")
else:
    print("7. [SKIP] Stripe subscription — set STRIPE_SECRET_KEY=sk_test_... to test\n")

# ── Done ─────────────────────────────────────────────────────────────────────
import os as _os
_os.unlink(_tmp.name)
print(f"{'='*60}")
print(f"  Test complete ({MODE})")
print(f"{'='*60}\n")
