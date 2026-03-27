import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import os
import time
import random
import string
from collections import defaultdict

import vertexai
from vertexai.generative_models import GenerativeModel, ChatSession
import threading

from streamlit_autorefresh import st_autorefresh
from captcha.image import ImageCaptcha

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Online Discussion Study",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# LOAD JSON FILES
# ============================================================================
def load_json(path):
    if not os.path.exists(path):
        st.error(f"Missing file: {path}")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPTS = load_json("prompts.json")
NORMS   = load_json("norms.json")

# ============================================================================
# WRITING TASK CONSTANTS
# ============================================================================

LIKERT_LABELS_RECOGN = [
    "Not at all", "Slightly", "Somewhat", "Moderately", "Very", "Mostly", "Completely",
]
LIKERT_LABELS_APPROP_WRITING = [
    "Extremely\ninappropriate", "Very\ninappropriate", "Somewhat\ninappropriate",
    "Neither inappropriate or appropriate", "Somewhat\nappropriate", "Very\nappropriate", "Extremely\nappropriate",
]

# ============================================================================
# GOOGLE SHEETS — lazy (main sheet)
# ============================================================================
def get_sheet():
    if "gsheet" not in st.session_state:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        st.session_state.gsheet = (
            gspread.authorize(creds)
            .open_by_url(st.secrets["google_sheet_url"])
            .sheet1
        )
    return st.session_state.gsheet

# ============================================================================
# GOOGLE SHEETS — writing sheet (separate worksheet index 1)
# ============================================================================
def get_writing_sheet():
    if "writing_gsheet" not in st.session_state:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        st.session_state.writing_gsheet = (
            gspread.authorize(creds)
            .open_by_url(st.secrets["google_sheet_url"])
            .get_worksheet(1)
        )
    return st.session_state.writing_gsheet

def save_to_writing_sheet(row):
    get_writing_sheet().append_row(row, value_input_option="RAW")

def check_prolific_id_exists(prolific_id):
    values = get_sheet().col_values(1)
    return prolific_id.lower() in [v.lower() for v in values[1:]]

def get_least_used_combination():
    sheet  = get_sheet()
    data   = sheet.get_all_values()
    counts = defaultdict(int)
    for p in PROMPTS:
        for n in NORMS:
            counts[(p, n)] = 0
    for row in data[1:]:
        if len(row) >= 3 and (row[1], row[2]) in counts:
            counts[(row[1], row[2])] += 1
    min_count = min(counts.values())
    return random.choice([k for k, v in counts.items() if v == min_count])

def save_to_google_sheets(row):
    get_sheet().append_row(row, value_input_option="RAW")

# ============================================================================
# SAVE EXCLUDED PARTICIPANTS
# ============================================================================
def save_excluded_participant(reason: str):
    """Save a partial row for participants excluded mid-study."""
    if st.session_state.get("excluded_data_saved"):
        return
    try:
        row = [
            st.session_state.get("prolific_id", ""),
            st.session_state.get("prompt_key", ""),
            st.session_state.get("norm_key", ""),
            json.dumps(st.session_state.get("initial_opinion", {}),  ensure_ascii=False),
            json.dumps(st.session_state.get("opinions_others", {}),  ensure_ascii=False),
            json.dumps(st.session_state.get("messages", []),         ensure_ascii=False),
            str(st.session_state.get("att_check_response_saved", "")),
            str(st.session_state.get("att_check_passed", "")),
            "",  # final_opinion — not reached
            "",  # opinions_others_final — not reached
            "",  # tightness_responses — not reached
            "",  # tightness_open
            "",  # involvement_responses
            "",  # threat_responses
            "",  # source_responses
            "",  # purpose_text
            "",  # age
            "",  # uk_location
            "",  # gender
            "",  # student
            "",  # education
            "",  # politics
            "",  # social_ladder
            str(st.session_state.get("engagement_text_saved", "")),
            str(st.session_state.get("engagement_word_count", 0)),
            "",  # final_comments
            str(st.session_state.get("parallel_engagement_time",    "")),
            str(st.session_state.get("sequential_engagement_time",  "")),
            str(st.session_state.get("interaction_engagement_time", "")),
            str(sum(1 for m in st.session_state.get("messages", []) if m["role"] == "user")),
            "",  # user_word_count
            "",  # total_duration
            datetime.now().isoformat(),
            f"EXCLUDED: {reason}",  # writing_group field repurposed as exclusion tag
            "", "", "", "", "", "",
        ]
        save_to_google_sheets(row)
        st.session_state.excluded_data_saved = True
    except Exception:
        pass  # silent — don't block the termination screen

