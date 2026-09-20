"""Settings shared by the agents: the OpenAI model and where the MCP server runs."""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Chat model for all agents. Override with OPENAI_MODEL in .env.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# The MCP server runs as one long-lived process (started on demand, see mcp_client.py).
MCP_HOST = "127.0.0.1"
MCP_PORT = int(os.getenv("MCP_PORT", "8765"))
MCP_URL = f"http://{MCP_HOST}:{MCP_PORT}/mcp"


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """The chat model. Temperature 0 keeps answers consistent, which suits data lookups."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to the .env file in the project folder.")
    return ChatOpenAI(model=OPENAI_MODEL, temperature=temperature)


# The customer database is a snapshot as of this date, so "recent", "overdue" etc. are judged from it.
DATA_AS_OF = "2026-09-15"
