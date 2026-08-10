#!/usr/bin/env python3
"""
OmniMind Revenue Engine — Stripe billing + SMTP email + PDF invoices.

Env vars (put in .env or export before running):
  STRIPE_SECRET_KEY     sk_live_... or sk_test_...
  STRIPE_PRICE_SETUP    Stripe price ID for one-time setup fee
  STRIPE_PRICE_MONTHLY  Stripe price ID for monthly retainer
  SMTP_HOST             default: smtp.gmail.com
  SMTP_PORT             default: 587
  SMTP_USER             your@email.com
  SMTP_PASS             app password
  SMTP_FROM             defaults to SMTP_USER
  OMNIMIND_DB           default: ./omnimind_warfare.db

Usage (standalone):
  python omnimind_billing.py link <client_id>     # Stripe payment link
  python omnimind_billing.py subscribe <client_id> <customer_email>  # Monthly sub
  python omnimind_billing.py charge <client_id>   # One-off monthly charge
  python omnimind_billing.py invoice <client_id>  # PDF invoice
  python omnimind_billing.py email <client_id>    # Email latest invoice
  python omnimind_billing.py bill                 # Charge all active clients
  python omnimind_billing.py mrr                  # MRR + $8K goal tracker
"""

import os
import sqlite3
import smtplib
import sys
from datetime import datetime, timedelta
from email import encoders
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

# ── Optional dependencies — degrade gracefully ────────────────────────────────
try:
    import stripe as _stripe
    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_OK = bool(_stripe.api_key)
except ImportError:
    _stripe = None
    STRIPE_OK = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ── Pricing tiers ─────────────────────────────────────────────────────────────
PACKAGES: Dict[str, Dict] = {
    "starter":    {"setup": 399,  "monthly": 299,  "label": "Starter Security"},
    "security":   {"setup": 599,  "monthly": 499,  "label": "Managed Security"},
    "enterprise": {"setup": 1299, "monthly": 999,  "label": "Enterprise Shield"},
}

TARGET_MRR = 8000   # $8K/month goal
DB_PATH = os.environ.get("OMNIMIND_DB", "./omnimind_warfare.db")


# =============================================================================
# DATABASE (read-only; writes stay in omnimind_warfare.py)
# =============================================================================

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _get_client(client_id: int) -> Optional[Dict]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        return dict(row) if row else None


def _active_clients() -> List[Dict]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM clients WHERE status = 'active'").fetchall()
        return [dict(r) for r in rows]


def _log_payment(client_id: int, amount: float, method: str, note: str = ""):
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                client_id INTEGER,
                amount REAL,
                method TEXT,
                note TEXT,
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO payments (client_id, amount, method, note) VALUES (?, ?, ?, ?)",
            (client_id, amount, method, note),
        )
        conn.execute(
            "UPDATE clients SET monthly_paid = monthly_paid + ? WHERE id = ?",
            (amount, client_id),
        )
        conn.commit()


# =============================================================================
# STRIPE
# =============================================================================

def create_payment_link(client_id: int, fee_type: str = "setup") -> str:
    """
    Generate a Stripe payment link for setup fee or one-time charge.
    Returns the URL to send to the client.
    Falls back to a formatted invoice URL if Stripe unavailable.
    """
    client = _get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")

    pkg = client.get("package") or "security"
    price_info = PACKAGES.get(pkg, PACKAGES["security"])
    amount_cents = int(price_info[fee_type] * 100)

    if not STRIPE_OK:
        # Fallback: PayPal.me or Venmo deep-link with pre-filled amount
        amount = price_info[fee_type]
        name_slug = client["name"].replace(" ", "+")
        print(f"[STRIPE NOT CONFIGURED] Send manual payment request:")
        print(f"  PayPal  : https://paypal.me/YourHandle/{amount}")
        print(f"  Venmo   : https://venmo.com/YourHandle?txn=charge&amount={amount}&note={name_slug}+Security+Setup")
        print(f"  Wise    : Create invoice for ${amount} to {client.get('email', 'client')}")
        return f"https://paypal.me/YourHandle/{amount}"

    price_id = os.environ.get("STRIPE_PRICE_SETUP" if fee_type == "setup" else "STRIPE_PRICE_MONTHLY")

    if price_id:
        session = _stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            customer_email=client.get("email"),
            metadata={"client_id": str(client_id), "client_name": client["name"]},
            success_url="https://omnimind.security/thank-you?session={CHECKOUT_SESSION_ID}",
            cancel_url="https://omnimind.security/contact",
        )
    else:
        session = _stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"{price_info['label']} — Setup Fee",
                        "description": f"One-time onboarding and security baseline for {client['name']}",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            customer_email=client.get("email"),
            metadata={"client_id": str(client_id)},
            success_url="https://omnimind.security/thank-you?session={CHECKOUT_SESSION_ID}",
            cancel_url="https://omnimind.security/contact",
        )

    url = session.url
    _log_payment(client_id, 0, "stripe_link_sent", f"Checkout link: {url}")
    print(f"[STRIPE] Payment link for {client['name']}: {url}")
    return url


