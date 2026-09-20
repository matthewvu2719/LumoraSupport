"""CSS for the chat drawer that slides in from the right edge of the page.

Streamlit has no drawer component, so the chat lives in a keyed container (`st.container(key=...)`
gets a `st-key-<key>` CSS class) that is fixed to the right edge and moved off-screen when closed.
"""
import streamlit as st


def _is_dark() -> bool:
    try:
        return st.context.theme.type != "light"
    except Exception:  # older Streamlit, or theme not reported: assume the common dark default
        return True


def chat_drawer_css(is_open: bool) -> str:
    dark = _is_dark()
    background = "#0e1117" if dark else "#ffffff"
    edge = "rgba(250, 250, 250, 0.18)" if dark else "rgba(49, 51, 63, 0.2)"
    shadow = "rgba(0, 0, 0, 0.55)" if dark else "rgba(0, 0, 0, 0.25)"
    transform = "translateX(0)" if is_open else "translateX(105%)"
    visibility = "visible" if is_open else "hidden"
    # When closing, keep the drawer visible until the slide-out has finished.
    visibility_delay = "0s" if is_open else "0.3s"
    return f"""
<style>
.st-key-chat_toggle {{
    position: fixed;
    right: 1.5rem;
    bottom: 1.5rem;
    width: auto;
    z-index: 990;
}}
.st-key-chat_drawer {{
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: clamp(420px, 50vw, 900px);
    max-width: 96vw;
    z-index: 1000;
    box-sizing: border-box;
    padding: 1.25rem 1.5rem 1.25rem 1.5rem;
    background: {background};
    border-left: 1px solid {edge};
    box-shadow: -14px 0 36px {shadow};
    overflow: hidden;
    transform: {transform};
    visibility: {visibility};
    transition: transform 0.3s ease, visibility 0s linear {visibility_delay};
}}
/* Streamlit wraps a keyed container in an extra layout wrapper: that wrapper is the flex item that must
   take up the space between the header and the input, and the messages scroll inside it. */
.st-key-chat_drawer > div:has(> .st-key-chat_messages) {{
    flex: 1 1 0;
    min-height: 0;
}}
.st-key-chat_messages {{
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    padding-right: 0.5rem;
}}
.st-key-chat_messages table {{
    display: block;
    overflow-x: auto;
}}
</style>
"""
