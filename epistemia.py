import streamlit as st
import json
import random
from datetime import datetime

import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2.service_account import Credentials

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Phase 9 Test",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# CONSTANTS
# ============================================================================
WRITING_FIXED_NORM = "not telling someone they have gained weight"
WORD_MIN = 50

LIKERT_LABELS_RECOGN = [
    "Not at all", "Slightly", "Somewhat", "Moderately", "Very", "Mostly", "Completely",
]
LIKERT_LABELS_APPROP_WRITING = [
    "Extremely\ninappropriate", "Very\ninappropriate", "Somewhat\ninappropriate",
    "Neither", "Somewhat\nappropriate", "Very\nappropriate", "Extremely\nappropriate",
]
# Phase 9 labels — text instead of numbers
LIKERT_LABELS_DEFAULT = [
    "Extremely\ninappropriate",
    "Very\ninappropriate",
    "Somewhat\ninappropriate",
    "Neither",
    "Somewhat\nappropriate",
    "Very\nappropriate",
    "Extremely\nappropriate",
]

INVOLVEMENT_ITEMS = [
    ("They got me involved.",       "inv_0"),
    ("They seemed relevant to me.", "inv_1"),
    ("They interested me.",         "inv_2"),
]
THREAT_ITEMS = [
    ("They tried to manipulate me.",            "thr_0"),
    ("They tried to pressure me.",              "thr_1"),
    ("They undermined my sense of self-worth.", "thr_2"),
    ("They made me feel less than capable.",    "thr_3"),
    ("They made me think I should change.",     "thr_4"),
]
SOURCE_ITEMS = [
    ("Reliable",  "src_0"),
    ("Trusted",   "src_1"),
    ("Honest",    "src_2"),
    ("Competent", "src_3"),
    ("Expert",    "src_4"),
    ("Informed",  "src_5"),
]

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
if "session_initialized" not in st.session_state:
    st.session_state.update({
        "session_initialized":      True,
        "phase":                    9,
        "involvement_responses":    {},
        "threat_responses":         {},
        "source_responses":         {},
        "writing_group":            random.choice(["A", "B"]),
        "writing_text_final":       "",
        "writing_keystroke_log":    {},   # {ISO timestamp: full text snapshot}
        "writing_llm_output":       "",
        "writing_llm_exchanges":    [],   # [{role, content, timestamp}]
        "writing_post_recogn":      None,
        "writing_post_appropriate": None,
        "writing_pending_msg":      None,
        "writing_chat_initialized": False,
        "gemini_model":             None,
        "writing_chat":             None,
        # timing
        "writing_phase_start":      None,
        "writing_phase_end":        None,
    })

# ============================================================================
# HELPERS — Likert scales
# ============================================================================
def likert_7(key, labels=None):
    """7-point scale rendered as clickable text buttons."""
    if labels is None:
        labels = LIKERT_LABELS_DEFAULT
    selected = st.session_state.get(key)
    cols = st.columns(7)
    for j, label in enumerate(labels):
        val = j + 1
        with cols[j]:
            btn_type = "primary" if selected == val else "secondary"
            if st.button(label, key=f"{key}_btn_{val}", use_container_width=True, type=btn_type):
                st.session_state[key] = val
                st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)
    return st.session_state.get(key)

def render_7pt_item(label, key):
    """Single Likert item with text labels (no numbers)."""
    st.markdown(f"**{label}**")
    cols     = st.columns(7)
    selected = st.session_state.get(key)
    scale_labels = [
        "Totally\ndisagree", "Mostly\ndisagree", "Somewhat\ndisagree",
        "Neither", "Somewhat\nagree", "Mostly\nagree", "Totally\nagree"
    ]
    for j in range(1, 8):
        with cols[j - 1]:
            lbl = scale_labels[j - 1]
            if st.button(lbl, key=f"{key}_{j}", use_container_width=True,
                         type="primary" if selected == j else "secondary"):
                st.session_state[key] = j
                st.rerun()
    st.markdown("")

# ============================================================================
# HELPERS — Autosave JS
#
# Every 1 s JS samples the textarea → writes {ISO_ts: text} into a hidden
# input (autosave_json_sink).  A flip-flop hidden input (autosave_trigger)
# forces a Streamlit rerun each second so Python can merge the log.
# On each rerun, merge_autosave_into_log() accumulates new entries.
# ============================================================================

AUTOSAVE_SINK_LABEL    = "autosave_json_sink"
AUTOSAVE_TRIGGER_LABEL = "autosave_trigger"

