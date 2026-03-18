import streamlit as st
import json
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
    "2", "3", "4", "5", "6",
    "7\nCompletely",
]

LIKERT_LABELS_APPROP = [
    "1\nExtremely\ninappropriate",
    "2\nVery\ninappropriate",
    "3\nSomewhat\ninappropriate",
    "4\nNeither",
    "5\nSomewhat\nappropriate",
    "6\nVery\nappropriate",
    "7\nExtremely\nappropriate",
]

# ============================================================================
# GOOGLE SHEETS
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
# VERTEX AI / GEMINI CLIENT
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
        "writing_initialized":      True,
        "writing_phase":            0,      # 0=prolific_id, 1=intro, 2=writing, 3=post-q, 4=done
        "writing_group":            None,   # assigned after prolific id entry
        "prolific_id":              "",
        "writing_text_final":       "",
        "writing_llm_output":       "",
        "writing_llm_exchanges":    [],
        "writing_post_recogn":      None,
        "writing_post_appropriate": None,
        "writing_data_saved":       False,
    })

# ============================================================================
# PHASE 0 — PROLIFIC ID + GROUP ASSIGNMENT
# ============================================================================
if st.session_state.writing_phase == 0:

    st.markdown("## Welcome")
    st.markdown("Please enter your Prolific ID to begin.")

    prolific_id_input = st.text_input(
        "Prolific ID:",
        value=st.session_state.prolific_id,
        placeholder="Enter your Prolific ID here…",
        key="prolific_id_input",
    )

    if st.button("Continue"):
        pid = prolific_id_input.strip()
        if not pid:
            st.warning("Please enter your Prolific ID before continuing.")
            st.stop()
        st.session_state.prolific_id   = pid
        st.session_state.writing_group = random.choice(["A", "B"])
        st.session_state.writing_phase = 1
        st.rerun()

