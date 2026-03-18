import streamlit as st
import json
import time
import random
from datetime import datetime

import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2.service_account import Credentials
import gspread

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Writing Task",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================================
# CONSTANTS
# ============================================================================
FIXED_NORM = "not telling someone they have gained weight"

LIKERT_LABELS_RECOGN = [
    "1\nNot at all",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7\nCompletely",
]

LIKERT_LABELS_APPROP = [
    "1\nExtremely inappropriate",
    "2\nVery inappropriate",
    "3\nSomewhat inappropriate",
    "4\nNeither",
    "5\nSomewhat appropriate",
    "6\nVery appropriate",
    "7\nExtremely appropriate",
]

# ============================================================================
# GOOGLE SHEETS — saving writing data
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
            .open_by_url(st.secrets["writing_sheet_url"])
            .sheet1
        )
    return st.session_state.writing_gsheet

def save_to_writing_sheet(row):
    get_writing_sheet().append_row(row, value_input_option="RAW")

# ============================================================================
# VERTEX AI / GEMINI CLIENT — lazy init
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
        st.session_state.gemini_model = GenerativeModel("gemini-2.5-flash")
    return st.session_state.gemini_model

# ============================================================================
# LIKERT-7 HELPER
# ============================================================================
def likert_7(key, labels):
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

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
if "writing_initialized" not in st.session_state:
    st.session_state.update({
        "writing_initialized":    True,
        "writing_phase":          81,           # start at phase 81
        "writing_group":          random.choice(["A", "B"]),
        "writing_text_final":     "",
        "writing_llm_output":     "",
        "writing_llm_exchanges":  [],
        "writing_post_recogn":    None,
        "writing_post_appropriate": None,
        "writing_data_saved":     False,
        # For standalone use — replace with actual prolific_id if embedded
        "prolific_id":            st.query_params.get("PROLIFIC_PID", "test_user"),
    })

# ============================================================================
# PHASE 81 — WRITING TASK
# ============================================================================
if st.session_state.writing_phase == 81:

    group = st.session_state.writing_group

    st.markdown("---")
    st.markdown("## One more question before we finish")
    st.markdown(
        "We are interested in how people express their personal view "
        "on a specific social norm in their own words."
    )
    st.markdown("---")

    st.markdown(
        "**Please write around 5 lines expressing your personal perception "
        "of the following social norm:**"
    )
    st.markdown(f"> *\"{FIXED_NORM}\"*")
    st.markdown(
        "There is no right or wrong answer. Write freely: you can describe "
        "what you think about this norm, share a personal experience, or argue a position."
    )

    # ── GROUP A — text area only ─────────────────────────────────────────────
    if group == "A":
        st.text_area(
            "Your answer (approx. 5 lines):",
            height=200,
            key="writing_text_input_A",
        )

        if st.button("Continue"):
            text = st.session_state.get("writing_text_input_A", "").strip()
            if len(text.split()) < 10:
                st.warning("Please write at least a few sentences before continuing.")
                st.stop()
            st.session_state.writing_text_final = text
            st.session_state.writing_phase = 82
            st.rerun()

    # ── GROUP B — LLM assistant + text area ──────────────────────────────────
    else:
        st.markdown(
            "You also have access to an AI assistant. "
            "You can use it however you like: to get ideas, to improve what you have written, "
            "or to generate the text directly. The choice is yours."
        )

        # Init dedicated writing chat — only once
        if "writing_chat" not in st.session_state:
            model        = get_gemini_model()
            writing_chat = model.start_chat()
            writing_chat.send_message(
                "You are a helpful writing assistant. "
                "The user is participating in a research study and needs to write "
                "approximately 5 lines expressing their personal view on the following "
                f"social norm: \"{FIXED_NORM}\". "
                "Help them think about the topic, suggest ideas, or draft text if asked. "
                "Be concise and neutral. Do not take strong political positions. "
                "Respond in the same language the user writes in."
            )
            st.session_state.writing_chat = writing_chat

        # Render past exchanges
        if st.session_state.writing_llm_exchanges:
            st.markdown("**AI Assistant:**")
            for msg in st.session_state.writing_llm_exchanges:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # LLM input
        llm_input = st.chat_input("Ask the AI for help (optional)…")
        if llm_input:
            st.session_state.writing_llm_exchanges.append(
                {"role": "user", "content": llm_input}
            )
            with st.chat_message("user"):
                st.markdown(llm_input)

            with st.chat_message("assistant"):
                stream = st.session_state.writing_chat.send_message(llm_input, stream=True)
                reply  = st.write_stream(chunk.text for chunk in stream)

            st.session_state.writing_llm_exchanges.append(
                {"role": "assistant", "content": reply}
            )
            st.session_state.writing_llm_output = reply
            st.rerun()

        st.markdown("---")
        st.markdown("**Your final text** *(write or paste here — this is what we will save)*:")
        st.text_area(
            "Your answer (approx. 5 lines):",
            height=200,
            key="writing_text_input_B",
            label_visibility="collapsed",
        )

        if st.button("Continue"):
            text = st.session_state.get("writing_text_input_B", "").strip()
            if len(text.split()) < 10:
                st.warning("Please write at least a few sentences before continuing.")
                st.stop()
            st.session_state.writing_text_final = text
            st.session_state.writing_phase = 82
            st.rerun()

