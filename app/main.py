"""Lumora support assistant: Streamlit UI.

Run:  streamlit run app/main.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `agents`, `ingestion` and `mcp_server` import when run by Streamlit

import streamlit as st  # noqa: E402

from agents import config  # noqa: E402,F401  (importing it loads the .env file)
from app.chat import render_chat  # noqa: E402
from app.customers import render_customers  # noqa: E402
from app.documents import render_documents  # noqa: E402
from app.runtime import get_supervisor, start_mcp_server  # noqa: E402

SECTIONS = ("Customers", "Policy documents")

st.set_page_config(page_title="Lumora Support Assistant", page_icon=":speech_balloon:", layout="wide",
                   initial_sidebar_state="collapsed")

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is not set. Add it to the `.env` file in the project folder and restart the app.")
    st.stop()

start_mcp_server()
supervisor = get_supervisor()

# `?section=documents` opens the Policy documents view on first load (handy for screenshots and demos).
if "section" not in st.session_state and st.query_params.get("section") == "documents":
    st.session_state.section = SECTIONS[1]

st.title("Lumora Support")
st.caption("Customer profiles, support tickets and company policies. Ask the assistant about any of them.")

section = st.segmented_control("Section", SECTIONS, default=SECTIONS[0], key="section",
                               label_visibility="collapsed") or SECTIONS[0]

if section == "Customers":
    render_customers()
else:
    render_documents()

render_chat(supervisor)  # the slide-in panel, fixed to the right edge of the page
