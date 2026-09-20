"""Chat drawer: a large panel that slides in from the right. Each question is answered on its own."""
import streamlit as st

from agents.supervisor import ask
from app.runtime import run_async
from app.styles import chat_drawer_css

EXAMPLES = (
    "Give me a quick overview of customer Ema Watson's profile and past support tickets.",
    "What is the current refund policy?",
)


def _show(exchange: dict) -> None:
    with st.chat_message("user"):
        st.markdown(exchange["question"])
    with st.chat_message("assistant"):
        st.markdown(exchange["answer"])
        if exchange["agents"]:
            st.caption("Answered by: " + " · ".join(exchange["agents"]))


def _set_open(value: bool) -> None:
    st.session_state.chat_open = value


def render_chat(supervisor) -> None:
    # The drawer is open when the page loads. `?chat=closed` starts it closed (handy for screenshots).
    st.session_state.setdefault("chat_open", st.query_params.get("chat") != "closed")
    is_open = st.session_state.chat_open
    st.markdown(chat_drawer_css(is_open), unsafe_allow_html=True)

    if not is_open:
        with st.container(key="chat_toggle"):
            st.button("Ask the assistant", icon=":material/chat:", type="primary",
                      on_click=_set_open, args=(True,))

    # The drawer is always rendered, so it can animate between its open and closed positions.
    with st.container(key="chat_drawer"):
        title, close = st.columns([5, 1], vertical_alignment="center")
        title.subheader("Ask the assistant")
        close.button("Close", icon=":material/close:", key="chat_close", on_click=_set_open, args=(False,),
                     width="stretch")

        messages = st.container(key="chat_messages")
        prompt = st.chat_input("Ask about a customer or a company policy...")

        with messages:
            if prompt:
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    try:
                        with st.spinner("Looking that up..."):
                            result = run_async(ask(supervisor, prompt))
                    except Exception as exc:  # network, rate limit, model errors: keep the app usable
                        st.error(f"Something went wrong, please try again. ({type(exc).__name__}: {exc})")
                        return
                # Keep the latest exchange so it stays on screen when the page re-runs.
                st.session_state.last = {"question": prompt, "answer": result["answer"], "agents": result["agents"]}
                st.rerun()
            elif "last" in st.session_state:
                _show(st.session_state.last)
            else:
                st.caption("Try asking, for example:")
                for example in EXAMPLES:
                    st.caption(f"• {example}")
