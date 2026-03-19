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

LIKERT_LABELS_RECOGN = [
    "Not at all", "Slightly", "Somewhat", "Moderately", "Very", "Mostly", "Completely",
]
LIKERT_LABELS_APPROP_WRITING = [
    "Extremely\ninappropriate", "Very\ninappropriate", "Somewhat\ninappropriate",
    "Neither", "Somewhat\nappropriate", "Very\nappropriate", "Extremely\nappropriate",
]
LIKERT_LABELS_DEFAULT = [
    "1\nExtremely inappropriate", "2\nVery inappropriate", "3\nSomewhat inappropriate",
    "4\nNeither", "5\nSomewhat appropriate", "6\nVery appropriate", "7\nExtremely appropriate",
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
        "writing_keystroke_log":    {},   # {ISO timestamp: partial text snapshot}
        "writing_llm_output":       "",
        "writing_llm_exchanges":    [],
        "writing_post_recogn":      None,
        "writing_post_appropriate": None,
        "writing_pending_msg":      None,
        "writing_chat_initialized": False,
        "gemini_model":             None,
        "writing_chat":             None,
    })

# ============================================================================
# HELPERS — Likert scales
# ============================================================================
def likert_7(key, labels=None):
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
    st.markdown(f"**{label}**")
    cols     = st.columns(7)
    selected = st.session_state.get(key)
    for j in range(1, 8):
        with cols[j - 1]:
            if st.button(str(j), key=f"{key}_{j}", use_container_width=True,
                         type="primary" if selected == j else "secondary"):
                st.session_state[key] = j
                st.rerun()
    st.markdown("")

# ============================================================================
# HELPERS — Autosave JS
#
# Strategy:
#   1. Every 1 second, JS reads the textarea and writes a {timestamp: text}
#      entry into a hidden <input> (the "autosave sink").
#   2. A second hidden <input> acts as a "flush trigger": JS toggles its value
#      between "0" and "1" each second, causing Streamlit to detect a widget
#      change and rerun the script.
#   3. On each rerun, Python reads the autosave sink and merges the JSON log
#      into st.session_state.writing_keystroke_log — accumulating ALL snapshots.
#   4. On Continue, the final text + complete accumulated log are saved.
#
# NOTE: Streamlit only reruns when a widget value CHANGES, so the flip-flop
# trigger ("0"→"1"→"0"→…) ensures a rerun every ~1 second while the user types.
# ============================================================================

AUTOSAVE_SINK_LABEL   = "autosave_json_sink"
AUTOSAVE_TRIGGER_LABEL = "autosave_trigger"

def inject_autosave_js():
    """
    Inject JS that:
    - Samples the textarea every 1 second.
    - Accumulates {ISO_ts: text} in window._ksLog.
    - Writes the full JSON into the hidden autosave_json_sink input.
    - Flips the autosave_trigger input between "0"/"1" every second
      so Streamlit detects a widget change and reruns.
    """
    st.markdown(f"""
<script>
(function() {{
    if (window._autosaveRunning) return;
    window._autosaveRunning = true;
    window._ksLog = window._ksLog || {{}};
    let lastText = null;

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
        for (const ta of tas) {{
            if (!ta.disabled) return ta;
        }}
        return null;
    }}

    let triggerFlip = false;

    function tick() {{
        const ta = findTextarea();
        if (ta) {{
            const val = ta.value;
            // Always record if text changed or if log is empty and we have text
            if (val !== lastText && val.trim() !== '') {{
                lastText = val;
                const ts = new Date().toISOString();
                window._ksLog[ts] = val;  // full snapshot at this second

                // Push accumulated log into sink input
                const sink = findInput('{AUTOSAVE_SINK_LABEL}');
                if (sink) {{
                    nativeSet(sink, JSON.stringify(window._ksLog));
                }}
            }}
        }}

        // Always flip the trigger so Streamlit picks up the change and reruns
        const trigger = findInput('{AUTOSAVE_TRIGGER_LABEL}');
        if (trigger) {{
            triggerFlip = !triggerFlip;
            nativeSet(trigger, triggerFlip ? '1' : '0');
        }}
    }}

    // Start immediately and then every 1000ms
    tick();
    setInterval(tick, 1000);
}})();
</script>
""", unsafe_allow_html=True)


def render_autosave_inputs():
    """
    Render the two hidden inputs used by the autosave JS.
    Returns (json_sink_value, trigger_value).
    """
    # Hide both inputs visually
    st.markdown("""
<style>
div[data-testid='stTextInput']:has(input[aria-label='autosave_json_sink']),
div[data-testid='stTextInput']:has(input[aria-label='autosave_trigger'])
{ position:absolute; opacity:0; pointer-events:none; height:0; overflow:hidden; }
</style>
""", unsafe_allow_html=True)

    sink_val    = st.text_input(AUTOSAVE_SINK_LABEL,    key="autosave_json_sink",    label_visibility="hidden")
    trigger_val = st.text_input(AUTOSAVE_TRIGGER_LABEL, key="autosave_trigger_val",  label_visibility="hidden")
    return sink_val, trigger_val