def inject_autosave_js():
    st.markdown(f"""
<script>
(function() {{
    // Preserve the log across reruns — never reset it
    window._ksLog = window._ksLog || {{}};

    // Clear any stacked interval from previous reruns
    if (window._autosaveIntervalId != null) {{
        clearInterval(window._autosaveIntervalId);
        window._autosaveIntervalId = null;
    }}

    let lastText = null;
    let triggerFlip = false;

    function nativeSet(el, val) {{
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    }}

    function findInput(label) {{
        return document.querySelector('input[aria-label="' + label + '"]');
    }}

    function findTextarea() {{
        const tas = document.querySelectorAll('textarea');
        for (const ta of tas) {{ if (!ta.disabled) return ta; }}
        return null;
    }}

    function tick() {{
        const ta = findTextarea();
        if (ta) {{
            const val = ta.value;
            if (val !== lastText && val.trim() !== '') {{
                lastText = val;
                const ts = new Date().toISOString();
                window._ksLog[ts] = val;
                const sink = findInput('{AUTOSAVE_SINK_LABEL}');
                if (sink) nativeSet(sink, JSON.stringify(window._ksLog));
            }}
        }}
        // Flip trigger to force Streamlit rerun
        const trigger = findInput('{AUTOSAVE_TRIGGER_LABEL}');
        if (trigger) {{
            triggerFlip = !triggerFlip;
            nativeSet(trigger, triggerFlip ? '1' : '0');
        }}
    }}

    tick();
    window._autosaveIntervalId = setInterval(tick, 1000);
}})();
</script>
""", unsafe_allow_html=True)


def render_autosave_inputs():
    st.markdown("""
<style>
div[data-testid='stTextInput']:has(input[aria-label='autosave_json_sink']),
div[data-testid='stTextInput']:has(input[aria-label='autosave_trigger'])
{ position:absolute; opacity:0; pointer-events:none; height:0; overflow:hidden; }
</style>
""", unsafe_allow_html=True)
    st.text_input(AUTOSAVE_SINK_LABEL,    key="autosave_json_sink",   label_visibility="hidden")
    st.text_input(AUTOSAVE_TRIGGER_LABEL, key="autosave_trigger_val", label_visibility="hidden")


def merge_autosave_into_log():
    raw = st.session_state.get("autosave_json_sink", "")
    if not raw:
        return
    try:
        incoming = json.loads(raw)
    except Exception:
        return
    log = st.session_state.writing_keystroke_log
    for ts, text in incoming.items():
        if ts not in log:
            log[ts] = text
    st.session_state.writing_keystroke_log = log

