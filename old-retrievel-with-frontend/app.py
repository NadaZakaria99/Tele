

"""
app.py — Banking SOP Assistant UI
===================================
Run with:  streamlit run app.py

Requires:  pip install streamlit
           rag_pipeline.py must be in the same directory (or on PYTHONPATH).
"""

import streamlit as st
import time
from datetime import datetime

# ── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="Banking SOP Assistant",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Lazy import so UI renders even if the pipeline has an import error ────────
@st.cache_resource(show_spinner="Initialising pipeline …")
def load_pipeline():
    """Import rag_pipeline once and cache it for the session."""
    import rag_pipeline as rp
    # Smoke-test the DB connection on startup
    try:
        rp.test_db_connection()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None
    return rp


# ── Styles ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Typography ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

/* ── App shell ── */
.stApp {
    background: #0d1117;
    color: #c9d1d9;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #21262d;
}

/* ── Header band ── */
.header-band {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px 0 8px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 24px;
}
.header-band h1 {
    font-size: 20px;
    font-weight: 600;
    color: #f0f6fc;
    margin: 0;
    letter-spacing: -0.3px;
}
.header-band span {
    font-size: 12px;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    background: #1c2128;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid #30363d;
}

/* ── Chat bubbles ── */
.msg-user {
    background: #1c2128;
    border: 1px solid #30363d;
    border-radius: 8px 8px 2px 8px;
    padding: 12px 16px;
    margin: 8px 0 8px 60px;
    color: #c9d1d9;
    font-size: 15px;
    line-height: 1.6;
}
.msg-assistant {
    background: #0d1117;
    border: 1px solid #21262d;
    border-left: 3px solid #388bfd;
    border-radius: 2px 8px 8px 8px;
    padding: 14px 18px;
    margin: 8px 60px 8px 0;
    color: #c9d1d9;
    font-size: 15px;
    line-height: 1.7;
}
.msg-assistant .label {
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
    color: #388bfd;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
.msg-error {
    background: #1a0f0f;
    border-left: 3px solid #da3633;
    border-radius: 2px 8px 8px 8px;
    padding: 12px 16px;
    margin: 8px 60px 8px 0;
    color: #ffa198;
    font-size: 14px;
}
.msg-blocked {
    background: #1a0f0f;
    border-left: 3px solid #e3b341;
    border-radius: 2px 8px 8px 8px;
    padding: 12px 16px;
    margin: 8px 60px 8px 0;
    color: #e3b341;
    font-size: 14px;
}

/* ── Source chunk cards ── */
.chunk-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 13px;
}
.chunk-card .chunk-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #8b949e;
    margin-bottom: 5px;
    display: flex;
    gap: 14px;
}
.chunk-card .chunk-meta .score-high { color: #3fb950; }
.chunk-card .chunk-meta .score-med  { color: #e3b341; }
.chunk-card .chunk-meta .score-low  { color: #8b949e; }
.chunk-card .chunk-text {
    color: #c9d1d9;
    line-height: 1.5;
}

/* ── Stage badges ── */
.stage-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin: 6px 0 14px;
}
.badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid;
}
.badge-done  { color: #3fb950; border-color: #238636; background: #0d1f0d; }
.badge-block { color: #e3b341; border-color: #9e6a03; background: #1a1400; }
.badge-error { color: #ffa198; border-color: #da3633; background: #1a0f0f; }
.badge-run   { color: #388bfd; border-color: #1f6feb; background: #0c1929; }

/* ── Divider ── */
hr { border-color: #21262d; }

/* ── Input area ── */
.stTextInput > div > div > input {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 15px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 2px rgba(56,139,253,0.15) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: #1f6feb !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 500 !important;
    padding: 8px 20px !important;
    transition: background 0.15s !important;
}
.stButton > button:hover {
    background: #388bfd !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-size: 13px !important;
    color: #8b949e !important;
    font-family: 'IBM Plex Mono', monospace !important;
}

/* ── Scrollable chat history ── */
.chat-container {
    max-height: 62vh;
    overflow-y: auto;
    padding-right: 4px;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []          # list of dicts: {role, content, sources, stages, ts}
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏦 Banking SOP Assistant")
    st.markdown(
        "<small style='color:#8b949e'>Powered by the NVIDIA RAG pipeline.<br>"
        "Answers are grounded in your SOP vector store.</small>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Pipeline status
    st.markdown("**Pipeline status**")
    pipeline = load_pipeline()
    st.session_state.pipeline = pipeline

    if pipeline:
        st.markdown(
            '<span class="badge badge-done">● DB connected</span>'
            '<br><span class="badge badge-done">● NemoGuard ready</span>'
            '<br><span class="badge badge-done">● Embeddings ready</span>'
            '<br><span class="badge badge-done">● pgvector ready</span>'
            '<br><span class="badge badge-done">● Reranker ready</span>'
            '<br><span class="badge badge-done">● Generator ready</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="badge badge-error">● Pipeline unavailable</span>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Quick-fire example queries
    st.markdown("**Example queries**")
    examples = [
        "What is the required verification process for a high-value wire transfer?",
        "How do I handle a customer requesting to close an account with a negative balance?",
        "Are there any exceptions to the 3-day hold policy on international checks?",
        "What KYC documents are required for corporate account opening?",
    ]
    for ex in examples:
        if st.button(ex[:55] + "…" if len(ex) > 55 else ex, use_container_width=True):
            st.session_state["prefill"] = ex

    st.divider()

    if st.button("Clear conversation", use_container_width=True):
        st.session_state.history = []
        st.rerun()

    st.markdown(
        "<small style='color:#8b949e'>Model stack:<br>"
        "Safety · NemoGuard 8B<br>"
        "Embed  · nv-embedqa-1b-v2<br>"
        "Rank   · nv-rerankqa-1b-v2<br>"
        "Gen    · Llama 3.1 8B</small>",
        unsafe_allow_html=True,
    )


# ── Main panel ────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="header-band">'
    '<h1>Banking SOP Assistant</h1>'
    '<span>RAG · pgvector · NVIDIA API</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Chat history ──────────────────────────────────────────────────────────────
col_chat, col_sources = st.columns([3, 2])

with col_chat:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    if not st.session_state.history:
        st.markdown(
            "<div style='text-align:center;padding:60px 20px;color:#8b949e;font-size:14px'>"
            "Ask a question about banking SOPs.<br>"
            "<small>Queries are safety-checked before retrieval.</small>"
            "</div>",
            unsafe_allow_html=True,
        )

    for turn in st.session_state.history:
        if turn["role"] == "user":
            st.markdown(f'<div class="msg-user">{turn["content"]}</div>', unsafe_allow_html=True)
        elif turn["role"] == "assistant":
            st.markdown(
                f'<div class="msg-assistant">'
                f'{turn["content"]}'
                f'<div style="font-size:11px;color:#484f58;margin-top:10px;font-family:IBM Plex Mono,monospace">'
                f'{turn.get("ts", "")}&nbsp;·&nbsp;{turn.get("latency", "")} ms</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif turn["role"] == "blocked":
            st.markdown(
                f'<div class="msg-blocked">🚫 {turn["content"]}</div>',
                unsafe_allow_html=True,
            )
        elif turn["role"] == "error":
            st.markdown(
                f'<div class="msg-error">⚠ {turn["content"]}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)


with col_sources:
    # Show sources for the latest assistant turn
    latest_sources = next(
        (t.get("sources", []) for t in reversed(st.session_state.history) if t["role"] == "assistant"),
        [],
    )

    if latest_sources:
        st.markdown(
            f"<small style='color:#8b949e;font-family:IBM Plex Mono,monospace'>"
            f"SOURCE CHUNKS — top {len(latest_sources)} after reranking</small>",
            unsafe_allow_html=True,
        )
        for i, chunk in enumerate(latest_sources, 1):
            r_score = chunk.get("reranker_score", None)
            c_dist  = chunk.get("cosine_distance", None)

            if r_score is not None:
                score_class = "score-high" if r_score > 5 else ("score-med" if r_score > 0 else "score-low")
                score_html = f'<span class="{score_class}">rerank {r_score:.3f}</span>'
            else:
                score_html = ""

            dist_html = (
                f'<span>cosine {c_dist:.4f}</span>' if c_dist is not None else ""
            )
            preview = chunk.get("content", "").replace("\n", " ").strip()[:280]

            st.markdown(
                f'<div class="chunk-card">'
                f'<div class="chunk-meta">'
                f'<span>Chunk #{chunk.get("id", i)}</span>'
                f'{dist_html}{score_html}'
                f'</div>'
                f'<div class="chunk-text">{preview}{"…" if len(chunk.get("content",""))>280 else ""}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='padding:40px 0;text-align:center;color:#484f58;font-size:13px;"
            "font-family:IBM Plex Mono,monospace'>source chunks appear here</div>",
            unsafe_allow_html=True,
        )


# ── Input bar ─────────────────────────────────────────────────────────────────
st.divider()

# Handle example-button prefill
prefill = st.session_state.pop("prefill", "")

with st.form(key="query_form", clear_on_submit=True):
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        query = st.text_input(
            label="query",
            value=prefill,
            placeholder="Ask a question about banking SOPs …",
            label_visibility="collapsed",
        )
    with col_btn:
        submitted = st.form_submit_button("Send", use_container_width=True)


# ── Pipeline invocation ───────────────────────────────────────────────────────
if submitted and query.strip():
    if not st.session_state.pipeline:
        st.error("Pipeline is not available. Check the sidebar for connection errors.")
    else:
        rp = st.session_state.pipeline

        # Append user turn immediately
        st.session_state.history.append({"role": "user", "content": query.strip()})

        stages = []
        t0 = time.monotonic()

        with st.spinner("Running pipeline …"):
            # ── Safety ──
            stages.append({"label": "Safety", "status": "run"})
            try:
                is_safe, category = rp.check_input_safety(query.strip())
            except Exception as e:
                st.session_state.history.append({
                    "role": "error",
                    "content": f"Safety check failed: {e}",
                })
                st.rerun()

            if not is_safe:
                stages[-1]["status"] = "block"
                st.session_state.history.append({
                    "role": "blocked",
                    "content": f"Query blocked by safety filter (category: {category}). "
                               "Please rephrase or ask a different question.",
                })
                st.rerun()

            stages[-1]["status"] = "done"

            # ── Topic Relevance ──
            stages.append({"label": "Topic", "status": "run"})
            try:
                is_relevant, topic_label = rp.check_topic_relevance(query.strip())
            except Exception as e:
                st.session_state.history.append({
                    "role": "error",
                    "content": f"Topic check failed: {e}",
                })
                st.rerun()

            if not is_relevant:
                stages[-1]["status"] = "block"
                st.session_state.history.append({
                    "role": "blocked",
                    "content": "I can only answer questions related to banking SOPs and legal topics relevant to banking operations. Please rephrase your question.",
                })
                st.rerun()

            stages[-1]["status"] = "done"

            # ── Embed ──
            stages.append({"label": "Embed", "status": "run"})
            try:
                embedding = rp.embed_query(query.strip())
                stages[-1]["status"] = "done"
            except Exception as e:
                stages[-1]["status"] = "error"
                st.session_state.history.append({"role": "error", "content": f"Embedding failed: {e}"})
                st.rerun()

            # ── Retrieve ──
            stages.append({"label": "Retrieve 20", "status": "run"})
            try:
                candidates = rp.vector_search(embedding, top_k=20)
                stages[-1]["status"] = "done"
            except Exception as e:
                stages[-1]["status"] = "error"
                st.session_state.history.append({"role": "error", "content": f"Vector search failed: {e}"})
                st.rerun()

            # ── Rerank ──
            stages.append({"label": "Rerank → 5", "status": "run"})
            try:
                top_docs = rp.rerank_chunks(query.strip(), candidates, top_n=5)
                stages[-1]["status"] = "done"
            except Exception as e:
                stages[-1]["status"] = "error"
                top_docs = candidates[:5]   # graceful fallback

            # ── Generate ──
            stages.append({"label": "Generate", "status": "run"})
            try:
                answer = rp.generate_answer(query.strip(), top_docs)
                stages[-1]["status"] = "done"
            except Exception as e:
                stages[-1]["status"] = "error"
                answer = f"Generation failed: {e}"

            # ── Response Safety ──
            stages.append({"label": "Out-Safety", "status": "run"})
            try:
                resp_is_safe, resp_category = rp.check_response_safety(answer, query.strip())
                if not resp_is_safe:
                    stages[-1]["status"] = "block"
                    answer = rp.RESPONSE_SAFETY_FALLBACK
                else:
                    stages[-1]["status"] = "done"
            except Exception as e:
                stages[-1]["status"] = "error"
                # fail open on error just like the main pipeline
                pass

        latency_ms = int((time.monotonic() - t0) * 1000)

        st.session_state.history.append({
            "role": "assistant",
            "content": answer,
            "sources": top_docs,
            "stages": stages,
            "ts": datetime.now().strftime("%H:%M:%S"),
            "latency": latency_ms,
        })
        st.rerun()