def create_subscription(client_id: int, customer_email: str) -> str:
    """Create a Stripe subscription for monthly retainer. Returns subscription ID."""
    if not STRIPE_OK:
        print("[STRIPE NOT CONFIGURED] Set STRIPE_SECRET_KEY to enable subscriptions")
        return ""

    client = _get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")

    pkg = client.get("package") or "security"
    price_info = PACKAGES.get(pkg, PACKAGES["security"])
    monthly_cents = int(price_info["monthly"] * 100)
    price_id = os.environ.get("STRIPE_PRICE_MONTHLY")

    customer = _stripe.Customer.create(
        email=customer_email,
        name=client["name"],
        metadata={"client_id": str(client_id)},
    )

    if price_id:
        sub = _stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            metadata={"client_id": str(client_id)},
        )
    else:
        price = _stripe.Price.create(
            unit_amount=monthly_cents,
            currency="usd",
            recurring={"interval": "month"},
            product_data={"name": f"{price_info['label']} Monthly Retainer"},
        )
        sub = _stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price.id}],
            metadata={"client_id": str(client_id)},
        )

    with _db() as conn:
        conn.execute(
            "UPDATE clients SET stripe_customer_id = ?, stripe_sub_id = ? WHERE id = ?",
            (customer.id, sub.id, client_id),
        )
        conn.commit()

    print(f"[STRIPE] Subscription created for {client['name']} — {sub.id}")
    print(f"[STRIPE] First charge: ${price_info['monthly']:.2f}/month")
    return sub.id


def charge_monthly_retainer(client_id: int) -> bool:
    """
    Charge monthly retainer via Stripe Invoice API (creates + finalizes invoice).
    Falls back to logging only if Stripe unavailable.
    """
    client = _get_client(client_id)
    if not client:
        return False

    pkg = client.get("package") or "security"
    price_info = PACKAGES.get(pkg, PACKAGES["security"])
    amount = price_info["monthly"]

    if not STRIPE_OK:
        print(f"[OFFLINE] Logged ${amount:.2f} retainer for {client['name']} (Stripe not configured)")
        _log_payment(client_id, amount, "manual", "Monthly retainer — manual log")
        return True

    customer_id = client.get("stripe_customer_id")
    if not customer_id:
        print(f"[WARN] {client['name']} has no Stripe customer ID — run `subscribe` first")
        return False

    invoice = _stripe.Invoice.create(
        customer=customer_id,
        auto_advance=True,
        description=f"Monthly retainer — {datetime.now().strftime('%B %Y')}",
    )
    _stripe.InvoiceItem.create(
        customer=customer_id,
        amount=int(amount * 100),
        currency="usd",
        description=f"{price_info['label']} — Monthly Security Services",
        invoice=invoice.id,
    )
    finalized = _stripe.Invoice.finalize_invoice(invoice.id)
    paid = _stripe.Invoice.pay(finalized.id)

    _log_payment(client_id, amount, "stripe_invoice", f"Invoice {paid.id}")
    print(f"[STRIPE] Charged ${amount:.2f} for {client['name']} — Invoice {paid.id}")
    return True


