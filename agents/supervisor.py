"""Supervisor: routes each question to the SQL agent, the policy agent, or both, and returns one answer.

    router ──sql──────► sql_agent ───────────────────────────► END
       │                    │ (hybrid, customer found)
       ├──both──► sql_agent ┴──► policy_agent ──► synthesize ──► END
       ├──policy──────────────► policy_agent ─────────────────► END
       └──direct (greeting / out of scope) ───────────────────► END

Every question is answered on its own: there is no memory of earlier questions.
"""
from typing import Annotated, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel
from typing_extensions import TypedDict

from agents.config import DATA_AS_OF, get_llm
from agents.policy_agent import build_policy_agent
from agents.sql_agent import build_sql_agent

NEEDS_INPUT = "NEEDS_INPUT:"  # the SQL agent starts a reply with this when it must ask the user something


class RoutePlan(BaseModel):
    route: Literal["sql", "policy", "both", "direct"]
    sql_question: str = ""
    policy_question: str = ""
    direct_reply: str = ""


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    route: str
    sql_question: str
    policy_question: str
    sql_answer: str
    needs_input: bool
    policy_answer: str


ROUTER_PROMPT = f"""You route messages for Lumora's customer support assistant. Lumora is a subscription \
software company. The assistant has two specialists:
- SQL specialist: customer profiles (plan, billing cycle, status, signup date, contact details) and support \
tickets (subject, category, priority, status, dates, resolution). It also answers counts and comparisons \
across customers.
- Policy specialist: the policy and company documents that users have uploaded. They can be about any \
topic (for example refunds, cancellation, privacy, terms of service, HR or employee handbooks, insurance, \
security), because users upload their own documents.

Today's date is {DATA_AS_OF}. Choose a route for the user's message:
- "sql": needs only customer or ticket data.
- "policy": needs what an uploaded document says, whatever its topic (company rules, procedures, coverage, \
terms, HR or insurance policies, handbooks), with no specific customer involved.
- "both": applies a policy to a specific customer's situation, for example eligibility for a refund, \
whether a customer is within a window, or what a rule means for a named customer's plan or ticket.
- "direct": greetings, thanks, questions about what the assistant can do, or clearly unrelated small talk \
and general knowledge (weather, sports, coding help). Also requests to change or delete customer data or \
tickets, and questions about uploading documents.
If a question could be answered by a company policy or document, even on a topic you would not expect from \
this company (insurance, vacation, dress code), use "policy": the policy specialist searches the uploaded \
documents and says when they do not cover it. When unsure between "direct" and "policy", choose "policy".
Never use "direct" for anything about a specific customer, ticket or policy. "Tell me about <a customer's \
name>" goes to "sql".
The one exception: if the message refers to a customer only by a pronoun or a vague phrase ("her", "he", \
"their", "that customer") without naming them, use "direct" and ask which customer they mean. Never guess \
a customer.

Each message is answered on its own, with no earlier conversation. Write the questions for the \
specialists so that they make sense on their own.
- sql_question (routes sql and both): what to look up. For "both", ask for the facts the policy depends on \
for that customer: plan, billing cycle, status, signup date and the relevant tickets with their dates and \
status.
- policy_question (routes policy and both): the policy question in general terms.
- direct_reply (route direct): a brief, friendly reply. Greet only if the user greeted you.
  - Unrelated question: say you can help with customer profiles, ticket history and company policies, \
and do not answer it.
  - Request to change or delete customer data or tickets: say you can only look information up and \
cannot change it. Do not suggest any other place to do it.
  - Question about uploading a policy document: say yes, policy PDFs are uploaded in the "Policy \
documents" section of the page, where existing documents can also be deleted or replaced.
Leave fields that do not apply empty."""


SYNTHESIZE_PROMPT = """You combine two specialists' findings into one answer for a customer support \
executive. Use only the findings below; do not add facts.

Structure:
1. One or two sentences with the direct answer to the question. If the findings cover more than one \
customer, give the answer for each of them.
2. "Customer" - the relevant customer facts, as short bullets. With several customers, one short group \
per customer.
3. "Policy" - the rule that applies and how it applies to this customer, with the date reasoning \
if dates matter, as short bullets.
4. "Sources" - the policy citations from the policy findings, unchanged.

Rules:
- Include every customer that appears in the findings. Never leave one out.
- If the policy findings say documents conflict, keep that and name the documents.
- If either specialist reports missing data (the customer was not found, the policy is not covered, a \
date is not in the data), say plainly what is missing and what that means for the answer.
- Do not add any date, number or fact that is not in the findings, and do not guess with words like \
"likely" or "probably".
- Keep it concise."""