# ============================================================================
# VERTEX AI / GEMINI CLIENT — lazy
# ============================================================================
def get_gemini_model() -> GenerativeModel:
    if "gemini_model" not in st.session_state:
        vertex_creds = Credentials.from_service_account_info(
            st.secrets["gcp_vertex_account"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        vertexai.init(
            project=st.secrets["gcp_project_id"],
            location=st.secrets.get("gcp_location", "europe-west9"),
            credentials=vertex_creds,
        )
        st.session_state.gemini_model = GenerativeModel("gemini-2.5-flash-lite")
    return st.session_state.gemini_model


def preload_gemini_in_background():
    def _init():
        try:
            get_gemini_model()
        except Exception:
            pass
    if not st.session_state.get("gemini_preload_started"):
        st.session_state.gemini_preload_started = True
        threading.Thread(target=_init, daemon=True).start()


def precompute_greeting_in_background():
    def _generate():
        try:
            prompt_data   = PROMPTS[st.session_state.prompt_key]
            norm_data     = NORMS[st.session_state.norm_key]
            initial_val   = st.session_state.initial_opinion.get(norm_data["title"], 50)
            system_prompt = (
                prompt_data["system_prompt_template"]
                .replace("{NORM_DESCRIPTION}", norm_data["title"])
                .replace("{INITIAL_OPINION}", str(initial_val))
            )
            model = get_gemini_model()
            chat  = model.start_chat()
            response = chat.send_message(
                f"{system_prompt}\n\nStart the discussion now. Open the topic."
            )
            st.session_state.precomputed_chat          = chat
            st.session_state.precomputed_greeting      = response.text
            st.session_state.precomputed_system_prompt = system_prompt
        except Exception:
            pass

    if not st.session_state.get("greeting_precompute_started"):
        st.session_state.greeting_precompute_started = True
        threading.Thread(target=_generate, daemon=True).start()

def get_or_rebuild_chat(system_prompt: str) -> ChatSession:
    if "gemini_chat" in st.session_state:
        return st.session_state.gemini_chat
    model = get_gemini_model()
    chat  = model.start_chat()
    st.session_state.gemini_chat = chat
    return chat

# ============================================================================
# SCROLL TO TOP
# ============================================================================
def scroll_to_top():
    unique = int(time.time() * 1000)
    st.components.v1.html(
        f"""
        <script id="scroll_{unique}">
            (function() {{
                function tryScroll() {{
                    let main = window.parent.document.querySelector('.main');
                    if (main) main.scrollTop = 0;
                    let appView = window.parent.document.querySelector('[data-testid="stAppViewBlockContainer"]');
                    if (appView) appView.scrollTop = 0;
                    let stMain = window.parent.document.querySelector('[data-testid="stMain"]');
                    if (stMain) stMain.scrollTop = 0;
                    window.parent.scroll(0, 0);
                }}
                tryScroll();
                setTimeout(tryScroll, 100);
                setTimeout(tryScroll, 300);
            }})();
        </script>
        """,
        height=0,
    )

def scroll_to_top_on_phase_entry():
    current_phase = st.session_state.phase
    if st.session_state.get("last_scrolled_phase") != current_phase:
        scroll_to_top()
        st.session_state.last_scrolled_phase = current_phase

# ============================================================================
# LEAVE WARNING (refresh / back button)
# ============================================================================
def inject_leave_warning():
    """Show a browser confirmation dialog if the user tries to leave/refresh."""
    st.components.v1.html(
        """
        <script>
        (function() {
            function attachWarning(win) {
                if (!win) return;
                if (win._leaveWarningAttached) return;
                win._leaveWarningAttached = true;
                win.addEventListener('beforeunload', function(e) {
                    e.preventDefault();
                    e.returnValue = 'If you leave or refresh this page, all your progress will be lost and you will have to start over.';
                    return 'If you leave or refresh this page, all your progress will be lost and you will have to start over.';
                });
            }
            attachWarning(window);
            try { attachWarning(window.parent); } catch(e) {}
            try { attachWarning(window.top); }    catch(e) {}
        })();
        </script>
        """,
        height=0,
    )

# ============================================================================
# [CHANGE 4] WEBSOCKET HEARTBEAT — prevents session timeout due to inactivity
# ============================================================================
def inject_heartbeat():
    """
    Sends a no-op ping to the Streamlit WebSocket every 4 minutes so that
    Streamlit Cloud does not close the session due to inactivity.
    Safe to call on every render — the interval is cleared and reset each time
    to avoid stacking multiple intervals across reruns.
    """
    st.components.v1.html(
        """
        <script>
        (function() {
            // Clear any existing heartbeat interval to avoid duplicates across reruns
            if (window._heartbeatIntervalId != null) {
                clearInterval(window._heartbeatIntervalId);
                window._heartbeatIntervalId = null;
            }

            function sendHeartbeat() {
                try {
                    // Find the Streamlit WebSocket and send a benign ping
                    // Streamlit exposes its websocket on window.parent
                    let ws = null;
                    try { ws = window.parent._streamlitWebsocket; } catch(e) {}

                    // Fallback: trigger a tiny DOM mutation that keeps the
                    // connection alive without causing a full rerun.
                    // We write to a hidden element if the WS isn't accessible.
                    let sentinel = window.parent.document.getElementById('_heartbeat_sentinel');
                    if (!sentinel) {
                        sentinel = window.parent.document.createElement('div');
                        sentinel.id = '_heartbeat_sentinel';
                        sentinel.style.display = 'none';
                        window.parent.document.body.appendChild(sentinel);
                    }
                    sentinel.setAttribute('data-ts', Date.now());
                } catch(e) {
                    // Silently ignore cross-origin errors
                }
            }

            // Fire immediately, then every 4 minutes (240 000 ms)
            sendHeartbeat();
            window._heartbeatIntervalId = setInterval(sendHeartbeat, 240000);
        })();
        </script>
        """,
        height=0,
    )

# ============================================================================
# LIKERT-7 HELPERS
# ============================================================================
LIKERT_LABELS = [
    "Extremely inappropriate", "Very inappropriate", "Somewhat inappropriate",
    "Neither inappropriate or appropriate", "Somewhat appropriate", "Very appropriate", "Extremely appropriate",
]

def likert_7(key, labels=None):
    if labels is None:
        labels = LIKERT_LABELS
    selected = st.session_state.get(key)
    cols = st.columns(7)
    for j, label in enumerate(labels):
        val = j + 1
        with cols[j]:
            btn_type = "primary" if selected == val else "secondary"
            if st.button(label, key=f"{key}_btn_{val}",
                         use_container_width=True, type=btn_type):
                st.session_state[key] = val
                st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)
    return st.session_state.get(key)

def render_7pt_item(label, key):
    st.markdown(f"**{label}**")
    cols     = st.columns(7)
    selected = st.session_state.get(key)
    scale_labels = [
        "Totally\ndisagree", "Mostly\ndisagree", "Somewhat\ndisagree",
        "Neither inappropriate or appropriate", "Somewhat\nagree", "Mostly\nagree", "Totally\nagree",
    ]
    for j in range(1, 8):
        with cols[j - 1]:
            if st.button(scale_labels[j - 1], key=f"{key}_{j}", use_container_width=True,
                         type="primary" if selected == j else "secondary"):
                st.session_state[key] = j
                st.rerun()
    st.markdown("")

# ============================================================================
# AUTOSAVE JS HELPERS
# ============================================================================
AUTOSAVE_SINK_LABEL    = "autosave_json_sink"
AUTOSAVE_TRIGGER_LABEL = "autosave_trigger"

def inject_autosave_js():
    st.markdown(f"""
<script>
(function() {{
    window._ksLog = window._ksLog || {{}};
    if (window._autosaveIntervalId != null) {{
        clearInterval(window._autosaveIntervalId);
        window._autosaveIntervalId = null;
    }}
    let lastText   = null;
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


def _compute_duration_seconds() -> int:
    try:
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        t0  = datetime.strptime(st.session_state.writing_phase_start, fmt)
        t1  = datetime.strptime(st.session_state.writing_phase_end,   fmt)
        return int((t1 - t0).total_seconds())
    except Exception:
        return -1

# ============================================================================
# CAPTCHA HELPER
# ============================================================================
CAPTCHA_LENGTH  = 5
CAPTCHA_WIDTH   = 200
CAPTCHA_HEIGHT  = 150
CAPTCHA_MAX_ATTEMPTS = 3

def render_captcha_phase():
    """
    Renders the CAPTCHA screen. Returns True if the user has already passed,
    False if they are still on this screen.
    After CAPTCHA_MAX_ATTEMPTS failures the participant is sent to phase -1.
    """
    if st.session_state.get("captcha_passed"):
        return True

    # Initialise attempt counter
    if "captcha_attempts" not in st.session_state:
        st.session_state.captcha_attempts = 0

    # Already exceeded max attempts → redirect to exclusion
    if st.session_state.captcha_attempts >= CAPTCHA_MAX_ATTEMPTS:
        st.session_state.excluded_reason = "failed_captcha"
        st.session_state.phase = -1
        st.rerun()

    remaining_attempts = CAPTCHA_MAX_ATTEMPTS - st.session_state.captcha_attempts

    st.markdown("## Human Verification")
    st.markdown("Please complete the verification below to continue.")

    if remaining_attempts < CAPTCHA_MAX_ATTEMPTS:
        st.warning(
            f"Incorrect code. Please try again. "
            f"You have **{remaining_attempts}** attempt{'s' if remaining_attempts != 1 else ''} remaining."
        )

    # Generate a captcha string once per attempt
    if "captcha_text" not in st.session_state:
        st.session_state.captcha_text = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=CAPTCHA_LENGTH)
        )

    image = ImageCaptcha(width=CAPTCHA_WIDTH, height=CAPTCHA_HEIGHT)
    data  = image.generate(st.session_state.captcha_text)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(data)
    with col2:
        user_input = st.text_input(
            "Enter the characters shown in the image:",
            key=f"captcha_input_{st.session_state.captcha_attempts}"
        )

    if st.button("Verify"):
        entered = (
            st.session_state.get(f"captcha_input_{st.session_state.captcha_attempts}", "")
            .replace(" ", "").strip().upper()
        )
        if entered == st.session_state.captcha_text.upper():
            st.session_state.captcha_passed = True
            del st.session_state["captcha_text"]
            st.rerun()
        else:
            st.session_state.captcha_attempts += 1
            if "captcha_text" in st.session_state:
                del st.session_state["captcha_text"]
            # Check immediately if now over the limit
            if st.session_state.captcha_attempts >= CAPTCHA_MAX_ATTEMPTS:
                st.session_state.excluded_reason = "failed_captcha"
                st.session_state.phase = -1
            st.rerun()

    return False

# ============================================================================
# PROLIFIC ID
# ============================================================================
prolific_id = st.query_params.get("PROLIFIC_PID", "")
if not prolific_id:
    st.error("Please access this study via Prolific to continue.")
    st.stop()

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
if "session_initialized" not in st.session_state:
    st.session_state.update({
        "session_initialized":          True,
        "prolific_id":                  prolific_id,
        "phase":                        0,
        "messages":                     [],
        "greeting_sent":                False,
        "data_saved":                   False,
        "pending_user_message":         None,
        "page_load_time":               time.time(),
        "engagement_first_interaction": None,
        "gemini_chat":                  None,
        "system_prompt_cache":          None,
        "last_scrolled_phase":          None,
        "captcha_passed":               False,
        "excluded_reason":              None,
        "excluded_data_saved":          False,
        # Writing task
        "writing_word_min":             random.choice([50, 75]),
        "writing_group_raw":            random.choices(["A", "B"]),
        "writing_group":                None,
        "writing_norm":                 None,
        "writing_text_final":           "",
        "writing_keystroke_log":        {},
        "writing_last_saved_text":      None,
        "writing_llm_streaming":        False,
        "writing_llm_output":           "",
        "writing_llm_exchanges":        [],
        "writing_post_recogn":          None,
        "writing_post_appropriate":     None,
        "writing_data_saved":           False,
        "writing_pending_msg":          None,
        "writing_chat_initialized":     False,
        "writing_chat":                 None,
        "writing_phase_start":          None,
        "writing_phase_end":            None,
        "involvement_responses":        {},
        "threat_responses":             {},
        "source_responses":             {},
    })

if st.session_state.get("writing_group") is None:
    raw  = st.session_state.writing_group_raw
    wmin = st.session_state.writing_word_min
    st.session_state.writing_group = f"{raw}{wmin}"
WORD_MIN = st.session_state.writing_word_min

# ============================================================================
# SCROLL TO TOP ON FIRST ENTRY INTO CURRENT PHASE
# ============================================================================
scroll_to_top_on_phase_entry()

# ============================================================================
# LEAVE WARNING — active for all phases between 1 and 13 inclusive
# (not on consent/intro screens, not on termination, not after submission)
# ============================================================================
_active_phases = { 0.75, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9.1, 9.2, 9.3, 10, 11, 12, 13, 14}
if st.session_state.phase in _active_phases:
    inject_leave_warning()

# ============================================================================
# [CHANGE 4] HEARTBEAT — active for all study phases to prevent timeout
# ============================================================================
if st.session_state.phase in _active_phases:
    inject_heartbeat()

# ============================================================================
# PHASE -1 — EARLY TERMINATION
# ============================================================================
if st.session_state.phase == -1:

    # Determine exclusion reason (set once)
    if not st.session_state.get("excluded_reason"):
        gdpr_val    = st.session_state.get("gdpr_consent_radio", "")
        consent_val = st.session_state.get("consent_radio", "")
        quality_val = st.session_state.get("quality_radio", "")

        if gdpr_val and not gdpr_val.startswith("Yes"):
            reason = "refused_gdpr_consent"
        elif consent_val == "I do not agree":
            reason = "refused_study_consent"
        elif quality_val in ("I will not provide my best answers", "I can't promise either way"):
            reason = "failed_quality_check"
        elif st.session_state.get("att_check_passed") is False:
            reason = "failed_attention_check"
        elif st.session_state.get("excluded_reason") == "failed_captcha":
            reason = "failed_captcha"
        else:
            reason = "unknown"
        st.session_state.excluded_reason = reason

    # Save once, silently
    save_excluded_participant(st.session_state.excluded_reason)

    st.markdown("## Thank you for your time.")
    st.markdown(
        "Unfortunately, your answer makes it impossible for us to include you in this study. "
        "Thank you for your time. You may now close this window."
    )
    st.stop()

# ============================================================================
# PHASE 0 — GDPR INFORMED CONSENT
# [CHANGE 1] Full text collapsed into an expander; only a summary is shown
#            by default so the page is less overwhelming.
# ============================================================================
elif st.session_state.phase == 0:
    st.markdown("## Informed Consent — Data Protection Information")
    st.markdown(
        "You are invited to participate in a research study conducted by the **Institute for Cognitive "
        "Science and Technologies (ISTC)** of the National Research Council and **Sapienza University of Rome**.\n\n"
        "Your data will be treated in full compliance with **GDPR 2016/679**. "
        "Participation is **voluntary** and you may withdraw at any time within 3 years by contacting "
        "**jacopo.nudo@uniroma1.it** with your Prolific ID."
    )

    with st.expander("📄 Read the full Data Protection Information"):
        st.markdown(
            "You are accessing the study by logging in with your Prolific ID. This is the only information "
            "researchers will obtain from you via Prolific. The data you share with Prolific are treated in "
            "full compliance with GDPR. The study will be carried out as an online survey programmed in Streamlit. "
            "All personal data about you will be collected through the survey from you — we do not obtain "
            "information about you from any other sources. Your personal data will not be used for automated "
            "decision-making including profiling."
        )

        st.markdown("### Data")
        st.markdown(
            "To carry out this processing operation the following categories of personal data may be processed:\n\n"
            "- **Socio-demographic information** (age, gender, educational level, income)\n"
            "- **Responses** to the questions included in the survey\n\n"
            "In addition, the survey tool may register:\n\n"
            "- **IP address and geolocation** of the respondent.\n\n"
            "These data will **not** be downloaded or processed by ISTC or Sapienza University of Rome and "
            "will remain on the server of the survey tool for as long as required (see Data Retention below).\n\n"
            "You may spontaneously provide other non-requested personal data in open-text replies. "
            "The Data Controller does not request nor expect special categories of data under Article 10(1) "
            "of Regulation 2018/1725 (data revealing racial or ethnic origin, political opinions, religious "
            "or philosophical beliefs, trade union membership, genetic/biometric data, health data, or data "
            "concerning sex life or sexual orientation). Any spontaneous inclusion of these types of data is "
            "the responsibility of the data subject and constitutes explicit consent under Article 10(2)(a) "
            "of Regulation 2018/1725.\n\n"
            "All data collected will be treated in accordance with **GDPR 2016/679** and the analogous "
            "Italian regulation (Legislative Decree 30 June 2003, n. 196)."
        )

        st.markdown("### Role and Contacts")
        st.markdown(
            "- **Data Controller** (Art. 13, par. 1, letter a): Institute for Cognitive Science and "
            "Technologies, ISTC-CNR — direzione.istc@istc.cnr.it — Tel: 06 44595246\n"
            "- **Data Protection Officer** (Art. 13, par. 1, letter b): rpd@cnr.it"
        )

        st.markdown("### Purposes for Data Processing, Transfer and Retention")
        st.markdown(
            "- **Purpose** (Art. 13, par. 1, letter c): Data collected will be used exclusively for the "
            "research purposes described above.\n"
            "- **Recipients** (Art. 13, par. 1, letter e): Access is reserved exclusively for researchers "
            "authorised by the Director of ISTC-CNR. The list is available at jacopo.nudo@uniroma1.it.\n"
            "- **Data transfer to third countries** (Art. 13, par. 1, letter f): Data will **not** be "
            "transferred to third countries.\n"
            "- **Data retention** (Art. 13, par. 2, letter a): Data will be kept on a secure server at Google. "
            "Access by Google is restricted and requires authorisation.\n"
            "- **Processing for other purposes** (Art. 13, par. 3): Data will be used exclusively for the "
            "research purposes described above."
        )

        st.markdown("### Your Rights")
        st.markdown(
            "- **Right of access, rectification, cancellation or limitation** (Art. 13, par. 2, letter b): "
            "You may request access to data at any time within 3 years of processing and have the right to "
            "have it removed, rectified, or restricted, including data portability.\n"
            "- **Right to withdraw consent** (Art. 13, par. 2, letter c): You may revoke your consent within "
            "3 years by contacting us and asking not to use your data.\n"
            "- **Right to lodge a complaint** (Art. 13, par. 2, letter d): Within 3 years of the treatment "
            "you may lodge a complaint with the Data Protection Authority.\n"
            "- **Providing personal data** (Art. 13, par. 2, letter e): By participating you accept all the "
            "purposes described above and provide the Data Controller with your personal data.\n\n"
            "To exercise your rights, write to **jacopo.nudo@uniroma1.it** including your Prolific ID."
        )

        st.markdown("### Legal Basis")
        st.markdown(
            "Legal basis (Art. 9, par. 2, letter a): the processing is legally authorised with the "
            "explicit acceptance of this Informed Consent."
        )

    st.markdown("---")
    st.markdown("### Declaration")
    st.markdown(
        "By selecting **'Yes, I agree'** below, I declare that:\n\n"
        "- I have read and understood the contents of this Information Sheet;\n"
        "- I have been informed about the objectives of the study and have had enough time to make my decision;\n"
        "- I understand that my participation is **voluntary** and that I am free to withdraw at any time "
        "without giving any explanation, and that my data will not be used if I withdraw;\n"
        "- I have been informed that data collected will remain **anonymous and protected** according to "
        "GDPR n. 2016/679 and Legislative Decree 30 June 2003 n. 196;\n"
        "- I consent to the processing of personal data for the scientific study purposes described above "
        "and to the publication of anonymous results for scientific purposes;\n"
        "- I am aware that data recorded during the study can only be viewed by specifically authorised "
        "personnel and allow these persons to access data relevant to this study."
    )

    gdpr_consent = st.radio(
        "Your response:",
        options=[
            "Yes, I agree with the above stated terms and want to participate in this survey",
            "No, I do not want to participate in this survey",
        ],
        index=None,
        key="gdpr_consent_radio",
    )

    if gdpr_consent is not None:
        if st.button("Continue"):
            if gdpr_consent.startswith("Yes"):
                st.session_state.phase = 0.25
                st.rerun()
            else:
                st.session_state.phase = -1
                st.rerun()

# ============================================================================
# PHASE 0.25 — STUDY CONSENT FORM
# ============================================================================
elif st.session_state.phase == 0.25:
    preload_gemini_in_background()
    st.markdown("## Thank you for joining our study!")

    st.markdown("""
**Before proceeding, please read the information below.**

**Aim of the Study**  
You are invited to participate in a study on social norms. The goal is to understand how people evaluate everyday behaviors and how they discuss these topics with an advanced AI.

**What will I be asked to do?**  
You will complete a short survey about social norms and then engage in a brief conversation with an AI based on your responses.  
The study takes approximately 12 minutes. Some questions include bonus payments (£0.50 each, up to £1 total).

**Voluntary participation**  
Your participation is voluntary. You may stop at any time by closing the browser. After completing the study, withdrawal will no longer be possible due to data anonymization.

**Risks and benefits**  
There are no direct risks. Some questions may feel sensitive; you may skip any question you prefer not to answer.

**Contact**  
For any questions about the study, please contact: **jacopo.nudo@uniroma1.it**

By clicking "I agree", you confirm that you have read and understood this information and agree to participate.
""")

    consent = st.radio(
        "Your response:",
        options=["I agree", "I do not agree"],
        index=None,
        key="consent_radio"
    )

    if consent == "I agree":
        if st.button("Continue"):
            try:
                if check_prolific_id_exists(prolific_id):
                    st.error("This Prolific ID has already completed the study.")
                    st.stop()
            except Exception as e:
                st.error(f"Could not verify Prolific ID. Please try again or contact us. Error: {e}")
                st.stop()
            st.session_state.phase = 0.5
            st.rerun()

    elif consent == "I do not agree":
        if st.button("Continue"):
            st.session_state.phase = -1
            st.rerun()

# ============================================================================
# PHASE 0.5 — DATA QUALITY CHECK
# ============================================================================
elif st.session_state.phase == 0.5:
    st.markdown("We care about the quality of our survey data. For us to fully understand your opinions, it is important that you provide careful answers to each question in this survey.")
    st.markdown(
        "Please note that this survey contains **attention check questions**. "
        "These are simple questions designed to verify that participants are reading carefully. "
        "**If you do not answer them correctly, you will be excluded from the study, "
        "the survey will end immediately, and you will not receive any payment.**"
    )
    st.markdown("**Do you commit to thoughtfully provide your best answers to the questions in this survey?**")

    quality = st.radio(
        "Your answer:",
        options=[
            "I will try to provide my best answers",
            "I will not provide my best answers",
            "I can't promise either way",
        ],
        index=None,
        key="quality_radio"
    )

    if quality == "I will try to provide my best answers":
        if st.button("Continue"):
            st.session_state.phase = 0.75   # → CAPTCHA next
            st.rerun()
    elif quality in ("I will not provide my best answers", "I can't promise either way"):
        if st.button("Continue"):
            st.session_state.phase = -1
            st.rerun()

# ============================================================================
# PHASE 0.75 — CAPTCHA VERIFICATION
# ============================================================================
elif st.session_state.phase == 0.75:
    passed = render_captcha_phase()
    if passed:
        st.session_state.phase = 1
        st.rerun()
    # render_captcha_phase handles st.stop() implicitly by not advancing

# ============================================================================
# PHASE 1 — BACKGROUND QUESTION
# ============================================================================
elif st.session_state.phase == 1:
    st.markdown("Please answer the question below in a few sentences. There is no right or wrong answer.")
    st.markdown("**If you could change one thing about the world, what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.**")

    def _engagement_callback():
        if st.session_state.engagement_first_interaction is None:
            st.session_state.engagement_first_interaction = time.time()

    st.text_area(
        "Your answer:",
        height=180,
        key="engagement_text",
        on_change=_engagement_callback,
        label_visibility="collapsed"
    )

    if st.button("Continue"):
        response = st.session_state.get("engagement_text", "").strip()
        if not response:
            st.warning("Please provide a response before continuing.")
            st.stop()
        now = time.time()
        st.session_state.engagement_text_saved       = response
        st.session_state.engagement_word_count       = len(response.split())
        st.session_state.parallel_engagement_time    = now - st.session_state.page_load_time
        st.session_state.sequential_engagement_time  = now - st.session_state.page_load_time
        st.session_state.interaction_engagement_time = (
            now - st.session_state.engagement_first_interaction
            if st.session_state.engagement_first_interaction else None
        )
        st.session_state.phase = 2
        st.rerun()

# ============================================================================
# PHASE 2 — INITIAL APPROPRIATENESS RATINGS
# ============================================================================
elif st.session_state.phase == 2:
    if "prompt_key" not in st.session_state:
        prompt_key, norm_key = get_least_used_combination()
        st.session_state.prompt_key = prompt_key
        st.session_state.norm_key   = norm_key
        st.session_state.start_time = time.time()

    if "sampled_norms" not in st.session_state:
        norm_data   = NORMS[st.session_state.norm_key]
        other_norms = [v for k, v in NORMS.items() if k != st.session_state.norm_key]
        sampled     = random.sample(other_norms, min(4, len(other_norms))) + [norm_data]
        random.shuffle(sampled)
        st.session_state.sampled_norms = sampled

        other_sampled = [n for n in sampled if n["title"] != norm_data["title"]]
        if other_sampled:
            st.session_state.writing_norm = random.choice(other_sampled)["title"]
        else:
            fallback_pool = [v for k, v in NORMS.items() if k != st.session_state.norm_key]
            st.session_state.writing_norm = (
                random.choice(fallback_pool)["title"] if fallback_pool else norm_data["title"]
            )

    if "phase2_index" not in st.session_state:
        st.session_state.phase2_index = 0
    if "initial_opinion" not in st.session_state:
        st.session_state.initial_opinion = {}

    i     = st.session_state.phase2_index
    norm  = st.session_state.sampled_norms[i]
    total = len(st.session_state.sampled_norms)

    st.markdown(f"*Question {i + 1} of {total}*")
    st.markdown("""From various sources in our everyday lives we have all developed a subjective "impression" or "feeling" for the appropriateness of any given behavior in a particular situation. In this study, we are interested in your judgment of the appropriateness of some particular behaviors in some particular settings.

Your task in each case is simply to rate, on a 7-point scale from 1 (completely inappropriate) to 7 (completely appropriate), the appropriateness of the particular behavior in the situation that is given.""")

    st.markdown(f"**How appropriate or inappropriate is the action of: '{norm['title']}'?**")
    val = likert_7(key=f"likert_p2_{i}")

    if st.button("Continue"):
        if val is None:
            st.warning("Please select a response before continuing.")
            st.stop()
        st.session_state.initial_opinion[norm['title']] = val
        if i + 1 < total:
            st.session_state.phase2_index += 1
            st.rerun()
        else:
            st.session_state.phase = 3
            st.rerun()

# ============================================================================
# PHASE 3 — EXPECTED OTHERS' RATINGS
# ============================================================================
elif st.session_state.phase == 3:
    if "phase3_index" not in st.session_state:
        st.session_state.phase3_index = 0
    if "opinions_others" not in st.session_state:
        st.session_state.opinions_others = {}

    i     = st.session_state.phase3_index
    norm  = st.session_state.sampled_norms[i]
    total = len(st.session_state.sampled_norms)

    st.markdown(f"*Question {i + 1} of {total}*")

    if i == 0:
        st.markdown("---")
        st.markdown("## Now: What do others think?")
        st.markdown("In this next section, we shift from asking about **your own opinion** to asking about **how you think other people responded**.")
        st.markdown("---")

    st.markdown("""We will now ask you what you think the other participants of this study from the UK have on average rated the appropriateness of these behaviors on a 7-point scale from 1 (completely inappropriate) to 7 (completely appropriate).

We will calculate the mean responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct (±0.5), you will receive an additional bonus of £0.50. Only one behavior will be randomly selected for payment.""")

    st.markdown(f"**What rating do you think other UK participants gave for the action of: '{norm['title']}'?**")
    st.markdown("Other respondents' average appropriateness rating:")
    val = likert_7(key=f"likert_p3_{i}")

    if st.button("Continue"):
        if val is None:
            st.warning("Please select a response before continuing.")
            st.stop()
        st.session_state.opinions_others[norm['title']] = val
        if i + 1 < total:
            st.session_state.phase3_index += 1
            st.rerun()
        else:
            st.session_state.phase = 4
            st.rerun()

# ============================================================================
# PHASE 4 — INSTRUCTIONS FOR CONVERSATION
# ============================================================================
elif st.session_state.phase == 4:
    st.markdown("""Now, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The purpose of this dialogue is to see how humans and AI interact. Please be open and honest in your responses. Remember that the AI is neutral and non-judgmental, and your participation is confidential. When the conversation begins, you should see an orange robot icon indicating it's generating responses. It can sometimes take up to 30s. If you don't see any icons or if it's taking too long to generate responses, try refreshing the page. If you run into further issues, please let us know.

Please read each AI message thoroughly, and you may have to scroll down to read its full message. You will be asked some questions about your interaction. You will have to write at least 2 messages to the AI, up to a maximum of 10.

When the conversation is over, you should see a message at the bottom: **Scroll down and proceed to the next section.**""")

    precompute_greeting_in_background()

    if st.button("Start Conversation"):
        st.session_state.phase = 5
        st.rerun()

# ============================================================================
# PHASE 5 — CONVERSATION WITH GEMINI
# ============================================================================
elif st.session_state.phase == 5:
    prompt_data   = PROMPTS[st.session_state.prompt_key]
    norm_data     = NORMS[st.session_state.norm_key]
    initial_val   = st.session_state.initial_opinion.get(norm_data["title"], 50)
    system_prompt = (
        prompt_data["system_prompt_template"]
        .replace("{NORM_DESCRIPTION}", norm_data["title"])
        .replace("{INITIAL_OPINION}", str(initial_val))
    )
    st.session_state.system_prompt_cache = system_prompt

    if not st.session_state.greeting_sent:
        if st.session_state.get("precomputed_greeting"):
            st.session_state.gemini_chat = st.session_state.precomputed_chat
            greeting_text = st.session_state.precomputed_greeting
        else:
            with st.spinner("Starting conversation..."):
                model = get_gemini_model()
                chat  = model.start_chat()
                response = chat.send_message(
                    f"{system_prompt}\n\nStart the discussion now. Present the norm you would like to discuss about."
                )
                st.session_state.gemini_chat = chat
                greeting_text = response.text

        st.session_state.messages.append({
            "role":      "assistant",
            "content":   greeting_text,
            "timestamp": datetime.now().isoformat(),
        })
        st.session_state.greeting_sent = True
        st.rerun()

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    assistant_count = sum(1 for m in st.session_state.messages if m["role"] == "assistant")
    round_count     = max(0, assistant_count - 1)

    if user_input := st.chat_input("Type your response here"):
        st.session_state.pending_user_message = {
            "role":      "user",
            "content":   user_input,
            "timestamp": datetime.now().isoformat(),
        }
        st.rerun()

    if st.session_state.pending_user_message:
        user_msg = st.session_state.pending_user_message
        st.session_state.messages.append(user_msg)
        with st.chat_message("user"):
            st.markdown(user_msg["content"])
        st.session_state.pending_user_message = None

        if round_count < 10:
            chat = st.session_state.get("gemini_chat")
            if chat is None:
                model = get_gemini_model()
                chat  = model.start_chat()
                chat.send_message(
                    f"{system_prompt}\n\n"
                    "Continue the ongoing discussion. "
                    "Below is the conversation so far (for context only):\n\n"
                    + "\n".join(
                        f"{'User' if m['role']=='user' else 'You'}: {m['content']}"
                        for m in st.session_state.messages[:-1]
                    )
                )
                st.session_state.gemini_chat = chat

            with st.chat_message("assistant"):
                stream     = chat.send_message(user_msg["content"], stream=True)
                reply_text = st.write_stream(chunk.text for chunk in stream)

            st.session_state.messages.append({
                "role":      "assistant",
                "content":   reply_text,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            closing = (
                "Thank you for your thoughtful responses! "
                "The discussion is now complete. "
                "Please scroll down and proceed to the next section."
            )
            st.session_state.messages.append({
                "role":      "assistant",
                "content":   closing,
                "timestamp": datetime.now().isoformat(),
            })
        st.rerun()

    # ── End Discussion button — mirrors Phase 9.2 word-count gate ──────────
    user_msg_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
    enough_messages = user_msg_count >= 2

    st.markdown("---")
    if enough_messages:
        if st.button("End Discussion & Continue"):
            st.session_state.phase = 6
            st.rerun()
    else:
        remaining = 2 - user_msg_count
        st.button("End Discussion & Continue", disabled=True)

# ============================================================================
# PHASE 6 — ATTENTION CHECK
# [CHANGE 2] If prompt_key == "1" (neutral prompt), add "None of the above"
#            as a valid correct answer in addition to the norm title.
# ============================================================================
elif st.session_state.phase == 6:
    st.markdown("**Which of the following best describes the main topic discussed with the AI?**")

    # [CHANGE 2] Build option list; for neutral prompt add "None of the above" option
    is_neutral_prompt = (st.session_state.get("prompt_key") == "1")
    options = [n["title"] for n in st.session_state.sampled_norms] + ["None of the above / I don't remember"]
    st.radio("Select one:", options, index=None, key="att_check_response", label_visibility="collapsed")

    if st.button("Continue"):
        if not st.session_state.get("att_check_response"):
            st.warning("Please select an answer before continuing.")
            st.stop()

        chosen        = st.session_state.att_check_response
        correct_title = NORMS[st.session_state.norm_key]["title"]

        st.session_state.att_check_response_saved = chosen

        # [CHANGE 2] Neutral prompt: "None of the above" is also a passing answer
        if is_neutral_prompt:
            passed = (chosen == correct_title or chosen == "None of the above / I don't remember")
        else:
            passed = (chosen == correct_title)

        st.session_state.att_check_passed = passed

        if not passed:
            st.session_state.phase = -1
        else:
            st.session_state.phase = 7
        st.rerun()

# ============================================================================
# PHASE 7 — FINAL APPROPRIATENESS RATINGS
# ============================================================================
elif st.session_state.phase == 7:
    if "phase7_index" not in st.session_state:
        st.session_state.phase7_index = 0
    if "final_opinion" not in st.session_state:
        st.session_state.final_opinion = {}

    i     = st.session_state.phase7_index
    norm  = st.session_state.sampled_norms[i]
    total = len(st.session_state.sampled_norms)
    title = norm["title"]

    st.markdown(f"*Question {i + 1} of {total}*")
    st.markdown("We ask you again to rate, on a 7-point scale from 1 (completely inappropriate) to 7 (completely appropriate), the appropriateness of these behaviors.")
    st.markdown(f"**How appropriate or inappropriate is the action of: '{title}'?**")
    val = likert_7(key=f"likert_p7_{i}")

    if st.button("Continue"):
        if val is None:
            st.warning("Please select a response before continuing.")
            st.stop()
        st.session_state.final_opinion[title] = val
        if i + 1 < total:
            st.session_state.phase7_index += 1
            st.rerun()
        else:
            st.session_state.phase = 8
            st.rerun()

# ============================================================================
# PHASE 8 — FINAL EXPECTED OTHERS' RATINGS
# ============================================================================
elif st.session_state.phase == 8:
    if "opinions_others_final" not in st.session_state:
        st.session_state.opinions_others_final = {}

    norm_data = NORMS[st.session_state.norm_key]
    title     = norm_data["title"]

    st.markdown("---")
    st.markdown("## Now: What do others think?")
    st.markdown("In this next section, we shift again from asking about **your own opinion** to asking about **how you think other people responded**.")
    st.markdown("---")

    st.markdown(f"""We will now ask you what you think the other participants of this study from the UK have on average rated the appropriateness of one specific behavior on a 7-point scale from 1 (completely inappropriate) to 7 (completely appropriate).

Just like you, the other participants also had a conversation with an AI about this topic before being asked this question again. Please imagine that their opinion may have been influenced by that interaction as well.

We will calculate the mean responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct (±0.5), you will receive an additional bonus of £0.50.""")

    st.markdown(f"**What rating do you think other UK participants gave (after their AI conversation) for the action of: '{title}'?**")
    st.markdown("Other respondents' average appropriateness rating:")
    val = likert_7(key="likert_p8_0")

    if st.button("Continue"):
        if val is None:
            st.warning("Please select a response before continuing.")
            st.stop()
        st.session_state.opinions_others_final[title] = val
        st.session_state.phase = 9
        st.rerun()

# ============================================================================
# PHASE 9 — CONVERSATION PERCEPTION
# ============================================================================
elif st.session_state.phase == 9:
    involvement_items = [
        ("They got me involved.",       "involvement_0"),
        ("They seemed relevant to me.", "involvement_1"),
        ("They interested me.",         "involvement_2"),
    ]
    threat_items = [
        ("They tried to manipulate me.",            "threat_0"),
        ("They tried to pressure me.",              "threat_1"),
        ("They undermined my sense of self-worth.", "threat_2"),
        ("They made me feel less than capable.",    "threat_3"),
        ("They made me think I should change.",     "threat_4"),
    ]
    source_items = [
        ("Reliable",  "source_0"),
        ("Trusted",   "source_1"),
        ("Honest",    "source_2"),
        ("Competent", "source_3"),
        ("Expert",    "source_4"),
        ("Informed",  "source_5"),
    ]

    def _render_group(items, header):
        st.markdown(f"#### {header}")
        for label, key in items:
            render_7pt_item(label, key)

    st.markdown("Indicate your degree of agreement with the following statements.")
    st.markdown("*Scale: Totally disagree → Totally agree*")
    _render_group(involvement_items, "The messages I read during the conversation with the AI:")
    _render_group(threat_items,      "The messages I read during the conversation with the AI:")
    _render_group(source_items,      "To what extent the source of these messages is:")

    if st.button("Continue"):
        all_keys = [k for _, k in involvement_items + threat_items + source_items]
        missing  = [k for k in all_keys if not st.session_state.get(k)]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        st.session_state.involvement_responses = {l: st.session_state[k] for l, k in involvement_items}
        st.session_state.threat_responses      = {l: st.session_state[k] for l, k in threat_items}
        st.session_state.source_responses      = {l: st.session_state[k] for l, k in source_items}
        st.session_state.phase = 9.1
        st.rerun()

# ============================================================================
# PHASE 9.1 — WRITING TASK: INSTRUCTIONS
# ============================================================================
elif st.session_state.phase == 9.1:
    writing_norm = st.session_state.get("writing_norm", "")

    st.markdown("## Writing Task — Instructions")
    st.markdown("---")
    st.markdown(f"**Please write around {WORD_MIN} words expressing your personal perception of a specific social norm.**")
    st.markdown(
        "There is **no right or wrong answer**. Write freely — you can describe "
        "what you think about the norm, share a personal experience, or argue a position."
    )
    st.markdown("---")
    st.markdown("**The norm you will be writing about is:**")
    st.markdown(
        f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
        f"padding:14px 18px;border-radius:4px;font-size:1.1rem;font-style:italic;'>"
        f"\"{writing_norm}\"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if st.button("Start writing →"):
        st.session_state.writing_phase_start = datetime.utcnow().isoformat() + "Z"
        st.session_state.phase = 9.2
        st.rerun()

# ============================================================================
# PHASE 9.2 — WRITING TASK: WRITING SCREEN
# ============================================================================
elif st.session_state.phase == 9.2:

    merge_autosave_into_log()

    writing_norm = st.session_state.get("writing_norm", "")
    group        = st.session_state.writing_group

    def _writing_ui(textarea_key: str, height: int):
        st.markdown(
            f"**Please write around {WORD_MIN} words expressing your personal perception of the following norm:**"
        )
        st.markdown(
            f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
            f"padding:12px 16px;border-radius:4px;font-style:italic;margin-bottom:16px;'>"
            f"\"{writing_norm}\"</div>",
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

        current_text = st.session_state.get(textarea_key, "") or ""
        word_count   = len(current_text.split()) if current_text.strip() else 0
        enough_words = word_count >= WORD_MIN

        st.progress(min(word_count / WORD_MIN, 1.0))
        if enough_words:
            st.success(f"✅ **{word_count} words** — minimum reached! You can continue.")
        else:
            remaining = WORD_MIN - word_count
            st.info(f"📝 **{word_count} / {WORD_MIN} words** — write {remaining} more word{'s' if remaining != 1 else ''} to continue.")

        if enough_words:
            if st.button("Continue →", key=f"btn_{textarea_key}"):
                _save_and_advance(textarea_key, current_text)
        else:
            st.button("Continue →", key=f"btn_{textarea_key}", disabled=True)

    def _save_and_advance(textarea_key: str, text: str):
        merge_autosave_into_log()
        st.session_state.writing_phase_end = datetime.utcnow().isoformat() + "Z"

        log = st.session_state.writing_keystroke_log
        if st.session_state.writing_phase_start:
            log["__phase_start__"] = st.session_state.writing_phase_start
        log["__phase_end__"] = st.session_state.writing_phase_end

        if not any(k for k in log if not k.startswith("__")):
            log[datetime.utcnow().isoformat() + "Z"] = text

        st.session_state.writing_text_final    = text
        st.session_state.writing_keystroke_log = log
        st.session_state.phase = 9.3
        st.rerun()

    if group == "A":
        st.markdown("## Your Writing")
        _writing_ui("writing_text_A", height=260)

    else:
        if not st.session_state.writing_chat_initialized:
            model        = get_gemini_model()
            writing_chat = model.start_chat()
            writing_chat.send_message(
                "You are an assistant."
                "The user is in a research study and must write approximately 100 words "
                "expressing their personal view on the following social norm: "
                f"\"{writing_norm}\". "
                "Be prepared: the user will very likely ask you to write the full response on their behalf. "
                "If they do, write a natural, personal-sounding text of approximately 100 words. "
                "Structure the text as follows: "
                "- Start with 1-2 neutral, bland sentences that acknowledge the norm without strong opinion. "
                "- In the middle, include 1-2 sentences that are strongly critical of or opposed to the norm. "
                "- End with 1-2 neutral, bland sentences that soften the tone again, as if reflecting or stepping back. "
                "Do not ask questions or discuss the task — just write the text directly. "
            )
            st.session_state.writing_chat             = writing_chat
            st.session_state.writing_chat_initialized = True

        col_write, col_chat = st.columns([3, 2], gap="large")

        with col_write:
            st.markdown("## Your Writing")
            _writing_ui("writing_text_B", height=300)

        with col_chat:
            st.markdown("## 🤖 AI Writing Assistant")
            st.caption("Use this assistant however you like — for ideas, feedback, or drafting. It's completely optional.")

            for msg in st.session_state.writing_llm_exchanges:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            if st.session_state.writing_pending_msg:
                pending  = st.session_state.writing_pending_msg
                ts_sent  = datetime.utcnow().isoformat() + "Z"
                st.session_state.writing_llm_exchanges.append({
                    "role": "user", "content": pending, "timestamp": ts_sent,
                })
                with st.chat_message("user"):
                    st.markdown(pending)
                st.session_state.writing_pending_msg = None

                chat = st.session_state.writing_chat
                with st.chat_message("assistant"):
                    st.session_state.writing_llm_streaming = True
                    stream   = chat.send_message(pending, stream=True)
                    reply    = st.write_stream(chunk.text for chunk in stream)
                    ts_reply = datetime.utcnow().isoformat() + "Z"
                    st.session_state.writing_llm_streaming = False

                st.session_state.writing_llm_exchanges.append({
                    "role": "assistant", "content": reply, "timestamp": ts_reply,
                })
                st.session_state.writing_llm_output = reply
                st.rerun()

            llm_input = st.chat_input("Ask the AI for help…", key="writing_chat_input")
            if llm_input:
                st.session_state.writing_pending_msg = llm_input
                st.rerun()

# ============================================================================
# PHASE 9.3 — WRITING TASK: POST-WRITING QUESTIONNAIRE + SAVE TO WRITING SHEET
# ============================================================================
elif st.session_state.phase == 9.3:
    writing_norm = st.session_state.get("writing_norm", "")

    st.markdown("## A few questions about what you just wrote")
    st.markdown("Please answer based on the text you wrote in the previous section.")
    st.markdown("---")

    st.markdown("**To what extent does the text you wrote reflect your personal opinion?**")
    st.markdown("*Not at all → Completely*")
    recogn = likert_7(key="writing_post_recogn", labels=LIKERT_LABELS_RECOGN)

    st.markdown("---")

    st.markdown(
        f"**After writing, how appropriate or inappropriate do you consider "
        f"the action of: \"{writing_norm}\"?**"
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

        if not st.session_state.writing_data_saved:
            dur_s = _compute_duration_seconds()
            writing_row = [
                st.session_state.prolific_id,
                st.session_state.get("writing_group", ""),
                writing_norm,
                st.session_state.get("writing_text_final", ""),
                json.dumps(st.session_state.get("writing_keystroke_log", {}), ensure_ascii=False),
                str(dur_s),
                json.dumps(st.session_state.get("writing_llm_exchanges", []), ensure_ascii=False),
                str(st.session_state.get("writing_post_recogn",     "")),
                str(st.session_state.get("writing_post_appropriate", "")),
            ]
            try:
                save_to_writing_sheet(writing_row)
                st.session_state.writing_data_saved = True
            except Exception as e:
                st.error(
                    f"There was an error saving your writing data: {e}. "
                    "Please contact the researchers before closing this page."
                )
                st.stop()

        st.session_state.phase = 10
        st.rerun()

# ============================================================================
# PHASE 10 — TIGHTNESS SCALE
# ============================================================================
elif st.session_state.phase == 10:
    st.markdown("""The following statements refer to the country in which you currently live, as a whole. Indicate whether you agree or disagree with the statements using the following scale. Note that the statements sometimes refer to "social norms," which are generally unwritten standards of behavior.""")

    tightness_items = [
        "In this country, there are many social norms that people should abide by.",
        "In this country, there are very clear expectations for how people should behave in most situations.",
        "In this country, people agree on which behaviors are appropriate and which are inappropriate in most situations.",
        "In this country, people have a great deal of freedom in deciding how they want to behave in most situations.",
        "In this country, if someone behaves inappropriately, others will strongly disapprove.",
        "In this country, people almost always comply with social norms.",
        "In this country, people have very little freedom in deciding how they want to behave in most situations.",
    ]
    scale_labels = ["Strongly disagree", "Moderately disagree", "Slightly disagree",
                    "Slightly agree", "Moderately agree", "Strongly agree"]

    for i, item in enumerate(tightness_items):
        st.markdown(f"**{item}**")
        cols     = st.columns(6)
        selected = st.session_state.get(f"tight_{i}")
        for j, label in enumerate(scale_labels):
            val = j + 1
            with cols[j]:
                if st.button(label, key=f"tight_{i}_{val}", use_container_width=True,
                             type="primary" if selected == val else "secondary"):
                    st.session_state[f"tight_{i}"] = val
                    st.rerun()
        st.markdown("")

    st.markdown("---")
    st.text_area(
        "Is there anything you would like to add or do you want to clarify about your answers?",
        height=100, key="tightness_open"
    )

    if st.button("Continue"):
        missing = [i for i in range(len(tightness_items)) if not st.session_state.get(f"tight_{i}")]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        st.session_state.tightness_responses = {
            item: st.session_state[f"tight_{i}"]
            for i, item in enumerate(tightness_items)
        }
        st.session_state.phase = 11
        st.rerun()

# ============================================================================
# PHASE 11 — PURPOSE OF STUDY
# ============================================================================
elif st.session_state.phase == 11:
    st.markdown("**What do you think is the purpose of this study?**")
    st.text_area("Your answer:", height=150, key="purpose_text", label_visibility="collapsed")

    if st.button("Continue"):
        response = st.session_state.get("purpose_text", "").strip()
        if not response:
            st.warning("Please write your answer before continuing.")
            st.stop()
        st.session_state.purpose_text_saved = response
        st.session_state.phase = 12
        st.rerun()

# ============================================================================
# PHASE 12 — DEMOGRAPHIC QUESTIONS
# ============================================================================
elif st.session_state.phase == 12:
    st.markdown("Please answer the following questions about yourself.")
    st.markdown("---")

    age = st.selectbox(
        "How old are you, in years?",
        list(range(18, 101)),
        index=None,
        placeholder="Select your age...",
        key="demo_age"
    )
    uk_location = st.selectbox(
        "Where do you live (in the UK)?",
        ["England", "Wales", "Scotland", "Northern Ireland"],
        index=None,
        placeholder="Select your location...",
        key="demo_location"
    )
    st.markdown("**What is your gender?**")
    gender = st.radio("Gender:", ["Male", "Female", "Other"],
                      horizontal=True, key="demo_gender", label_visibility="collapsed")
    st.markdown("**Are you currently enrolled as a student?**")
    student = st.radio("Student:", ["Yes", "No"],
                       horizontal=True, key="demo_student", label_visibility="collapsed")
    education = st.selectbox(
        "What is the highest level of education you have completed, or the highest degree you have received?",
        [
            "Less than high school degree (less than 12 years in school)",
            "High school graduate (12 or more years in school)",
            "Some college but no degree",
            "Bachelor's/Associate degree",
            "Master's degree",
            "Doctoral degree",
        ],
        index=None,
        placeholder="Select your education level...",
        key="demo_education"
    )
    st.markdown("**Here is a 7-point scale on which the political views that people might hold are arranged from extremely liberal (left) to extremely conservative (right). Where would you place yourself on this scale?**")
    col_l, col_m, col_r = st.columns([2, 5, 2])
    with col_l:
        st.markdown("<div style='text-align:right;padding-top:28px'>Extremely liberal (left)</div>",
                    unsafe_allow_html=True)
    with col_m:
        politics = st.slider("Politics", 1, 7, 4, key="demo_politics", label_visibility="collapsed")
    with col_r:
        st.markdown("<div style='padding-top:28px'>Extremely conservative (right)</div>",
                    unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    st.markdown("""**Think of a ladder as representing where people stand in the UK. At the top of the ladder are the people who are the best off – those who have the most money, the most education, and the most respected jobs. At the bottom are the people who are the worst off – those who have the least money, least education, the least respected jobs, or no job. Where would you place yourself on this ladder?**""")
    col_l2, col_m2, col_r2 = st.columns([2, 5, 2])
    with col_l2:
        st.markdown("<div style='text-align:right;padding-top:28px'>Bottom (1)</div>",
                    unsafe_allow_html=True)
    with col_m2:
        ladder = st.select_slider(
            "Social ladder position (1 = bottom, 10 = top):",
            options=list(range(1, 11)), value=5, key="demo_ladder",
            label_visibility="collapsed"
        )
    with col_r2:
        st.markdown("<div style='padding-top:28px'>Top (10)</div>",
                    unsafe_allow_html=True)

    if st.button("Continue"):
        errors = []
        if age         is None: errors.append("Please select your age.")
        if uk_location is None: errors.append("Please select where you live in the UK.")
        if education   is None: errors.append("Please select your education level.")
        if errors:
            for e in errors: st.warning(e)
            st.stop()
        st.session_state.demographics = {
            "age": age, "uk_location": uk_location, "gender": gender,
            "student": student, "education": education,
            "politics": politics, "social_ladder": ladder,
        }
        st.session_state.phase = 13
        st.rerun()

# ============================================================================
# PHASE 13 — DEBRIEFING
# [CHANGE 3] Removed the sentence starting with "We set out to measure..."
#            up to "...appropriate behavior." as it is better explained later.
# ============================================================================
elif st.session_state.phase == 13:
    st.markdown("## Debriefing")
    st.markdown("""Our study focuses on a type of artificial intelligence (AI) called a "large language model" or LLM. An LLM is a type of AI that can engage you in a conversation.

When you interact with an LLM, you provide it with a "query" (an excerpt of text) and it generates a response. This response is based on the knowledge it has learned during its training. An LLM is still a machine learning system, and its knowledge is limited by the data it was trained on. It might not always provide the most accurate or up-to-date information, and it can sometimes generate responses that don't make perfect sense. However, as AI technology advances, these models continue to improve in their understanding and generation of human language.

Recent research has shown that LLMs have developed the ability to generate persuasive messages. This has raised concerns about their potential to influence how people perceive and evaluate social norms. We displayed these messages to you and other participants to observe how you may react to them. We were particularly interested in whether, after interacting with an LLM, you might report a different view on the appropriateness of everyday behaviors.

If you felt that your views were changed or influenced by the conversation, we encourage you to reflect on how and why this happened. It is important to understand that the model was designed to present arguments in a persuasive manner, and your responses contribute to our understanding of how AI can be used to impact judgments about social norms.

To reiterate, in this experiment, the messages that you were exposed to were written by AI (in the form of an LLM).

We hope that our research can contribute to a better understanding of how to make these models safer and reduce the risk of their misuse. We appreciate the time you spent participating in this experiment. You can learn more about LLMs by clicking *(TBD)*. If you have any further questions, please reach out to the researchers at *(TBD)*. As a reminder, you have the right to withdraw your responses by contacting the researcher with your Prolific ID through e-mail or through Prolific's anonymous messaging system.""")

    if st.button("Continue"):
        st.session_state.phase = 14
        st.rerun()

# ============================================================================
# PHASE 14 — FINAL COMMENTS + SAVE TO MAIN GOOGLE SHEET
# ============================================================================
elif st.session_state.phase == 14 and not st.session_state.data_saved:
    st.markdown("You may optionally leave any comments about the study in the box below.")
    st.text_area("Comments (optional):", height=120, key="final_comments", label_visibility="collapsed")

    if st.button("Finish & Submit"):
        demographics   = st.session_state.get("demographics", {})
        total_duration = time.time() - st.session_state.start_time
        user_word_count = sum(
            len(m["content"].split())
            for m in st.session_state.messages if m["role"] == "user"
        )

        row = [
            st.session_state.prolific_id,
            st.session_state.prompt_key,
            st.session_state.norm_key,
            json.dumps(st.session_state.get("initial_opinion", {}),       ensure_ascii=False),
            json.dumps(st.session_state.get("opinions_others", {}),       ensure_ascii=False),
            json.dumps(st.session_state.get("messages", []),              ensure_ascii=False),
            str(st.session_state.get("att_check_response_saved", "")),
            str(st.session_state.get("att_check_passed", "")),
            json.dumps(st.session_state.get("final_opinion", {}),         ensure_ascii=False),
            json.dumps(st.session_state.get("opinions_others_final", {}), ensure_ascii=False),
            json.dumps(st.session_state.get("tightness_responses", {}),   ensure_ascii=False),
            str(st.session_state.get("tightness_open", "")),
            json.dumps(st.session_state.get("involvement_responses", {}), ensure_ascii=False),
            json.dumps(st.session_state.get("threat_responses", {}),      ensure_ascii=False),
            json.dumps(st.session_state.get("source_responses", {}),      ensure_ascii=False),
            str(st.session_state.get("purpose_text_saved", "")),
            str(demographics.get("age",           "")),
            str(demographics.get("uk_location",   "")),
            str(demographics.get("gender",        "")),
            str(demographics.get("student",       "")),
            str(demographics.get("education",     "")),
            str(demographics.get("politics",      "")),
            str(demographics.get("social_ladder", "")),
            str(st.session_state.get("engagement_text_saved", "")),
            str(st.session_state.get("engagement_word_count", 0)),
            str(st.session_state.get("final_comments", "")),
            str(st.session_state.get("parallel_engagement_time",    "")),
            str(st.session_state.get("sequential_engagement_time",  "")),
            str(st.session_state.get("interaction_engagement_time", "")),
            str(sum(1 for m in st.session_state.messages if m["role"] == "user")),
            str(user_word_count),
            str(round(total_duration, 2)),
            datetime.now().isoformat(),
            str(st.session_state.get("writing_group", "")),
            json.dumps(st.session_state.get("writing_keystroke_log", {}), ensure_ascii=False),
            str(_compute_duration_seconds()),
            json.dumps(st.session_state.get("writing_llm_exchanges", []), ensure_ascii=False),
            str(st.session_state.get("writing_post_recogn",      "")),
            str(st.session_state.get("writing_post_appropriate",  "")),
        ]

        try:
            save_to_google_sheets(row)
        except Exception as e:
            st.error(f"There was an error saving your data: {e}. Please contact the researchers before closing this page.")
            st.stop()

        st.session_state.data_saved = True
        st.session_state.phase = 15
        st.rerun()

# ============================================================================
# PHASE 15 — THANK YOU & PROLIFIC REDIRECT
# ============================================================================
elif st.session_state.phase >= 15:
    st.markdown("## Thank you for participating.")
    st.markdown("Your responses have been successfully recorded.")
    st.markdown("Please click the link below to finish the study and retrieve your Prolific completion code.")

    pid          = st.session_state.get("prolific_id", "")
    base_url     = "https://www.prolific.co/"
    redirect_url = f"{base_url}?PROLIFIC_PID={pid}"
    st.markdown(
        f"[**→ Return to Prolific to complete your submission**]({redirect_url})",
        unsafe_allow_html=True
    )