"""Read-only access to the customer/ticket SQLite database.

Everything here opens the database read-only, so nothing in the app can change customer data.
The MCP server exposes these functions as tools.
"""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "customers.db"

TICKET_STATUSES = ("open", "in_progress", "resolved", "closed")
UNRESOLVED = ("open", "in_progress")  # what "unresolved" means when used as a ticket status filter
TICKET_CATEGORIES = ("billing", "refund", "cancellation", "technical", "account", "other")
PLANS = ("Free", "Starter", "Pro", "Enterprise")
CUSTOMER_STATUSES = ("active", "cancelled", "past_due")

MAX_SQL_ROWS = 100
_MAX_VM_STEPS = 5_000_000  # abort runaway queries (each callback is 1000 SQLite VM steps)


@contextmanager
def _connect(db_path: Path = DB_PATH):
    """Open the database read-only and always close it afterwards."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _check(value: str | None, allowed: tuple[str, ...], label: str) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"Invalid {label} {value!r}. Allowed values: {', '.join(allowed)}")


def search_customers(query: str, limit: int = 10, db_path: Path = DB_PATH) -> list[dict]:
    """Find customers by name or email. Every word in `query` must match the start of the first
    name, last name or email (case-insensitive), so "ema" finds Ema Watson but not Jennifer
    Freeman. Returns every match: when several customers share a name (e.g. two named John), the
    caller shows all of them instead of guessing.
    """
    words = query.split()
    if not words:
        return []
    clauses = " AND ".join(
        "(first_name LIKE :w{i} OR last_name LIKE :w{i} OR email LIKE :w{i})".format(i=i)
        for i in range(len(words))
    )
    params = {f"w{i}": f"{w}%" for i, w in enumerate(words)}
    params["limit"] = limit
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT customer_id, first_name, last_name, email, plan, status
                FROM customers WHERE {clauses}
                ORDER BY last_name, first_name LIMIT :limit""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_customer_profile(customer_id: int, db_path: Path = DB_PATH) -> dict | None:
    """Full profile plus a summary of the customer's tickets. None if the ID does not exist."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
        if row is None:
            return None
        counts = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tickets WHERE customer_id = ? GROUP BY status",
            (customer_id,),
        ).fetchall()
    profile = dict(row)
    by_status = {r["status"]: r["n"] for r in counts}
    profile["ticket_summary"] = {"total": sum(by_status.values()), "by_status": by_status}
    return profile


def get_customer_tickets(
    customer_id: int,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """A customer's tickets, newest first, optionally filtered by status and/or category.

    status may be one of the four ticket statuses, or "unresolved" for open and in_progress together.
    """
    _check(status, TICKET_STATUSES + ("unresolved",), "status")
    _check(category, TICKET_CATEGORIES, "category")
    sql = "SELECT * FROM tickets WHERE customer_id = :cid"
    params: dict = {"cid": customer_id, "limit": limit}
    if status == "unresolved":
        sql += " AND status IN ('open', 'in_progress')"
    elif status:
        sql += " AND status = :status"
        params["status"] = status
    if category:
        sql += " AND category = :category"
        params["category"] = category
    sql += " ORDER BY created_at DESC LIMIT :limit"
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def list_customers(
    limit: int = 50,
    offset: int = 0,
    plan: str | None = None,
    status: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """A page of customers with ticket counts, for the customer browser in the UI."""
    _check(plan, PLANS, "plan")
    _check(status, CUSTOMER_STATUSES, "status")
    sql = """SELECT c.customer_id, c.first_name, c.last_name, c.email, c.plan, c.billing_cycle, c.status,
                    COUNT(t.ticket_id) AS total_tickets,
                    COALESCE(SUM(t.status IN ('open', 'in_progress')), 0) AS active_tickets
             FROM customers c LEFT JOIN tickets t ON t.customer_id = c.customer_id WHERE 1 = 1"""
    params: dict = {"limit": limit, "offset": offset}
    if plan:
        sql += " AND c.plan = :plan"
        params["plan"] = plan
    if status:
        sql += " AND c.status = :status"
        params["status"] = status
    sql += " GROUP BY c.customer_id ORDER BY c.last_name, c.first_name LIMIT :limit OFFSET :offset"
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def run_readonly_sql(query: str, max_rows: int = MAX_SQL_ROWS, db_path: Path = DB_PATH) -> dict:
    """Run a single SELECT statement and return {"columns", "rows", "truncated"}.

    Layers of protection: the connection is read-only, SQLite's authorizer denies everything
    except reading, only one statement is allowed, and the row count and run time are capped.
    Raises ValueError with a message the caller can show to the model so it can fix its query.
    """
    text = query.strip().rstrip(";").strip()
    if not text:
        raise ValueError("Empty query.")
    if ";" in text:
        raise ValueError("Only a single SQL statement is allowed.")
    if not re.match(r"(?is)^(select|with)\b", text):
        raise ValueError("Only SELECT queries are allowed.")
    max_rows = max(1, min(max_rows, MAX_SQL_ROWS))

    with _connect(db_path) as conn:
        conn.execute("PRAGMA query_only = ON")  # set before the authorizer, which denies PRAGMA
        conn.set_authorizer(_authorizer)
        steps = {"n": 0}

        def _limit_runtime() -> int:
            steps["n"] += 1
            return 1 if steps["n"] > _MAX_VM_STEPS // 1000 else 0  # non-zero aborts the query

        conn.set_progress_handler(_limit_runtime, 1000)
        try:
            cursor = conn.execute(text)
            fetched = cursor.fetchmany(max_rows + 1)
        except sqlite3.Error as exc:
            raise ValueError(f"SQL error: {exc}") from exc
        columns = [d[0] for d in cursor.description] if cursor.description else []
    return {
        "columns": columns,
        "rows": [dict(r) for r in fetched[:max_rows]],
        "truncated": len(fetched) > max_rows,
    }