# ============================================================================
# HELPERS — Gemini
# ============================================================================
def get_gemini_model() -> GenerativeModel:
    if st.session_state.gemini_model is None:
        vertex_creds = Credentials.from_service_account_info(
            st.secrets["gcp_vertex_account"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        vertexai.init(
            project=st.secrets["gcp_project_id"],
            location=st.secrets.get("gcp_location", "europe-west9"),
            credentials=vertex_creds,
        )
        st.session_state.gemini_model = GenerativeModel("gemini-2.5-flash")
    return st.session_state.gemini_model

# ============================================================================
# PHASE 9 — Conversation Perception
# ============================================================================
if st.session_state.phase == 9:
    st.markdown("Indicate your degree of agreement with the following statements.")
    st.markdown("*Scale: Totally disagree → Totally agree*")

    def _render_group(items, header):
        st.markdown(f"#### {header}")
        for label, key in items:
            render_7pt_item(label, key)

    _render_group(INVOLVEMENT_ITEMS, "Involvement — The messages I read during the conversation with the AI:")
    _render_group(THREAT_ITEMS,      "Perceived Threat — The messages I read during the conversation with the AI:")
    _render_group(SOURCE_ITEMS,      "Evaluation of the Source — To what extent the source of these messages is:")

    if st.button("Continue"):
        all_keys = [k for _, k in INVOLVEMENT_ITEMS + THREAT_ITEMS + SOURCE_ITEMS]
        missing  = [k for k in all_keys if not st.session_state.get(k)]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        st.session_state.involvement_responses = {l: st.session_state[k] for l, k in INVOLVEMENT_ITEMS}
        st.session_state.threat_responses      = {l: st.session_state[k] for l, k in THREAT_ITEMS}
        st.session_state.source_responses      = {l: st.session_state[k] for l, k in SOURCE_ITEMS}
        st.session_state.phase = 9.1
        st.rerun()

# ============================================================================
# PHASE 9.1 — Writing Task Instructions
# ============================================================================
elif st.session_state.phase == 9.1:
    st.markdown("## Writing Task — Instructions")
    st.markdown("---")
    st.markdown("**Please write around 5 lines expressing your personal perception of a specific social norm.**")
    st.markdown(
        "There is **no right or wrong answer**. Write freely — you can describe "
        "what you think about the norm, share a personal experience, or argue a position."
    )
    st.markdown("---")
    st.markdown("**The norm you will be writing about is:**")
    st.markdown(
        f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
        f"padding:14px 18px;border-radius:4px;font-size:1.1rem;font-style:italic;'>"
        f"\"{WRITING_FIXED_NORM}\"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(f"*(Debug: assigned to Group **{st.session_state.writing_group}**)*")

    if st.button("Start writing →"):
        # Record phase start time
        st.session_state.writing_phase_start = datetime.utcnow().isoformat() + "Z"
        st.session_state.phase = 9.2
        st.rerun()

# ============================================================================
# PHASE 9.2 — Writing Task Screen
# ============================================================================
elif st.session_state.phase == 9.2:

    # Merge any new autosave data on every rerun (includes 1-s triggered reruns)
    merge_autosave_into_log()

    group = st.session_state.writing_group

    def _writing_ui(textarea_key: str, height: int, show_word_counter: bool = False):
        """Norm box + textarea + autosave + optional word counter + continue button."""
        st.markdown(
            "**Please write around 5 lines expressing your personal perception of the following norm:**"
        )
        st.markdown(
            f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
            f"padding:12px 16px;border-radius:4px;font-style:italic;margin-bottom:16px;'>"
            f"\"{WRITING_FIXED_NORM}\"</div>",
            unsafe_allow_html=True,
        )

        st.text_area(
            "Your answer:",
            height=height,
            key=textarea_key,
            label_visibility="collapsed",
            placeholder="Write your thoughts here…",
        )

        render_autosave_inputs()
        inject_autosave_js()

        # ── Word counter + conditional Continue (Group B) ────────────────────
        current_text  = st.session_state.get(textarea_key, "") or ""
        word_count    = len(current_text.split()) if current_text.strip() else 0
        enough_words  = word_count >= WORD_MIN

        if show_word_counter:
            # Progress bar and word count
            progress = min(word_count / WORD_MIN, 1.0)
            st.progress(progress)

            if enough_words:
                st.success(
                    f"✅ **{word_count} words** — minimum reached! You can continue.",
                    icon=None,
                )
            else:
                remaining = WORD_MIN - word_count
                st.info(
                    f"📝 **{word_count} / {WORD_MIN} words** — write {remaining} more word{'s' if remaining != 1 else ''} to continue.",
                )

            # Show live autosave snapshot count
            n_snap = len(st.session_state.writing_keystroke_log)
            if n_snap > 0:
                st.caption(f"💾 {n_snap} snapshot{'s' if n_snap != 1 else ''} autosaved")

            # Continue only enabled when enough words
            if enough_words:
                if st.button("Continue →", key=f"btn_{textarea_key}"):
                    _save_and_advance(textarea_key, current_text)
            else:
                st.button("Continue →", key=f"btn_{textarea_key}", disabled=True)

        else:
            # Group A — original behaviour
            n_snap = len(st.session_state.writing_keystroke_log)
            if n_snap > 0:
                st.caption(f"💾 {n_snap} snapshot{'s' if n_snap != 1 else ''} autosaved")

            if st.button("Continue →", key=f"btn_{textarea_key}"):
                if word_count < WORD_MIN:
                    st.warning(f"Please write at least {WORD_MIN} words before continuing.")
                    st.stop()
                _save_and_advance(textarea_key, current_text)

    def _save_and_advance(textarea_key: str, text: str):
        """Finalise log and advance to phase 9.3."""
        merge_autosave_into_log()

        # Record phase end time
        st.session_state.writing_phase_end = datetime.utcnow().isoformat() + "Z"

        # Add explicit start/end markers to the log
        log = st.session_state.writing_keystroke_log
        if st.session_state.writing_phase_start:
            log["__phase_start__"] = st.session_state.writing_phase_start
        log["__phase_end__"] = st.session_state.writing_phase_end

        # Fallback: ensure at least one snapshot
        if not any(k for k in log if not k.startswith("__")):
            ts = datetime.utcnow().isoformat() + "Z"
            log[ts] = text

        st.session_state.writing_text_final    = text
        st.session_state.writing_keystroke_log = log
        st.session_state.phase = 9.3
        st.rerun()

    # ── GROUP A ──────────────────────────────────────────────────────────────
    if group == "A":
        st.markdown("## Your Writing")
        _writing_ui("writing_text_A", height=260, show_word_counter=False)

    # ── GROUP B ──────────────────────────────────────────────────────────────
    else:
        if not st.session_state.writing_chat_initialized:
            model        = get_gemini_model()
            writing_chat = model.start_chat()
            writing_chat.send_message(
                "You are a helpful writing assistant. "
                "The user is in a research study and must write approximately 5 lines "
                "expressing their personal view on the following social norm: "
                f"\"{WRITING_FIXED_NORM}\". "
                "Help them think about the topic, suggest ideas, or draft text if asked. "
                "Be concise and neutral. Respond in the same language the user writes in."
            )
            st.session_state.writing_chat             = writing_chat
            st.session_state.writing_chat_initialized = True

        col_write, col_chat = st.columns([3, 2], gap="large")

        with col_write:
            st.markdown("## Your Writing")
            _writing_ui("writing_text_B", height=300, show_word_counter=True)

        with col_chat:
            st.markdown("## 🤖 AI Writing Assistant")
            st.caption("Optional — use for ideas, feedback, or drafting.")

            for msg in st.session_state.writing_llm_exchanges:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    # Show timestamp below each message
                    if "timestamp" in msg:
                        st.caption(f"🕐 {msg['timestamp']}")

            if st.session_state.writing_pending_msg:
                pending    = st.session_state.writing_pending_msg
                ts_sent    = datetime.utcnow().isoformat() + "Z"
                st.session_state.writing_llm_exchanges.append({
                    "role":      "user",
                    "content":   pending,
                    "timestamp": ts_sent,
                })
                with st.chat_message("user"):
                    st.markdown(pending)
                    st.caption(f"🕐 {ts_sent}")
                st.session_state.writing_pending_msg = None

                chat = st.session_state.writing_chat
                with st.chat_message("assistant"):
                    stream     = chat.send_message(pending, stream=True)
                    reply      = st.write_stream(chunk.text for chunk in stream)
                    ts_reply   = datetime.utcnow().isoformat() + "Z"
                    st.caption(f"🕐 {ts_reply}")

                st.session_state.writing_llm_exchanges.append({
                    "role":      "assistant",
                    "content":   reply,
                    "timestamp": ts_reply,
                })
                st.session_state.writing_llm_output = reply
                st.rerun()

            llm_input = st.chat_input("Ask the AI for help…", key="writing_chat_input")
            if llm_input:
                st.session_state.writing_pending_msg = llm_input
                st.rerun()

# ============================================================================
# PHASE 9.3 — Post-Writing Questionnaire
# ============================================================================
elif st.session_state.phase == 9.3:
    st.markdown("## A few questions about what you just wrote")
    st.markdown("Please answer based on the text you wrote in the previous section.")
    st.markdown("---")

    st.markdown("**To what extent does the text you wrote reflect your personal opinion?**")
    st.markdown("*Not at all → Completely*")
    recogn = likert_7(key="writing_post_recogn", labels=LIKERT_LABELS_RECOGN)

    st.markdown("---")

    st.markdown(
        f"**After writing, how appropriate or inappropriate do you consider "
        f"the action of: \"{WRITING_FIXED_NORM}\"?**"
    )
    st.markdown("*Extremely inappropriate → Extremely appropriate*")
    appropriate = likert_7(key="writing_post_appropriate", labels=LIKERT_LABELS_APPROP_WRITING)

    st.markdown("---")

    if st.button("Continue →"):
        if recogn is None or appropriate is None:
            st.warning("Please answer both questions before continuing.")
            st.stop()
        st.session_state.writing_post_recogn      = recogn
        st.session_state.writing_post_appropriate = appropriate
        st.session_state.phase = 99
        st.rerun()

# ============================================================================
# PHASE 99 — DATA SUMMARY
# ============================================================================
elif st.session_state.phase == 99:
    st.markdown("# 📋 Collected Data — Debug Summary")
    st.markdown("This page shows all the data that would be saved to Google Sheets in the real study.")
    st.markdown("---")

    st.markdown("## Phase 9 — Conversation Perception")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Involvement**")
        for label, val in st.session_state.involvement_responses.items():
            st.write(f"- {label}: **{val}**")
    with col2:
        st.markdown("**Perceived Threat**")
        for label, val in st.session_state.threat_responses.items():
            st.write(f"- {label}: **{val}**")
    with col3:
        st.markdown("**Source Evaluation**")
        for label, val in st.session_state.source_responses.items():
            st.write(f"- {label}: **{val}**")

    st.markdown("---")
    st.markdown("## Phase 9.2 — Writing Task")
    st.write(f"**Norm:** {WRITING_FIXED_NORM}")
    st.write(f"**Group:** {st.session_state.writing_group}")

    # Timing
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.write(f"⏱ **Phase start:** {st.session_state.writing_phase_start or '—'}")
    with col_t2:
        st.write(f"⏱ **Phase end:** {st.session_state.writing_phase_end or '—'}")

    # Duration
    if st.session_state.writing_phase_start and st.session_state.writing_phase_end:
        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            t0  = datetime.strptime(st.session_state.writing_phase_start, fmt)
            t1  = datetime.strptime(st.session_state.writing_phase_end,   fmt)
            dur = int((t1 - t0).total_seconds())
            st.write(f"⏱ **Duration:** {dur} seconds ({dur // 60}m {dur % 60}s)")
        except Exception:
            pass

    st.markdown("**Final written text:**")
    st.text_area("", value=st.session_state.writing_text_final, height=160,
                 disabled=True, label_visibility="collapsed")
    final_words = len(st.session_state.writing_text_final.split()) if st.session_state.writing_text_final else 0
    st.write(f"Word count: **{final_words}**")

    # Keystroke log — filter out meta keys for display
    real_log = {k: v for k, v in st.session_state.writing_keystroke_log.items()
                if not k.startswith("__")}
    n_entries = len(real_log)
    st.markdown(f"**Autosave log** — {n_entries} 1-second snapshots:")
    st.json(st.session_state.writing_keystroke_log)

    if st.session_state.writing_group == "B":
        st.markdown("**AI chat exchanges (with timestamps):**")
        st.write(f"Number of messages: **{len(st.session_state.writing_llm_exchanges)}**")
        st.json(st.session_state.writing_llm_exchanges)

    st.markdown("---")
    st.markdown("## Phase 9.3 — Post-Writing Questionnaire")
    st.write(f"Reflects personal opinion (1–7): **{st.session_state.writing_post_recogn}**")
    st.write(f"Post-writing appropriateness (1–7): **{st.session_state.writing_post_appropriate}**")

    st.markdown("---")
    st.markdown("## Full data payload")
    payload = {
        "involvement_responses":   st.session_state.involvement_responses,
        "threat_responses":        st.session_state.threat_responses,
        "source_responses":        st.session_state.source_responses,
        "writing_group":           st.session_state.writing_group,
        "writing_norm":            WRITING_FIXED_NORM,
        "writing_text_final":      st.session_state.writing_text_final,
        "writing_phase_start":     st.session_state.writing_phase_start,
        "writing_phase_end":       st.session_state.writing_phase_end,
        "writing_keystroke_log":   st.session_state.writing_keystroke_log,
        "writing_snapshot_count":  len(real_log),
        "writing_llm_exchanges":   st.session_state.writing_llm_exchanges,
        "writing_llm_output":      st.session_state.writing_llm_output,
        "writing_post_recogn":     st.session_state.writing_post_recogn,
        "writing_post_appropriate":st.session_state.writing_post_appropriate,
        "timestamp":               datetime.now().isoformat(),
    }
    st.json(payload)

    st.markdown("## Google Sheets columns")
    sheet_row = [
        json.dumps(st.session_state.involvement_responses, ensure_ascii=False),
        json.dumps(st.session_state.threat_responses,      ensure_ascii=False),
        json.dumps(st.session_state.source_responses,      ensure_ascii=False),
        str(st.session_state.writing_group),
        str(st.session_state.writing_phase_start),
        str(st.session_state.writing_phase_end),
        json.dumps(st.session_state.writing_keystroke_log, ensure_ascii=False),
        json.dumps(st.session_state.writing_llm_exchanges, ensure_ascii=False),
        str(st.session_state.writing_post_recogn),
        str(st.session_state.writing_post_appropriate),
    ]
    col_names = [
        "col12 involvement", "col13 threat", "col14 source",
        "col33 writing_group",
        "col34 writing_phase_start", "col35 writing_phase_end",
        "col36 keystroke_log", "col37 llm_exchanges",
        "col38 post_recogn", "col39 post_appropriate",
    ]
    for name, val in zip(col_names, sheet_row):
        with st.expander(name):
            st.code(val, language="json")

    st.markdown("---")
    if st.button("🔄 Restart test"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()