# ============================================================================
# PHASE 82 — POST-WRITING QUESTIONNAIRE
# ============================================================================
elif st.session_state.writing_phase == 82:

    st.markdown("## A few questions about what you just wrote")
    st.markdown("Please answer based on the text you wrote in the previous section.")
    st.markdown("---")

    st.markdown("**To what extent does the text you wrote reflect your personal opinion?**")
    st.markdown("*1 = Not at all — 7 = Completely*")
    recogn = likert_7(key="writing_post_recogn", labels=LIKERT_LABELS_RECOGN)

    st.markdown("---")

    st.markdown(
        f"**After writing, how appropriate or inappropriate do you consider "
        f"the action of: \"{FIXED_NORM}\"?**"
    )
    st.markdown("*1 = Extremely inappropriate — 7 = Extremely appropriate*")
    appropriate = likert_7(key="writing_post_appropriate", labels=LIKERT_LABELS_APPROP)

    st.markdown("---")

    if st.button("Continue"):
        if recogn is None or appropriate is None:
            st.warning("Please answer both questions before continuing.")
            st.stop()
        st.session_state.writing_post_recogn      = recogn
        st.session_state.writing_post_appropriate = appropriate

        # ── Save to Google Sheets ────────────────────────────────────────────
        if not st.session_state.writing_data_saved:
            writing_row = [
                st.session_state.prolific_id,                                        # A: Prolific ID
                st.session_state.get("writing_group", ""),                           # B: Group (A or B)
                FIXED_NORM,                                                          # C: Fixed norm
                st.session_state.get("writing_text_final", ""),                      # D: Final text
                st.session_state.get("writing_llm_output", ""),                      # E: Last LLM output
                json.dumps(
                    st.session_state.get("writing_llm_exchanges", []),
                    ensure_ascii=False
                ),                                                                   # F: Full LLM exchange log
                str(len(st.session_state.get("writing_llm_exchanges", [])) // 2),   # G: N queries sent
                str(st.session_state.get("writing_post_recogn", "")),               # H: Recognition (Likert 1-7)
                str(st.session_state.get("writing_post_appropriate", "")),          # I: Post-appropriateness (Likert 1-7)
                datetime.now().isoformat(),                                          # J: Timestamp
            ]
            try:
                save_to_writing_sheet(writing_row)
                st.session_state.writing_data_saved = True
            except Exception as e:
                st.warning(f"Writing experiment data could not be saved: {e}")

        st.session_state.writing_phase = 83
        st.rerun()

# ============================================================================
# PHASE 83 — DONE (hand back to main flow or show completion)
# ============================================================================
elif st.session_state.writing_phase >= 83:
    st.markdown("## Thank you!")
    st.markdown("Your responses have been recorded. You may now proceed to the next section of the study.")
    # If embedded in a larger study, replace the block above with:
    #   st.session_state.phase = 9
    #   st.rerun()