def bill_all_active():
    """Charge monthly retainer for every active client."""
    clients = _active_clients()
    print(f"\nBilling {len(clients)} active clients...")
    success = 0
    for c in clients:
        ok = charge_monthly_retainer(c["id"])
        if ok:
            success += 1
    print(f"\nBilling complete: {success}/{len(clients)} charged")


# =============================================================================
# PDF INVOICE
# =============================================================================

def generate_invoice_pdf(client_id: int) -> bytes:
    """Generate a PDF invoice. Returns raw bytes."""
    client = _get_client(client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")

    pkg = client.get("package") or "security"
    price_info = PACKAGES.get(pkg, PACKAGES["security"])
    invoice_num = f"INV-{client_id:04d}-{datetime.now().strftime('%Y%m')}"
    due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    if not REPORTLAB_OK:
        # Plain-text invoice fallback
        txt = f"""
OMNIMIND SECURITY SERVICES
Invoice #{invoice_num}
Date: {datetime.now().strftime('%Y-%m-%d')}
Due:  {due_date}

Bill To:
  {client['name']}
  {client['domain']}
  {client.get('email', '')}

Services:
  {price_info['label']} — Monthly Retainer    ${price_info['monthly']:.2f}

Total Due: ${price_info['monthly']:.2f}

Payment: Reply to this email or use your Stripe payment link.
Thank you for your business.

OmniMind Security
https://omnimind.security
"""
        return txt.encode()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>OMNIMIND SECURITY SERVICES</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Invoice #{invoice_num}", styles["Heading2"]))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}    Due: {due_date}", styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Bill To</b>", styles["Heading3"]))
    story.append(Paragraph(client["name"], styles["Normal"]))
    story.append(Paragraph(client["domain"], styles["Normal"]))
    if client.get("email"):
        story.append(Paragraph(client["email"], styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Services</b>", styles["Heading3"]))
    table_data = [
        ["Description", "Amount"],
        [f"{price_info['label']} — Monthly Retainer", f"${price_info['monthly']:.2f}"],
        ["Security scanning, monitoring & reporting", ""],
        ["", ""],
        ["TOTAL DUE", f"${price_info['monthly']:.2f}"],
    ]
    t = Table(table_data, colWidths=[380, 100])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE",  (0, -1), (-1, -1), 1, colors.black),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f0f0f0")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 30))

    story.append(Paragraph("Payment due within 7 days. Thank you for your business.", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<i>OmniMind Security — https://omnimind.security</i>", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def save_invoice(client_id: int) -> str:
    """Save invoice PDF to ./invoices/ and return path."""
    pdf = generate_invoice_pdf(client_id)
    out_dir = Path("./invoices")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m")
    ext = "pdf" if REPORTLAB_OK else "txt"
    path = out_dir / f"invoice_{client_id:04d}_{stamp}.{ext}"
    path.write_bytes(pdf)
    print(f"[INVOICE] Saved: {path}")
    return str(path)


# =============================================================================
# SMTP EMAIL
# =============================================================================

def send_invoice_email(client_id: int) -> bool:
    """Email the latest invoice PDF to the client."""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    client = _get_client(client_id)
    if not client:
        return False

    to_email = client.get("email")
    if not to_email:
        print(f"[EMAIL] No email on file for {client['name']}")
        return False

    if not smtp_user or not smtp_pass:
        print("[EMAIL] Set SMTP_USER and SMTP_PASS to enable email delivery")
        print(f"[EMAIL] Would send invoice to: {to_email}")
        return False

    pkg = client.get("package") or "security"
    price_info = PACKAGES.get(pkg, PACKAGES["security"])
    invoice_bytes = generate_invoice_pdf(client_id)
    ext = "pdf" if REPORTLAB_OK else "txt"
    invoice_name = f"omnimind_invoice_{datetime.now().strftime('%Y%m')}.{ext}"

    msg = MIMEMultipart()
    msg["From"]    = smtp_from
    msg["To"]      = to_email
    msg["Subject"] = f"OmniMind Security Invoice — {datetime.now().strftime('%B %Y')}"

    body = f"""Hi {client['name'].split()[0]},

Please find your monthly security services invoice attached.

Services this month:
  ✓ Continuous vulnerability monitoring
  ✓ Weekly automated scan reports
  ✓ Critical alert notifications
  ✓ Security advisory support

Amount Due: ${price_info['monthly']:.2f}
Due Date:   {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}

Questions? Reply to this email.

Thanks for trusting OmniMind Security.
"""
    msg.attach(MIMEText(body, "plain"))

    part = MIMEApplication(invoice_bytes, Name=invoice_name)
    part["Content-Disposition"] = f'attachment; filename="{invoice_name}"'
    msg.attach(part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[EMAIL] Invoice sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")
        return False


# =============================================================================
# MRR DASHBOARD
# =============================================================================

def mrr_dashboard():
    """Print MRR breakdown, per-client revenue, and $8K goal tracker."""
    clients = _active_clients()

    mrr = 0.0
    rows = []
    for c in clients:
        pkg = c.get("package") or "security"
        price_info = PACKAGES.get(pkg, PACKAGES["security"])
        m = price_info["monthly"]
        mrr += m
        rows.append((c["name"], pkg, m))

    needed = max(0, TARGET_MRR - mrr)
    pct = min(100, (mrr / TARGET_MRR) * 100)
    bar_len = 40
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"\n{'═'*60}")
    print(f"  OMNIMIND MRR DASHBOARD — {datetime.now().strftime('%B %Y')}")
    print(f"{'═'*60}")
    print()

    if rows:
        print(f"  {'Client':<30} {'Package':<12} {'MRR':>8}")
        print(f"  {'─'*30} {'─'*12} {'─'*8}")
        for name, pkg, m in rows:
            print(f"  {name:<30} {pkg:<12} ${m:>7.2f}")
        print(f"  {'─'*50}")
    else:
        print("  No active clients yet.")
    print()

    print(f"  Current MRR  : ${mrr:>8.2f}")
    print(f"  Target MRR   : ${TARGET_MRR:>8.2f}")
    print(f"  Gap to close : ${needed:>8.2f}")
    print()
    print(f"  [{bar}] {pct:.0f}%")
    print()

    if needed > 0:
        cheapest = PACKAGES["starter"]["monthly"]
        clients_needed = -(-int(needed // cheapest), 1)[int(needed // cheapest) == 0]
        print(f"  To hit $8K: +{clients_needed} more client(s) on Starter (${cheapest}/mo)")
        print(f"              or +{int(needed // PACKAGES['security']['monthly'])+1} on Security (${PACKAGES['security']['monthly']}/mo)")
    else:
        print(f"  TARGET REACHED. Scale to ${TARGET_MRR * 2:,.0f}?")

    # 90-day annualized projection
    arr = mrr * 12
    print(f"\n  ARR (annualized): ${arr:,.2f}")
    print(f"{'═'*60}\n")


# =============================================================================
# CLI
# =============================================================================

def _ensure_billing_columns():
    """Add Stripe columns to clients table if not present."""
    with _db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
        if "stripe_customer_id" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN stripe_customer_id TEXT")
        if "stripe_sub_id" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN stripe_sub_id TEXT")
        conn.commit()


def main():
    _ensure_billing_columns()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "link":
        cid = int(sys.argv[2])
        url = create_payment_link(cid)
        print(f"\nSend this link to your client:\n  {url}")

    elif cmd == "subscribe":
        cid = int(sys.argv[2])
        email = sys.argv[3] if len(sys.argv) > 3 else None
        if not email:
            c = _get_client(cid)
            email = c.get("email") if c else None
        if not email:
            print("Usage: subscribe <client_id> <email>")
            sys.exit(1)
        create_subscription(cid, email)

    elif cmd == "charge":
        cid = int(sys.argv[2])
        charge_monthly_retainer(cid)

    elif cmd == "invoice":
        cid = int(sys.argv[2])
        path = save_invoice(cid)
        print(f"Invoice: {path}")

    elif cmd == "email":
        cid = int(sys.argv[2])
        send_invoice_email(cid)

    elif cmd == "bill":
        bill_all_active()

    elif cmd == "mrr":
        mrr_dashboard()

    else:
        print(f"Unknown command: {cmd}")
        print("Run with no args for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
