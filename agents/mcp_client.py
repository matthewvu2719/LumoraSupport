"""Connect the agents to the MCP server.

The server takes about 10 seconds to start (it loads the embedding model), and the adapter's
default stdio mode would start a new one for every tool call. So the server runs as a single
long-lived HTTP process instead: `ensure_server()` starts it if needed, and every tool call
is then a quick HTTP request.
"""
import atexit
import socket
import subprocess
import sys
import time

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agents.config import MCP_HOST, MCP_PORT, MCP_URL, ROOT

# Which tools each agent may use. Upload and delete are for the UI, not the agents.
SQL_TOOLS = {"search_customers", "get_customer_profile", "get_customer_tickets",
             "list_customers", "run_readonly_sql"}
POLICY_TOOLS = {"search_policies"}

_server_process: subprocess.Popen | None = None


def server_running() -> bool:
    try:
        with socket.create_connection((MCP_HOST, MCP_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_server(timeout: float = 120.0) -> None:
    """Start the MCP server in the background if it is not already running, and wait for it."""
    global _server_process
    if server_running():
        return
    log = open(ROOT / "data" / "mcp_server.log", "w")
    _server_process = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server", "--transport", "http",
         "--host", MCP_HOST, "--port", str(MCP_PORT)],
        cwd=ROOT, stdout=log, stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no console window on Windows
    )
    atexit.register(stop_server)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_process.poll() is not None:
            raise RuntimeError(f"MCP server exited during start-up. See {ROOT / 'data' / 'mcp_server.log'}")
        if server_running():
            return
        time.sleep(0.5)
    raise RuntimeError(f"MCP server did not start within {timeout:.0f}s. See {ROOT / 'data' / 'mcp_server.log'}")


def stop_server() -> None:
    """Stop the server if this process started it."""
    global _server_process
    if _server_process and _server_process.poll() is None:
        _server_process.terminate()
    _server_process = None


async def load_tools(names: set[str] | None = None) -> list[BaseTool]:
    """LangChain tools for the MCP server's tools (all of them, or just those in `names`)."""
    ensure_server()
    client = MultiServerMCPClient({"lumora": {"transport": "streamable_http", "url": MCP_URL}})
    tools = await client.get_tools()
    return [t for t in tools if names is None or t.name in names]
