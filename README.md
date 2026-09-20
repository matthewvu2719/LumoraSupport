# Demo video
https://www.youtube.com/watch?v=ZuGce84Q5Vo

# Lumora Support Assistant

A Generative AI multi-agent system that lets a customer support executive ask questions in plain English about
two kinds of data:

- **Structured data**: customer profiles and support tickets, stored in a SQL database.
- **Unstructured data**: company policy PDFs, processed into a searchable vector knowledge base.

The user types a question in a chat panel. A supervisor agent decides whether the answer lives in the customer
data, the policy documents, or both, and returns a formatted answer with sources.

**Scenario:** the sample company is **Lumora**, a fictional subscription software company (Free, Starter, Pro and
Enterprise plans, billed monthly or annually). All customer and ticket data is synthetic. Policy PDFs are
public documents used as sample content.

---

## Features

- Ask about a customer: profile, plan, tickets ("Give me a quick overview of customer Ema's profile and past
  support ticket details").
- Ask about a policy: summary from the uploaded documents, with citations ("What is the current refund policy?").
- Upload, list, replace and delete policy PDFs from the app.
- Browse customers with search, and open a profile with its tickets.
- Hybrid questions that combine both ("Is Ema Watson's refund request within our refund window?").
- Safe by design: customer data is read-only, SQL is restricted to a single SELECT, answers come only from
  retrieved data, and unrelated or unsupported requests are declined.

---

## Architecture

```
Browser (displays the page)
   |  clicks, typing
   v
Streamlit process (port 8501)                        UI + agent orchestration in one Python process
 |- pages: customers, policy documents, chat drawer
 |- LangGraph supervisor
 |     |- router (one small LLM call) -> sql | policy | both | direct
 |     |- SQL agent      (tool-calling agent)  --+
 |     |- Policy agent   (tool-calling agent)  --+--> OpenAI API (chat model)
 |     '- synthesizer (merges answers for hybrid questions)
 |
 |  the pages and the agents both call tools through an MCP client
 v
MCP tools server on uvicorn (port 8765)              the only code that touches the data
 |- SQL tools    --> SQLite   (data/customers.db, opened read-only)
 '- policy tools --> Chroma    (data/chroma/) + local embedding model
```

### Data: structured vs. unstructured

| | Structured | Unstructured |
|---|---|---|
| Content | Customer profiles, support tickets | Policy PDFs (refund, privacy, terms, ...) |
| Storage | SQLite (`data/customers.db`) | Chroma vector DB (`data/chroma/`) |
| Query method | SQL (exact filters, joins) | Semantic similarity search |
| Loaded | Seeded once by a script, then read-only | Ingested when a PDF is added (upload or script) |

### How a PDF becomes a searchable knowledge base

1. **Extract** the text page by page (`pypdf`), keeping page numbers.
2. **Clean** it: remove page numbers and repeated headers/footers (documents of 3+ pages), rejoin wrapped lines.
3. **Chunk** it (about 800 characters, 120 overlap), keeping sections together where headings are numbered.
4. **Attach metadata** to each chunk: source file, page, section, chunk index, file hash, upload time.
5. **Embed** each chunk with a local model (`all-MiniLM-L6-v2`, no API key needed).
6. **Store** vectors and metadata in Chroma.

At question time the query is embedded, the closest chunks are retrieved, and the policy agent answers only from
them, citing document and page.

### Design decisions

- **All data access goes through an MCP server.** Agents and the UI call tools by name; nothing else touches the
  databases. The server runs over streamable HTTP on uvicorn (started by the MCP SDK) with a single `/mcp`
  endpoint. It is one long-lived process, because starting a new one per tool call takes about 10 seconds.
- **Supervisor pattern.** A router picks the specialist (or both), and a synthesizer merges results for hybrid
  questions. The SQL agent and policy agent are tool-calling agents with their own prompts and tool sets.
- **Safe SQL.** Specific tools (`get_customer_profile`, `get_customer_tickets`, ...) are preferred. A fallback
  `run_readonly_sql` tool allows one SELECT only, on a read-only connection, with an authorizer that denies
  everything except reading, a row cap and a run-time limit.
- **Grounded answers.** The policy agent answers only from retrieved passages, cites them, says so when nothing
  relevant is found (similarity below 0.30), and names each document when documents disagree.
- **Multiple matches.** If a name matches several customers, all of them are shown instead of guessing.
- **Ticket status.** "Open", "unresolved", "pending" and "still active" all mean open plus in-progress tickets
  (the tickets tool has an `unresolved` status for this).
- **Document management.** A file with the same name as an existing document replaces it; an identical file is
  skipped; a different name is added alongside, and answers cite the document they come from.
- **No conversation memory.** Every question is answered on its own.

### Technology stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph, LangChain (`create_agent`) |
| LLM | OpenAI chat model (default `gpt-4o-mini`) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2`, local |
| SQL database | SQLite |
| Vector database | Chroma (embedded, on disk) |
| Tool server | MCP (official Python SDK, `FastMCP`) on uvicorn |
| MCP client | `langchain-mcp-adapters` |
| UI | Streamlit |

---

## Project structure

```
.
|- app/                     Streamlit UI
|   |- main.py              page layout and section switch
|   |- customers.py         customer table, search, profile card
|   |- documents.py         upload, list, delete policy documents
|   |- chat.py              slide-in chat panel
|   |- styles.py            CSS for the chat panel
|   |- runtime.py           glue between Streamlit and the async agents
|   '- tools.py             calls from the UI to the MCP tools
|- agents/
|   |- config.py            model, ports, reference date
|   |- mcp_client.py        starts the MCP server if needed, loads tools
|   |- sql_agent.py         customer and ticket specialist
|   |- policy_agent.py      policy specialist
|   '- supervisor.py        router, specialists, synthesizer
|- mcp_server/
|   |- sql_tools.py         read-only customer queries and SELECT guard
|   |- policy_tools.py      policy search, upload, list, delete
|   '- server.py            FastMCP server exposing all tools
|- ingestion/
|   |- config.py            paths, embedding model, chunk size
|   |- extract.py           PDF text extraction and cleaning
|   |- chunk.py             section-aware chunking with metadata
|   |- store.py             embed and store in Chroma; ingest, replace, list, delete
|   |- search.py            similarity search with citations
|   |- ingest_seed.py       load every PDF in data/policies/ into the vector DB
|   '- check_retrieval.py   try searches against the vector DB
|- db/
|   |- schema.sql           customers and tickets tables
|   '- seed_db.py           synthetic data generator (Faker)
|- data/
|   |- customers.db         seeded SQL database (committed)
|   |- policies/            source policy PDFs
|   '- chroma/              vector database (generated, git-ignored)
|- tests/                   pytest tests (no API key or LLM needed)
|- .streamlit/config.toml   Streamlit settings (localhost only, upload limit)
|- .env.example             copy to .env and add your key
|- pytest.ini
'- requirements.txt
```

---

## Setup

Requires Python 3.11 or newer and an OpenAI API key.

```bash
# 1. clone and enter the project
git clone <repository-url>
cd <project-folder>

# 2. create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate

# 3. install dependencies (large download: it includes PyTorch for the local embedding model. Please wait until all downloads have finished before continuing to next step 5)
pip install -r requirements.txt

# 4. add your API key
copy .env.example .env            # macOS/Linux: cp .env.example .env
#    then edit .env and set OPENAI_API_KEY=...

# 5. build the knowledge base from the PDFs in data/policies/
python -m ingestion.ingest_seed

# 6. run the app
streamlit run app/main.py
```

Notes:

- `data/customers.db` is included in the repository, so the customer data needs no setup.
- `data/chroma/` is not included: step 5 builds it. It is safe to rerun (unchanged files are skipped).
- The first embedding run downloads the model (about 90 MB), once.
- The first page load takes about 15 to 20 seconds while the app starts the MCP tools server in the background.
  You do not need to start that server yourself.

### Configuration (optional, in `.env`)

| Setting | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | none | Required. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model used by the agents. |
| `MCP_PORT` | `8765` | Port of the local tools server. Change it if the port is taken. |

---

## Usage

Open `http://localhost:8501`. The page has two sections, selected at the top, and a chat panel on the right.

**Customers.** Search by name or email, select a row, and the profile card shows contact details, plan, status and
a ticket table (newest first). The "Unresolved" column counts open and in-progress tickets.

**Policy documents.** Upload a PDF, see the documents in the knowledge base (passage count and upload time), or
delete one (with a confirmation).

- Same file name as an existing document: replaced.
- Same file, unchanged: skipped.
- Different file name: added next to the others. If two documents disagree, the assistant names both.

**Chat.** The panel is open when the page loads; close it with "Close" and reopen it with "Ask the assistant".
Each answer says which specialist answered (SQL agent, Policy agent, or both).

Example questions:

| Question | Handled by |
|---|---|
| "Give me a quick overview of customer Ema's profile and past support ticket details." | SQL agent |
| "What is the current refund policy?" | Policy agent |
| "Which customers have an urgent ticket that is still open?" | SQL agent (aggregate query) |
| "Is Ema Watson's refund request within our refund window?" | Both (needs the sample refund policy) |
| "Give me John's profile" (two customers share the name) | SQL agent, shows every match |
| "What is the weather in Paris?" | Declined: out of scope |
| "Delete Ema Watson's refund ticket" | Declined: data is read-only |

### Data

- **Customers and tickets:** 59 synthetic customers and 162 tickets, generated by `db/seed_db.py` (Faker, fixed
  random seed). Two demo customers are hand-crafted: **Ema Watson** (Pro, annual, an open refund ticket raised 6
  days after signing up) and **John Smith** (Starter, monthly, an open cancellation ticket). The data is a
  snapshot as of **2026-09-15**. To regenerate it (this resets all data): `python db/seed_db.py`.
- **Policy documents:** any text-based (not scanned) public policy PDF. Put it in `data/policies/` and run
  `python -m ingestion.ingest_seed`, or upload it in the app.

### Try the search directly

```bash
python -m ingestion.check_retrieval "your question about the uploaded policy"
```

Each result shows a similarity score and its citation. Relevant matches usually score 0.5 to 0.8; results below
0.30 are treated as "not found".

### Tests

```bash
pytest
```

The tests cover PDF extraction and cleaning, chunking, the SQL tools and the SELECT-only guard, ingestion
(add, skip, replace, delete), search, and upload validation. They need no API key. They use a temporary database
and vector store, and the first run downloads the embedding model. The agents' answers vary between runs, so they
are checked with a list of evaluation questions instead of automated tests.

---

## Limitations and notes

- **`mcp` is pinned to `>=1.24,<2`.** `langchain-mcp-adapters` requires `mcp<2.0.0`, and version 2 renamed
  `FastMCP` to `MCPServer`, so the server uses the 1.x name.
- **Section names in citations need numbered headings** (for example "2. Refunds"). For PDFs with other heading
  styles, answers still work, but citations show only the document and page.
- **Scanned PDFs are not supported** (no OCR): the upload fails with a clear message.
- **No conversation memory:** a follow-up such as "and her open tickets?" is not understood on its own.
- **"Open" wording:** "how many open tickets" is sometimes read strictly (status open only), while "unresolved",
  "pending" and "still open" include in-progress tickets.
- **The tools server is local only:** it listens on `127.0.0.1` with no authentication or HTTPS. A real
  deployment would need authentication, HTTPS and shared storage.
- **Restart the app after code changes.** Streamlit can keep old versions of helper modules in memory.
- **Stale tools server:** if another copy of the project (or an earlier crash) left a tools server running on the
  same port, the app will silently use it and may show the wrong data. Stop that process or change `MCP_PORT`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "OPENAI_API_KEY is not set" | Create `.env` from `.env.example` and add your key. |
| First load takes a long time | Normal: the tools server and embedding model are starting. |
| "MCP server did not start" | Read `data/mcp_server.log`. Another program may be using the port: set `MCP_PORT`. |
| Old documents or customers appear | A stale tools server is running: stop it, or change `MCP_PORT`. |
| An upload is rejected | It must be a text-based PDF, under 10 MB, with a plain `.pdf` file name. |
| The chat answers "the documents do not cover this" | Nothing scored above 0.30. Check with `python -m ingestion.check_retrieval "..."`. |
