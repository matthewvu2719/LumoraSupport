-- Fictional company: Lumora, a subscription SaaS (project management software).

DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    email          TEXT UNIQUE NOT NULL,
    phone          TEXT,
    country        TEXT,
    plan           TEXT NOT NULL CHECK (plan IN ('Free','Starter','Pro','Enterprise')),
    billing_cycle  TEXT CHECK (billing_cycle IN ('monthly','annual')),  -- NULL for Free
    status         TEXT NOT NULL CHECK (status IN ('active','cancelled','past_due')),
    signup_date    DATE NOT NULL,
    cancelled_date DATE                                                 -- set when status = 'cancelled'
);

CREATE TABLE tickets (
    ticket_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    subject       TEXT NOT NULL,
    description   TEXT,
    category      TEXT NOT NULL CHECK (category IN ('billing','refund','cancellation','technical','account','other')),
    priority      TEXT NOT NULL CHECK (priority IN ('low','medium','high','urgent')),
    status        TEXT NOT NULL CHECK (status IN ('open','in_progress','resolved','closed')),
    created_at    DATETIME NOT NULL,
    resolved_at   DATETIME,
    resolution    TEXT
);

CREATE INDEX idx_tickets_customer ON tickets(customer_id);
CREATE INDEX idx_customers_name ON customers(last_name, first_name);
