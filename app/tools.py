"""Calls from the UI to the MCP server's tools (policy documents and customer data).

The UI uses the same tools as the agents, so there is one path to the data. Each function
returns plain Python values and raises ToolError with a readable message when a tool fails.
"""
import base64
import json

import streamlit as st

from agents.mcp_client import load_tools
from app.runtime import run_async, start_mcp_server

_ERROR_PREFIX = "Error executing tool"


class ToolError(Exception):
    """A tool call failed; the message is written for the user."""


@st.cache_resource(show_spinner=False)
def _tools() -> dict:
    start_mcp_server()
    names = {"list_policy_documents", "ingest_policy_document", "delete_policy_document",
             "list_customers", "get_customer_profile", "get_customer_tickets"}
    return {t.name: t for t in run_async(load_tools(names))}


def _call(name: str, **args) -> list:
    """Call a tool and return its result as a list of decoded values (an empty list for no results)."""
    blocks = run_async(_tools()[name].ainvoke(args))
    if isinstance(blocks, str):
        blocks = [{"text": blocks}]
    values = []
    for block in blocks or []:
        text = block["text"] if isinstance(block, dict) else str(block)
        if text.startswith(_ERROR_PREFIX):
            raise ToolError(text.split(": ", 1)[-1])
        values.append(json.loads(text))
    return values


def list_documents() -> list[dict]:
    """Documents in the knowledge base: source, chunks, uploaded_at."""
    return _call("list_policy_documents")


def upload_document(filename: str, content: bytes) -> dict:
    """Add a PDF. Returns filename, chunks, replaced, skipped."""
    return _call("ingest_policy_document", filename=filename,
                 content_base64=base64.b64encode(content).decode())[0]


def delete_document(filename: str) -> dict:
    """Remove a document. Returns found and deleted_chunks."""
    return _call("delete_policy_document", filename=filename)[0]


def list_customers() -> list[dict]:
    """All customers with plan, status and ticket counts (there are only a few dozen)."""
    return _call("list_customers", limit=500)


def get_profile(customer_id: int) -> dict:
    """One customer's full profile, including a ticket summary."""
    return _call("get_customer_profile", customer_id=customer_id)[0]


def get_tickets(customer_id: int) -> list[dict]:
    """A customer's tickets, newest first."""
    return _call("get_customer_tickets", customer_id=customer_id)