def _text(message) -> str:
    content = message.content
    return content if isinstance(content, str) else " ".join(str(part) for part in content)


async def build_supervisor():
    """Build and compile the supervisor graph (loads both specialist agents)."""
    sql_agent = await build_sql_agent()
    policy_agent = await build_policy_agent()
    router_llm = get_llm().with_structured_output(RoutePlan)
    llm = get_llm()

    async def route_node(state: State) -> dict:
        messages = state["messages"]
        plan: RoutePlan = await router_llm.ainvoke([
            ("system", ROUTER_PROMPT),
            ("user", _text(messages[-1])),
        ])
        route = plan.route
        # Guard against a route with no question to hand over.
        if route in ("sql", "both") and not plan.sql_question:
            plan.sql_question = _text(messages[-1])
        if route in ("policy", "both") and not plan.policy_question:
            plan.policy_question = _text(messages[-1])
        return {"route": route, "sql_question": plan.sql_question, "policy_question": plan.policy_question,
                "sql_answer": "", "policy_answer": "", "needs_input": False,
                **({"messages": [AIMessage(content=plan.direct_reply or "How can I help with customers or policies?")]}
                   if route == "direct" else {})}

    async def sql_node(state: State) -> dict:
        result = await sql_agent.ainvoke({"messages": [("user", state["sql_question"])]})
        answer = _text(result["messages"][-1]).strip()
        needs_input = answer.startswith(NEEDS_INPUT)
        if needs_input:
            answer = answer[len(NEEDS_INPUT):].strip()
        update: dict = {"sql_answer": answer, "needs_input": needs_input}
        if state["route"] == "sql" or needs_input:  # nothing more to do: this is the reply
            update["messages"] = [AIMessage(content=answer)]
        return update

    async def policy_node(state: State) -> dict:
        question = state["policy_question"]
        if state["route"] == "both":
            question = (
                f"{question}\n\nFacts about the customer, from the customer database:\n{state['sql_answer']}\n\n"
                "Apply the policy to these facts. The database records the signup date but not payment or "
                "renewal dates: if the policy depends on the payment date, say which date you used and why "
                "(for example the plan started at signup), and if it cannot be determined, say so."
            )
        result = await policy_agent.ainvoke({"messages": [("user", question)]})
        answer = _text(result["messages"][-1]).strip()
        update: dict = {"policy_answer": answer}
        if state["route"] == "policy":
            update["messages"] = [AIMessage(content=answer)]
        return update

    async def synthesize_node(state: State) -> dict:
        question = _text(state["messages"][-1])
        reply = await llm.ainvoke([
            ("system", SYNTHESIZE_PROMPT),
            ("user", f"Question: {question}\n\nCustomer findings:\n{state['sql_answer']}\n\n"
                     f"Policy findings:\n{state['policy_answer']}"),
        ])
        return {"messages": [AIMessage(content=_text(reply).strip())]}

    def after_route(state: State) -> Literal["sql", "policy", "__end__"]:
        return {"sql": "sql", "both": "sql", "policy": "policy"}.get(state["route"], END)

    def after_sql(state: State) -> Literal["policy", "__end__"]:
        return "policy" if state["route"] == "both" and not state["needs_input"] else END

    def after_policy(state: State) -> Literal["synthesize", "__end__"]:
        return "synthesize" if state["route"] == "both" else END

    graph = StateGraph(State)
    graph.add_node("route", route_node)
    graph.add_node("sql", sql_node)
    graph.add_node("policy", policy_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", after_route, {"sql": "sql", "policy": "policy", END: END})
    graph.add_conditional_edges("sql", after_sql, {"policy": "policy", END: END})
    graph.add_conditional_edges("policy", after_policy, {"synthesize": "synthesize", END: END})
    graph.add_edge("synthesize", END)
    return graph.compile()


async def ask(supervisor, question: str) -> dict:
    """Send one question through the supervisor. Returns the answer plus which specialists ran."""
    state = await supervisor.ainvoke({"messages": [("user", question)]})
    route = state["route"]
    ran = {"sql": ["SQL agent"], "policy": ["Policy agent"], "direct": []}.get(route, ["SQL agent", "Policy agent"])
    if route == "both" and state.get("needs_input"):
        ran = ["SQL agent"]  # stopped to ask the user; the policy agent did not run
    return {"answer": _text(state["messages"][-1]), "route": route, "agents": ran,
            "sql_answer": state.get("sql_answer", ""), "policy_answer": state.get("policy_answer", "")}
