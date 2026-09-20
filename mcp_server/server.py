"""MCP server for the Lumora support assistant.

Exposes the customer database (read-only) and the policy knowledge base as tools that the
agents (and the UI) call. Nothing else in the project touches the databases directly.

Run:  python -m mcp_server.server                      # stdio: the client starts it as a subprocess
      python -m mcp_server.server --transport http     # HTTP on http://127.0.0.1:8000/mcp
"""
import argparse
import logging
import sys

from mcp.server.fastmcp import FastMCP

from ingestion.config import DEFAULT_TOP_K
from mcp_server import policy_tools, sql_tools

mcp = FastMCP(
    "lumora-support",
    instructions=(
        "Tools for Lumora customer support. Customer and ticket tools read a SQL database; "
        "policy tools search company policy documents (refund, cancellation, privacy, terms). "
        "All customer data is read-only."
    ),
    log_level="WARNING",  # keep the server quiet; stdio clients show its stderr
)


# --------------------------------------------------------------------------- customers (SQL)

@mcp.tool()
def search_customers(query: str, limit: int = 10) -> list[dict]:
    """Find customers by name or email. Use this first whenever the user names a customer.

    Every word in `query` must match the start of the first name, last name or email
    (case-insensitive). Returns customer_id, name, email, plan and status for each match.
    Several customers can share a first name: when more than one matches, treat all of
    them as relevant instead of picking one. An empty list means no such customer.
    """
    return sql_tools.search_customers(query, limit)


@mcp.tool()
def get_customer_profile(customer_id: int) -> dict:
    """Get a customer's full profile: contact details, country, plan (Free/Starter/Pro/Enterprise),
    billing_cycle (monthly/annual), status (active/cancelled/past_due), signup_date and
    cancelled_date, plus a ticket_summary with the total and counts by status.
    """
    profile = sql_tools.get_customer_profile(customer_id)
    if profile is None:
        raise ValueError(f"No customer with ID {customer_id}. Use search_customers to find the right ID.")
    return profile


@mcp.tool()
def get_customer_tickets(
    customer_id: int,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get a customer's support tickets, newest first.

    Optional filters: status and category (billing, refund, cancellation, technical, account,
    other). status is one of open, in_progress, resolved, closed, or "unresolved", which
    means open and in_progress together (use it for anything not finished yet). Omit status
    to get all tickets. Each ticket has ticket_id, subject, description, category, priority
    (low/medium/high/urgent), status, created_at, resolved_at and resolution.
    """
    return sql_tools.get_customer_tickets(customer_id, status, category, limit)


@mcp.tool()
def list_customers(
    limit: int = 50,
    offset: int = 0,
    plan: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List customers alphabetically by last name, with total_tickets and active_tickets
    (open + in_progress) counts. Optional filters: plan (Free, Starter, Pro, Enterprise) and
    status (active, cancelled, past_due). Use limit and offset to page through results.
    """
    return sql_tools.list_customers(limit, offset, plan, status)


@mcp.tool()
def run_readonly_sql(query: str, max_rows: int = 100) -> dict:
    """Run one read-only SQL SELECT on the customer database. Use this only for questions
    the other customer tools cannot answer, such as counts or comparisons across customers.

    Database schema (SQLite):
      customers(customer_id, first_name, last_name, email, phone, country,
                plan['Free','Starter','Pro','Enterprise'], billing_cycle['monthly','annual',NULL],
                status['active','cancelled','past_due'], signup_date, cancelled_date)
      tickets(ticket_id, customer_id -> customers, subject, description,
              category['billing','refund','cancellation','technical','account','other'],
              priority['low','medium','high','urgent'],
              status['open','in_progress','resolved','closed'],
              created_at, resolved_at, resolution)
    Dates are ISO text (e.g. '2026-09-13T10:24:00'). Only a single SELECT (or WITH ... SELECT)
    is allowed; results are capped at 100 rows. Returns {columns, rows, truncated}. If the
    query errors, read the message and fix the query.
    """
    return sql_tools.run_readonly_sql(query, max_rows)


# ------------------------------------------------------------------ policies (knowledge base)

@mcp.tool()
def search_policies(query: str, k: int = DEFAULT_TOP_K, source: str | None = None) -> list[dict]:
    """Search the company policy documents (refund, cancellation, privacy, terms of service, and
    any uploaded documents) for passages relevant to `query`.

    Returns passages best first, each with text, a citation (document, page, section) and a
    similarity score. Quote the citation when answering. An empty list means the documents
    do not cover the question: say so rather than guessing. If passages from different
    documents disagree, tell the user and name each document. `source` restricts the search
    to one document by file name.
    """
    return policy_tools.search_policies(query, k, source)


@mcp.tool()
def list_policy_documents() -> list[dict]:
    """List the policy documents currently in the knowledge base, with chunk counts and
    upload times."""
    return policy_tools.list_policy_documents()


@mcp.tool()
def ingest_policy_document(filename: str, content_base64: str) -> dict:
    """Add a policy PDF to the knowledge base. `content_base64` is the base64-encoded file.

    A file with the same name as an existing document replaces it; an identical file is
    skipped. Returns filename, chunks, replaced and skipped.
    """
    return policy_tools.ingest_policy_document(filename, content_base64)


@mcp.tool()
def delete_policy_document(filename: str) -> dict:
    """Remove a policy document and all its passages from the knowledge base. Returns
    found and deleted_chunks."""
    return policy_tools.delete_policy_document(filename)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lumora support MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    for noisy in ("httpx", "httpcore", "huggingface_hub", "sentence_transformers", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Load the embedding model and open the vector DB now, so the first search is not slow.
    # (stdio uses stdout for the protocol, so anything informational must go to stderr.)
    from ingestion.store import get_store
    get_store()
    print(f"lumora-support MCP server ready ({args.transport})", file=sys.stderr)

    if args.transport == "http":
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