def merge_autosave_into_log():
    """
    Read the current autosave sink and merge new entries into
    st.session_state.writing_keystroke_log (accumulates across reruns).
    """
    raw = st.session_state.get("autosave_json_sink", "")
    if not raw:
        return
    try:
        incoming = json.loads(raw)
    except Exception:
        return
    # Merge: existing entries are never overwritten
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
        st.session_state.gemini_model = GenerativeModel("gemma3")
    return st.session_state.gemini_model

# ============================================================================
# PHASE 9 — Conversation Perception
# ============================================================================
if st.session_state.phase == 9:
    st.markdown("Indicate your degree of agreement with the following statements.")
    st.markdown("*Scale: 1 = Totally disagree — 7 = Totally agree*")

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
        st.session_state.phase = 9.2
        st.rerun()

# ============================================================================
# PHASE 9.2 — Writing Task Screen
# ============================================================================
elif st.session_state.phase == 9.2:

    # ── Merge any new autosave data from JS into session state ───────────────
    # This runs on EVERY rerun (including the 1-second triggered reruns),
    # so the log grows continuously while the user types.
    merge_autosave_into_log()

    group = st.session_state.writing_group

    # Show live snapshot count so researcher can verify autosave is working
    n_snapshots = len(st.session_state.writing_keystroke_log)
    if n_snapshots > 0:
        st.caption(f"💾 Autosave active — {n_snapshots} snapshot{'s' if n_snapshots != 1 else ''} recorded")

    def _writing_ui(textarea_key: str, height: int):
        """Norm box + textarea + autosave JS + continue button."""
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

        # Render hidden autosave inputs (sink + trigger)
        render_autosave_inputs()

        # Inject the 1-second sampler + trigger JS
        inject_autosave_js()

        if st.button("Continue →", key=f"btn_{textarea_key}"):
            text = st.session_state.get(textarea_key, "").strip()
            if len(text.split()) < 50:
                st.warning("Please write at least 50 words before continuing.")
                st.stop()

            # Final merge before leaving the phase
            merge_autosave_into_log()

            # Ensure at least one entry exists (fallback if JS never fired)
            if not st.session_state.writing_keystroke_log:
                ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                st.session_state.writing_keystroke_log[ts] = text

            st.session_state.writing_text_final = text
            st.session_state.phase = 9.3
            st.rerun()

    # ── GROUP A ──────────────────────────────────────────────────────────────
    if group == "A":
        st.markdown("## Your Writing")
        _writing_ui("writing_text_A", height=260)

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
            _writing_ui("writing_text_B", height=300)

        with col_chat:
            st.markdown("## 🤖 AI Writing Assistant")
            st.caption("Optional — use for ideas, feedback, or drafting.")

            for msg in st.session_state.writing_llm_exchanges:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            if st.session_state.writing_pending_msg:
                pending = st.session_state.writing_pending_msg
                st.session_state.writing_llm_exchanges.append({"role": "user", "content": pending})
                with st.chat_message("user"):
                    st.markdown(pending)
                st.session_state.writing_pending_msg = None

                chat = st.session_state.writing_chat
                with st.chat_message("assistant"):
                    stream = chat.send_message(pending, stream=True)
                    reply  = st.write_stream(chunk.text for chunk in stream)

                st.session_state.writing_llm_exchanges.append({"role": "assistant", "content": reply})
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
    st.markdown("*1 = Not at all — 7 = Completely*")
    recogn = likert_7(key="writing_post_recogn", labels=LIKERT_LABELS_RECOGN)

    st.markdown("---")

    st.markdown(
        f"**After writing, how appropriate or inappropriate do you consider "
        f"the action of: \"{WRITING_FIXED_NORM}\"?**"
    )
    st.markdown("*1 = Extremely inappropriate — 7 = Extremely appropriate*")
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
    st.markdown("**Final written text:**")
    st.text_area("", value=st.session_state.writing_text_final, height=160,
                 disabled=True, label_visibility="collapsed")
    final_words = len(st.session_state.writing_text_final.split()) if st.session_state.writing_text_final else 0
    st.write(f"Word count: **{final_words}**")

    n_entries = len(st.session_state.writing_keystroke_log)
    st.markdown(f"**Change log** — {n_entries} snapshots (1-per-second autosave):")
    st.json(st.session_state.writing_keystroke_log)

    if st.session_state.writing_group == "B":
        st.markdown("**AI chat exchanges:**")
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
        "writing_keystroke_log":   st.session_state.writing_keystroke_log,
        "writing_snapshot_count":  len(st.session_state.writing_keystroke_log),
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
        json.dumps(st.session_state.writing_keystroke_log, ensure_ascii=False),
        json.dumps(st.session_state.writing_llm_exchanges, ensure_ascii=False),
        str(st.session_state.writing_post_recogn),
        str(st.session_state.writing_post_appropriate),
    ]
    col_names = ["col12 involvement", "col13 threat", "col14 source",
                 "col33 writing_group", "col34 keystroke_log",
                 "col35 llm_exchanges", "col36 post_recogn", "col37 post_appropriate"]
    for name, val in zip(col_names, sheet_row):
        with st.expander(name):
            st.code(val, language="json")

    st.markdown("---")
    if st.button("🔄 Restart test"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()