# ============================================================================
# PHASE 1 — TASK INTRODUCTION
# ============================================================================
elif st.session_state.writing_phase == 1:

    st.markdown("## Writing Task — Instructions")
    st.markdown("---")

    st.markdown(
        "In this part of the study, we are interested in how people express "
        "their personal views on everyday social norms in their own words."
    )
    st.markdown(
        "You will be asked to write **around 5 lines** expressing your personal "
        "perception of a specific social norm."
    )
    st.markdown(
        "There is **no right or wrong answer**. Write freely — you can describe "
        "what you think about the norm, share a personal experience, or argue a position."
    )

    st.markdown("---")
    st.markdown("**The norm you will be writing about is:**")
    st.markdown(
        f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
        f"padding:14px 18px;border-radius:4px;font-size:1.1rem;font-style:italic;'>"
        f"\"{FIXED_NORM}\"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if st.session_state.writing_group == "B":
        st.info(
            "💡 On the next screen you will also have access to an **AI writing assistant** "
            "on the right side of the page. You can use it however you like — to brainstorm, "
            "get feedback, or draft text. The choice is entirely yours."
        )

    if st.button("Start writing →"):
        st.session_state.writing_phase = 2
        st.rerun()

# ============================================================================
# PHASE 2 — WRITING SCREEN
# ============================================================================
elif st.session_state.writing_phase == 2:

    group = st.session_state.writing_group

    # ── GROUP A — full-width text area ───────────────────────────────────────
    if group == "A":
        st.markdown("## Your Writing")
        st.markdown(
            "**Please write around 5 lines expressing your personal perception "
            "of the following norm:**"
        )
        st.markdown(
            f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
            f"padding:12px 16px;border-radius:4px;font-style:italic;margin-bottom:16px;'>"
            f"\"{FIXED_NORM}\"</div>",
            unsafe_allow_html=True,
        )

        st.text_area(
            "Your answer:",
            height=260,
            key="writing_text_input_A",
            label_visibility="collapsed",
            placeholder="Write your thoughts here…",
        )

        if st.button("Continue →"):
            text = st.session_state.get("writing_text_input_A", "").strip()
            if len(text.split()) < 10:
                st.warning("Please write at least a few sentences before continuing.")
                st.stop()
            st.session_state.writing_text_final = text
            st.session_state.writing_phase = 3
            st.rerun()

    # ── GROUP B — two columns: writing on left, AI chat on right ────────────
    else:
        # Init dedicated writing chat — only once
        if "writing_chat" not in st.session_state:
            model        = get_gemini_model()
            writing_chat = model.start_chat()
            writing_chat.send_message(
                "You are a helpful writing assistant. "
                "The user is participating in a research study and must write "
                "approximately 5 lines expressing their personal view on the following "
                f"social norm: \"{FIXED_NORM}\". "
                "Help them think about the topic, suggest ideas, or draft text if asked. "
                "Be concise and neutral. Do not take strong political positions. "
                "Respond in the same language the user writes in."
            )
            st.session_state.writing_chat = writing_chat

        col_write, col_chat = st.columns([3, 2], gap="large")

        # ── Left: writing area ───────────────────────────────────────────────
        with col_write:
            st.markdown("## Your Writing")
            st.markdown(
                "**Please write around 5 lines expressing your personal perception "
                "of the following norm:**"
            )
            st.markdown(
                f"<div style='background:#f0f2f6;border-left:4px solid #4e8cff;"
                f"padding:12px 16px;border-radius:4px;font-style:italic;margin-bottom:16px;'>"
                f"\"{FIXED_NORM}\"</div>",
                unsafe_allow_html=True,
            )
            st.text_area(
                "Your answer:",
                height=300,
                key="writing_text_input_B",
                label_visibility="collapsed",
                placeholder="Write your thoughts here…",
            )
            if st.button("Continue →"):
                text = st.session_state.get("writing_text_input_B", "").strip()
                if len(text.split()) < 10:
                    st.warning("Please write at least a few sentences before continuing.")
                    st.stop()
                st.session_state.writing_text_final = text
                st.session_state.writing_phase = 3
                st.rerun()

        # ── Right: AI chat ───────────────────────────────────────────────────
        with col_chat:
            st.markdown("## 🤖 AI Writing Assistant")
            st.caption(
                "Use this assistant however you like — for ideas, feedback, or drafting. "
                "It's completely optional."
            )

            # Scrollable chat history
            chat_container = st.container(height=400)
            with chat_container:
                if not st.session_state.writing_llm_exchanges:
                    st.markdown(
                        "<div style='color:#aaa;font-size:.9rem;padding:8px 0;'>"
                        "Ask me anything about this topic…</div>",
                        unsafe_allow_html=True,
                    )
                for msg in st.session_state.writing_llm_exchanges:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

            # Chat input below the container
            llm_input = st.chat_input("Ask the AI for help…", key="writing_chat_input")
            if llm_input:
                st.session_state.writing_llm_exchanges.append(
                    {"role": "user", "content": llm_input}
                )
                with st.spinner("Thinking…"):
                    stream = st.session_state.writing_chat.send_message(
                        llm_input, stream=True
                    )
                    reply = "".join(chunk.text for chunk in stream)

                st.session_state.writing_llm_exchanges.append(
                    {"role": "assistant", "content": reply}
                )
                st.session_state.writing_llm_output = reply
                st.rerun()

# ============================================================================
# PHASE 3 — POST-WRITING QUESTIONNAIRE
# ============================================================================
elif st.session_state.writing_phase == 3:

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

    if st.button("Continue →"):
        if recogn is None or appropriate is None:
            st.warning("Please answer both questions before continuing.")
            st.stop()
        st.session_state.writing_post_recogn      = recogn
        st.session_state.writing_post_appropriate = appropriate

        # ── Save to Google Sheets ────────────────────────────────────────────
        if not st.session_state.writing_data_saved:
            writing_row = [
                st.session_state.prolific_id,                                       # A
                st.session_state.get("writing_group", ""),                          # B
                FIXED_NORM,                                                         # C
                st.session_state.get("writing_text_final", ""),                     # D
                st.session_state.get("writing_llm_output", ""),                     # E
                json.dumps(
                    st.session_state.get("writing_llm_exchanges", []),
                    ensure_ascii=False,
                ),                                                                  # F
                str(len(st.session_state.get("writing_llm_exchanges", [])) // 2),  # G
                str(st.session_state.get("writing_post_recogn", "")),              # H
                str(st.session_state.get("writing_post_appropriate", "")),         # I
                datetime.now().isoformat(),                                         # J
            ]
            try:
                save_to_writing_sheet(writing_row)
                st.session_state.writing_data_saved = True
            except Exception as e:
                st.warning(f"Data could not be saved: {e}")

        st.session_state.writing_phase = 4
        st.rerun()

# ============================================================================
# PHASE 4 — DONE
# ============================================================================
elif st.session_state.writing_phase >= 4:
    st.markdown("## Thank you!")
    st.markdown("Your responses have been recorded successfully.")
    st.markdown("You may now proceed to the next section of the study.")
    # If embedded in the main study, replace the lines above with:
    #   st.session_state.phase = 9
    #   st.rerun()