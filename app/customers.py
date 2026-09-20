"""Customer browser: see who exists, and open a customer's profile and tickets.

It shows the data the assistant works with, so John knows which customers he can ask about.
"""
import pandas as pd
import streamlit as st

from app import tools

# Customer data is a read-only snapshot, so results can be reused between page re-runs.
_CACHE_SECONDS = 300


@st.cache_data(ttl=_CACHE_SECONDS, show_spinner=False)
def _customers() -> list[dict]:
    return tools.list_customers()


@st.cache_data(ttl=_CACHE_SECONDS, show_spinner=False)
def _profile(customer_id: int) -> dict:
    return tools.get_profile(customer_id)


@st.cache_data(ttl=_CACHE_SECONDS, show_spinner=False)
def _tickets(customer_id: int) -> list[dict]:
    return tools.get_tickets(customer_id)


def _full_name(customer: dict) -> str:
    return f"{customer['first_name']} {customer['last_name']}"


def _matches(customer: dict, query: str) -> bool:
    """Every word typed must be the start of the first name, last name or email (like the assistant's search)."""
    fields = [customer["first_name"].lower(), customer["last_name"].lower(), customer["email"].lower()]
    return all(any(field.startswith(word) for field in fields) for word in query.lower().split())


def render_profile(customer_id: int) -> None:
    """A customer's profile and tickets."""
    try:
        profile = _profile(customer_id)
        tickets = _tickets(customer_id)
    except tools.ToolError as exc:
        st.error(f"Could not load this customer: {exc}")
        return

    with st.container(border=True):
        st.markdown(f"#### {_full_name(profile)}")
        left, right = st.columns(2)
        left.markdown(f"**Email:** {profile['email']}  \n**Phone:** {profile['phone']}  \n**Country:** {profile['country']}")
        cycle = profile["billing_cycle"] or "n/a"
        right.markdown(f"**Plan:** {profile['plan']} ({cycle})  \n**Status:** {profile['status']}  \n"
                       f"**Customer since:** {profile['signup_date']}")

        st.markdown(f"**Tickets** ({profile['ticket_summary']['total']})")
        if not tickets:
            st.caption("This customer has no support tickets.")
        else:
            table = pd.DataFrame(tickets)[["ticket_id", "subject", "category", "priority", "status", "created_at"]]
            table["created_at"] = table["created_at"].str[:10]
            table.columns = ["ID", "Subject", "Category", "Priority", "Status", "Created"]
            st.dataframe(table, hide_index=True, width="stretch")


def render_customers() -> None:
    try:
        customers = _customers()
    except tools.ToolError as exc:
        st.error(f"Could not load the customer list: {exc}")
        return

    # Everything is stacked in the left column (the table, then the selected customer's profile), so the
    # chat panel, which slides over the right side of the page, never covers it.
    left, _ = st.columns([9, 11], gap="large")

    with left:
        query = st.text_input("Search", placeholder="Search by name or email", label_visibility="collapsed")
        shown = [c for c in customers if _matches(c, query)] if query.strip() else customers
        if not shown:
            st.info("No customers match that search.")
            return

        table = pd.DataFrame([{
            "Name": _full_name(c), "Plan": c["plan"], "Status": c["status"], "Unresolved": c["active_tickets"],
        } for c in shown])
        st.caption(f"{len(shown)} of {len(customers)} customers. Select a row to see the profile and tickets.")
        height = min(35 * (len(table) + 1) + 3, 300)  # fit few results, scroll many
        event = st.dataframe(table, hide_index=True, width="stretch", height=height,
                             on_select="rerun", selection_mode="single-row", key="customer_table")

        selected = event.selection.rows
        if selected and selected[0] < len(shown):
            render_profile(shown[selected[0]]["customer_id"])
        else:
            st.caption("No customer selected.")
