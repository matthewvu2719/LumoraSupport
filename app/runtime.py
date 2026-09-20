"""Glue between Streamlit and the async agents.

Streamlit re-runs the script on every interaction and is synchronous, while the agents are async.
Everything async runs on one background event loop that lives as long as the app, so async clients
(HTTP connections to OpenAI and the MCP server) are never used from a closed loop.
"""
import asyncio
import threading

import streamlit as st

from agents.mcp_client import ensure_server
from agents.supervisor import build_supervisor


@st.cache_resource
def _event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True, name="agents-loop").start()
    return loop


def run_async(coro):
    """Run a coroutine on the background loop and wait for its result."""
    return asyncio.run_coroutine_threadsafe(coro, _event_loop()).result()


@st.cache_resource(show_spinner="Starting the MCP server (the first start takes about 15 seconds)...")
def start_mcp_server() -> bool:
    ensure_server()
    return True


@st.cache_resource(show_spinner="Loading the assistant...")
def get_supervisor():
    """The supervisor graph, built once per app process. Conversation memory lives inside it."""
    start_mcp_server()
    return run_async(build_supervisor())
