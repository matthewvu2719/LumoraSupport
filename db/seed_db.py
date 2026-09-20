"""Seed data/customers.db with synthetic data for Lumora, a fictional subscription SaaS."""
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

random.seed(42)
fake = Faker()
Faker.seed(42)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "customers.db"
SCHEMA = Path(__file__).with_name("schema.sql").read_text()

N_CUSTOMERS = 59
AS_OF = datetime(2026, 9, 15)  # fixed "today" so the seed is reproducible

# (subject, description, resolution used once the ticket is resolved/closed)
TICKET_TEMPLATES = {
    "billing": [
        ("Charged twice this month", "Customer sees a duplicate subscription charge on their statement.",
         "Duplicate charge reversed."),
        ("Invoice not received", "Customer did not receive the monthly invoice by email.",
         "Invoice re-sent and email preferences corrected."),
        ("Update payment method", "Card expired and the renewal payment failed.",
         "Customer updated the card and the payment succeeded."),
    ],
    "refund": [
        ("Refund request for annual plan", "Customer wants a refund shortly after an annual renewal.",
         "Refund approved and processed to the original payment method."),
        ("Refund not yet received", "Refund was approved but has not reached the customer.",
         "Confirmed with the payment provider; funds arrived within 5 business days."),
        ("Refund request outside window", "Customer requests a refund several weeks after being charged.",
         "Refund declined per the refund policy; offered account credit instead."),
    ],
    "cancellation": [
        ("Cancel my subscription", "Customer wants to cancel before the next billing date.",
         "Subscription cancelled; access continues until the end of the billing period."),
        ("Downgrade to a lower plan", "Customer wants to move to a cheaper tier.",
         "Plan downgraded effective next billing cycle."),
    ],
    "technical": [
        ("Cannot log in", "Login fails with an invalid credentials error.",
         "Password reset and session cleared; login restored."),
        ("Export to PDF fails", "The app errors out when exporting a project report.",
         "Fixed in the latest release."),
        ("Integration with Slack stopped syncing", "Task notifications no longer reach Slack.",
         "Integration re-authorized; syncing restored."),
    ],
    "account": [
        ("Change account email", "Customer wants to update their registered email.",
         "Email updated after identity verification."),
        ("Add team members", "Customer needs more seats on their plan.",
         "Seats added and prorated on the next invoice."),
        ("Delete my account and data", "Customer requests account and data deletion.",
         "Deletion request completed per the privacy policy."),
    ],
    "other": [
        ("Feature request: Gantt view", "Customer would like a Gantt chart view.",
         "Logged with the product team."),
        ("General question about plans", "Customer asked about differences between plans.",
         "Sent plan comparison details."),
    ],
}

# Hand-crafted customers, so demos and evaluation questions have known answers.
# (first, last, email, phone, country, plan, billing_cycle, status, signup, cancelled)
DEMO_CUSTOMERS = [
    ("Ema", "Watson", "ema.watson@example.com", "+1-415-555-0142", "United States",
     "Pro", "annual", "active", date(2026, 9, 7), None),
    ("John", "Smith", "john.smith@example.com", "+44-20-5550-0119", "United Kingdom",
     "Starter", "monthly", "active", date(2025, 6, 3), None),
]

# customer email -> [(subject, description, category, priority, status, created_at, resolved_at, resolution)]
DEMO_TICKETS = {
    # Bought an annual Pro plan on 2026-09-07 and asks for a refund 6 days later (inside a typical 14-day window).
    "ema.watson@example.com": [
        ("Refund request for annual plan",
         "Customer purchased the annual Pro plan on 7 Sep and wants a full refund because it does not fit their workflow.",
         "refund", "high", "open", datetime(2026, 9, 13, 10, 24), None, None),
        ("Cannot invite team members",
         "Invitation emails to teammates are not being delivered.",
         "technical", "medium", "resolved", datetime(2026, 9, 9, 14, 5), datetime(2026, 9, 10, 9, 30),
         "Emails were caught by the customer spam filter; whitelisted the sender domain."),
    ],
    "john.smith@example.com": [
        ("Cancel my subscription",
         "Customer wants to cancel before the next billing date.",
         "cancellation", "medium", "open", datetime(2026, 9, 14, 13, 45), None, None),
    ],
}

INSERT_CUSTOMER = """INSERT INTO customers
    (first_name, last_name, email, phone, country, plan, billing_cycle, status, signup_date, cancelled_date)
    VALUES (?,?,?,?,?,?,?,?,?,?)"""
INSERT_TICKET = """INSERT INTO tickets
    (customer_id, subject, description, category, priority, status, created_at, resolved_at, resolution)
    VALUES (?,?,?,?,?,?,?,?,?)"""


def iso(d):
    """ISO string for a date/datetime, or None."""
    if d is None:
        return None
    return d.isoformat(timespec="seconds") if isinstance(d, datetime) else d.isoformat()


def random_customer(i):
    first, last = fake.first_name(), fake.last_name()
    plan = random.choices(["Free", "Starter", "Pro", "Enterprise"], [3, 4, 3, 1])[0]
    cycle = None if plan == "Free" else random.choice(["monthly", "annual"])
    status = random.choices(["active", "cancelled", "past_due"], [8, 1.5, 1])[0]
    signup = fake.date_between(start_date=AS_OF - timedelta(days=3 * 365), end_date=AS_OF - timedelta(days=30))
    cancelled = None
    if status == "cancelled":
        cancelled = fake.date_between(start_date=signup + timedelta(days=15), end_date=AS_OF)
    email = f"{first}.{last}{i}@{fake.free_email_domain()}".lower()
    return (first, last, email, fake.phone_number(), fake.country(), plan, cycle, status, signup, cancelled)


def random_tickets(cid, signup):
    signup_dt = datetime.combine(signup, datetime.min.time())
    for _ in range(random.randint(0, 6)):
        category = random.choice(list(TICKET_TEMPLATES))
        subject, desc, resolution = random.choice(TICKET_TEMPLATES[category])
        created = fake.date_time_between(start_date=signup_dt, end_date=AS_OF)
        status = random.choices(["open", "in_progress", "resolved", "closed"], [2, 2, 3, 3])[0]
        done = status in ("resolved", "closed")
        resolved_at = min(created + timedelta(days=random.randint(1, 10)), AS_OF) if done else None
        priority = random.choices(["low", "medium", "high", "urgent"], [3, 4, 2, 1])[0]
        yield (cid, subject, desc, category, priority, status, iso(created), iso(resolved_at),
               resolution if done else None)


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    customers = list(DEMO_CUSTOMERS)
    customers += [random_customer(i) for i in range(len(customers) + 1, N_CUSTOMERS + 1)]
    for c in customers:
        cur.execute(INSERT_CUSTOMER, (*c[:8], iso(c[8]), iso(c[9])))

    for cid, signup_str, email in cur.execute(
            "SELECT customer_id, signup_date, email FROM customers").fetchall():
        if email in DEMO_TICKETS:
            for subject, desc, cat, prio, status, created, resolved, resolution in DEMO_TICKETS[email]:
                cur.execute(INSERT_TICKET, (cid, subject, desc, cat, prio, status,
                                            iso(created), iso(resolved), resolution))
        else:
            for t in random_tickets(cid, date.fromisoformat(signup_str)):
                cur.execute(INSERT_TICKET, t)

    conn.commit()
    n_c = cur.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    n_t = cur.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    print(f"Seeded {n_c} customers and {n_t} tickets -> {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
