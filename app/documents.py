"""Policy documents view: upload, list and delete the documents the assistant answers from."""
from datetime import datetime

import streamlit as st

from app import tools


def _init_state() -> None:
    st.session_state.setdefault("uploader_n", 0)      # changing the uploader's key clears it
    st.session_state.setdefault("flash", [])          # messages to show once after an action
    st.session_state.setdefault("pending_delete", None)
    if "docs" not in st.session_state:
        st.session_state.docs = tools.list_documents()


def _refresh() -> None:
    st.session_state.docs = tools.list_documents()


def _flash(level: str, text: str) -> None:
    st.session_state.flash.append((level, text))


def _uploaded(when: str) -> str:
    try:
        return datetime.fromisoformat(when).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return when


def _handle_uploads(files) -> None:
    with st.spinner("Reading and indexing the document..."):
        for file in files:
            try:
                result = tools.upload_document(file.name, file.getvalue())
            except tools.ToolError as exc:
                _flash("error", f"{file.name}: {exc}")
                continue
            if result["skipped"]:
                _flash("info", f"{file.name} is already in the knowledge base and unchanged.")
            elif result["replaced"]:
                _flash("success", f"Replaced the existing version of {file.name} ({result['chunks']} passages).")
            else:
                _flash("success", f"Added {file.name} ({result['chunks']} passages).")
    st.session_state.uploader_n += 1
    _refresh()
    st.rerun()


def _document_row(doc: dict) -> None:
    name = doc["source"]
    with st.container(border=True):
        details, action = st.columns([4, 2], vertical_alignment="center")
        details.markdown(f"**{name}**")
        details.caption(f"{doc['chunks']} passages · added {_uploaded(doc['uploaded_at'])}")

        if st.session_state.pending_delete != name:
            if action.button("Delete", key=f"delete_{name}", icon=":material/delete:", width="stretch"):
                st.session_state.pending_delete = name
                st.rerun()
            return

        st.warning(f"Delete {name}? Its passages are removed from the knowledge base and cannot be restored.")
        confirm, cancel = st.columns(2)
        if confirm.button("Delete", key=f"confirm_{name}", type="primary", width="stretch"):
            try:
                tools.delete_document(name)
                _flash("success", f"Deleted {name}.")
            except tools.ToolError as exc:
                _flash("error", f"Could not delete {name}: {exc}")
            st.session_state.pending_delete = None
            _refresh()
            st.rerun()
        if cancel.button("Cancel", key=f"cancel_{name}", width="stretch"):
            st.session_state.pending_delete = None
            st.rerun()


def render_documents() -> None:
    _init_state()

    # Everything sits in the left column, so the chat panel (which covers the right side) never hides it.
    left, _ = st.columns([2, 3], gap="large")
    with left:
        st.markdown("#### Add a document")
        files = st.file_uploader(
            "Upload a policy PDF",
            type=["pdf"],
            accept_multiple_files=True,
            key=f"uploader_{st.session_state.uploader_n}",
            label_visibility="collapsed",
        )
        st.caption("A file with the same name as an existing document replaces it. A different name is added "
                   "next to the others, and answers cite the document they come from.")
        if files:
            _handle_uploads(files)

        for level, text in st.session_state.flash:
            getattr(st, level)(text)
        st.session_state.flash = []

        docs = st.session_state.docs
        st.markdown(f"#### Documents in the knowledge base ({len(docs)})")
        if not docs:
            st.caption("No policy documents yet. Upload a PDF to get started.")
        for doc in docs:
            _document_row(doc)
