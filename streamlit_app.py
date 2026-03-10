import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import os
import time
import random
from collections import defaultdict

import vertexai
from vertexai.generative_models import GenerativeModel, ChatSession
import threading

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
pos=99

# ============================================================================
# GOOGLE SHEETS — lazy
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
# VERTEX AI / GEMINI CLIENT — lazy
# ============================================================================
def get_gemini_model() -> GenerativeModel:
    """Inizializza Vertex AI usando le credenziali nei Streamlit Secrets."""
    if "gemini_model" not in st.session_state:
        # Legge le credenziali dal blocco [gcp_vertex_account] in secrets.toml
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
    """Avvia l'inizializzazione di Vertex AI in un thread separato."""
    def _init():
        try:
            get_gemini_model()
        except Exception:
            pass
    if not st.session_state.get("gemini_preload_started"):
        st.session_state.gemini_preload_started = True
        threading.Thread(target=_init, daemon=True).start()


def precompute_greeting_in_background():
    """
    Precalcola il greeting dell'AI in background durante la fase 4,
    così quando l'utente clicca 'Start Conversation' è già pronto.
    """
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
            pass  # Se fallisce, la fase 5 lo rigenera normalmente

    if not st.session_state.get("greeting_precompute_started"):
        st.session_state.greeting_precompute_started = True
        threading.Thread(target=_generate, daemon=True).start()

def get_or_rebuild_chat(system_prompt: str) -> ChatSession:
    """
    Restituisce la ChatSession attiva oppure la ricostruisce
    dalla cronologia dei messaggi salvati in session_state.
    """
    if "gemini_chat" in st.session_state:
        return st.session_state.gemini_chat

    model = get_gemini_model()
    chat  = model.start_chat()

    # Ricostruisce la storia: ignora l'ultimo messaggio utente (verrà inviato adesso)
    history = [m for m in st.session_state.messages if m["role"] != "system"]
    for i, msg in enumerate(history):
        if msg["role"] == "user":
            # Invia il messaggio utente e aspetta la risposta dell'assistant successiva
            next_msg = history[i + 1] if i + 1 < len(history) else None
            if next_msg and next_msg["role"] == "assistant":
                # Simula lo scambio già avvenuto senza fare chiamate API reali
                # Vertex AI ChatSession mantiene la history internamente
                pass
    # Nota: Vertex AI non permette di iniettare storia manualmente come OpenAI.
    # La chat viene ricreata pulita; la storia visuale resta in st.session_state.messages.
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
                    // Streamlit 1.x
                    let main = window.parent.document.querySelector('.main');
                    if (main) main.scrollTop = 0;
                    
                    // Streamlit più recenti
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
# ============================================================================
# SLIDER HELPER
# ============================================================================
def labeled_slider(label, key, default=50):
    col_left, col_mid, col_right = st.columns([1, 6, 1])
    with col_left:
        st.markdown(
            "<div style='text-align:left; padding-top:28px'>0<br><small>Completely<br>inappropriate</small></div>",
            unsafe_allow_html=True
        )
    with col_mid:
        val = st.slider(label, 0, 100, default, key=key, label_visibility="collapsed")
    with col_right:
        st.markdown(
            "<div style='text-align:right; padding-top:28px'>100<br><small>Completely<br>appropriate</small></div>",
            unsafe_allow_html=True
        )
    st.markdown("<br><br>", unsafe_allow_html=True)
    return val

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
        "gemini_chat":                  None,   # ChatSession Gemini
        "system_prompt_cache":          None,   # system prompt usato nella chat
    })

# ============================================================================
# PHASE -1 — EARLY TERMINATION
# ============================================================================

if st.session_state.phase!=pos:
    scroll_to_top()
if st.session_state.phase == -1:
    pos=st.session_state.phase
    st.markdown("## Thank you for your time.")
    st.markdown(
        "Unfortunately, your answer makes it impossible for us to include you in this study. "
        "Thank you for your time. You may now close this window."
    )
    st.stop()

# ============================================================================
# PHASE 0 — CONSENT FORM
# ============================================================================
elif st.session_state.phase == 0:
    pos=st.session_state.phase
    # Avvia la connessione a Vertex AI in background mentre l'utente legge il consenso
    preload_gemini_in_background()
    st.markdown("## Thank you for joining our study!")
    st.markdown("""
**Before proceeding, please read carefully the information reported below.**

**Aim of the Study**  
You are being invited to participate in a study of social norms. The purpose of this study is to analyze everyday norms – i.e., norms about behavior that many people perform regularly, and most people could perform if they wanted to – and to understand how people engage in conversations about these topics with an advanced AI.

**What will I be asked to do?**  
If you agree to take part, you will be asked to answer a set of survey questions related to social norms. These include questions about how appropriate you and other people think behaviors are in different settings. Concerning questions about how other people perceive behaviors, you will receive a bonus payment if you make a correct guess. Next, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The study should take approximately *(TBD)* minutes to complete.

**Can I change my mind?**  
Participation is voluntary and you can decline to participate in the research or any aspects of the research at any time without penalty. You may withdraw by simply closing the browser on the computer. It will not be possible for you to withdraw after the completion of the survey because your responses are anonymous.

**Risks and benefits**  
There are no direct benefits to you as a participant. Study results will help inform the scholarly understanding of AI conversations about everyday norms work. There is a risk that some of the questions may be sensitive and/or could cause you psychological distress. You don't have to answer any questions you don't want to. There are questions where you will receive a bonus payment of £0.50 if you answer correctly (two questions, for a maximum of £1).

**Privacy and data**  
The data that you provide will be anonymous so your responses cannot be linked back to you. The study data will be stored on an encrypted server at *(TBD)*. The anonymous dataset will be stored indefinitely and shared with other researchers for research and teaching purposes. We plan to publish the results of this study in academic journals and present them at conferences.

**Any questions?**  
If you have any questions about the research, please contact *(TBD)*.

By clicking "I agree" below you are indicating that you have read this information and agree to participate in this research study.
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
            scroll_to_top()
            st.rerun()
    elif consent == "I do not agree":
        if st.button("Continue"):
            st.session_state.phase = -1
            scroll_to_top()
            st.rerun()

# ============================================================================
# PHASE 0.5 — DATA QUALITY CHECK
# ============================================================================
elif st.session_state.phase == 0.5:
    pos=st.session_state.phase
    st.markdown("We care about the quality of our survey data. For us to fully understand your opinions, it is important that you provide careful answers to each question in this survey.")
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
            st.session_state.phase = 1
            scroll_to_top()
            st.rerun()
    elif quality in ("I will not provide my best answers", "I can't promise either way"):
        if st.button("Continue"):
            st.session_state.phase = -1
            scroll_to_top()
            st.rerun()

# ============================================================================
# PHASE 1 — BACKGROUND QUESTION
# ============================================================================
elif st.session_state.phase == 1:
    pos=st.session_state.phase
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
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 2 — INITIAL APPROPRIATENESS RATINGS
# ============================================================================
elif st.session_state.phase == 2:
    pos=st.session_state.phase
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

    st.markdown("""From various sources in our everyday lives we have all developed a subjective "impression" or "feeling" for the appropriateness of any given behavior in a particular situation. In this study, we are interested in your judgment of the appropriateness of some particular behaviors in some particular settings.

Your task in each case is simply to rate, on a scale from 0 (completely inappropriate) to 100 (completely appropriate), the appropriateness of the particular behavior in the situation that is given.""")

    opinions = {}
    for i, norm in enumerate(st.session_state.sampled_norms):
        st.markdown(f"**How appropriate or inappropriate is it to {norm['title']}?**")
        opinions[norm['title']] = labeled_slider(" ", key=f"slider_{i}", default=50)

    if st.button("Continue"):
        st.session_state.initial_opinion = opinions
        st.session_state.phase = 3
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 3 — EXPECTED OTHERS' RATINGS (initial)
# ============================================================================
elif st.session_state.phase == 3:
    pos=st.session_state.phase
    st.markdown("""We will now ask you what you think the other participants of this study from the UK have on average rated the appropriateness of these behaviors from 0 (completely inappropriate) to 100 (completely appropriate).

We will calculate the mean responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct (±3), you will receive an additional bonus of £0.50. Only one behavior will be randomly selected for payment.""")

    opinions_others = {}
    for i, norm in enumerate(st.session_state.sampled_norms):
        st.markdown(f"**{norm['title']}**")
        st.markdown("Other respondents' average appropriateness rating:")
        opinions_others[norm['title']] = labeled_slider(" ", key=f"group_slider_{i}", default=50)

    if st.button("Continue"):
        st.session_state.opinions_others = opinions_others
        st.session_state.phase = 4
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 4 — INSTRUCTIONS FOR CONVERSATION
# ============================================================================
elif st.session_state.phase == 4:
    pos=st.session_state.phase
    st.markdown("""Now, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The purpose of this dialogue is to see how humans and AI interact. Please be open and honest in your responses. Remember that the AI is neutral and non-judgmental, and your participation is confidential. When the conversation begins, you should see an AI icon with chat bubbles "..." indicating it's generating responses. It can sometimes take up to 30s. If you don't see any icons or if it's taking too long to generate responses, try refreshing the page. If you run into further issues, please let us know.

Please read each AI message thoroughly, and you may have to scroll down to read its full message. You will be asked some questions about your interaction. You will have to write at least 2 messages to the AI, up to a maximum of 10.

When the conversation is over, you should see a message at the bottom: **Scroll down and proceed to the next section.**""")

    # Avvia il precompute del greeting in background mentre l'utente legge le istruzioni
    precompute_greeting_in_background()

    if st.button("Start Conversation"):
        st.session_state.phase = 5
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 5 — CONVERSATION WITH GEMINI
# ============================================================================
elif st.session_state.phase == 5:
    pos=st.session_state.phase
    prompt_data   = PROMPTS[st.session_state.prompt_key]
    norm_data     = NORMS[st.session_state.norm_key]
    initial_val   = st.session_state.initial_opinion.get(norm_data["title"], 50)
    system_prompt = (
        prompt_data["system_prompt_template"]
        .replace("{NORM_DESCRIPTION}", norm_data["title"])
        .replace("{INITIAL_OPINION}", str(initial_val))
    )
    st.session_state.system_prompt_cache = system_prompt

    # ------------------------------------------------------------------ #
    # GREETING — usa il precomputed se disponibile, altrimenti lo genera  #
    # ------------------------------------------------------------------ #
    if not st.session_state.greeting_sent:
        if st.session_state.get("precomputed_greeting"):
            # ✅ Greeting già pronto — nessuna attesa
            st.session_state.gemini_chat = st.session_state.precomputed_chat
            greeting_text = st.session_state.precomputed_greeting
        else:
            # ⏳ Fallback: genera al momento (precompute non ancora finito)
            with st.spinner("Starting conversation..."):
                model = get_gemini_model()
                chat  = model.start_chat()
                response = chat.send_message(
                    f"{system_prompt}\n\nStart the discussion now. Open the topic."
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

    # ------------------------------------------------------------------ #
    # RENDER HISTORY                                                       #
    # ------------------------------------------------------------------ #
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    assistant_count = sum(1 for m in st.session_state.messages if m["role"] == "assistant")
    round_count     = max(0, assistant_count - 1)

    # ------------------------------------------------------------------ #
    # INPUT UTENTE                                                         #
    # ------------------------------------------------------------------ #
    if user_input := st.chat_input("Type your response here"):
        st.session_state.pending_user_message = {
            "role":      "user",
            "content":   user_input,
            "timestamp": datetime.now().isoformat(),
        }
        st.rerun()

    # ------------------------------------------------------------------ #
    # ELABORA MESSAGGIO UTENTE E GENERA RISPOSTA                          #
    # ------------------------------------------------------------------ #
    if st.session_state.pending_user_message:
        user_msg = st.session_state.pending_user_message
        st.session_state.messages.append(user_msg)
        with st.chat_message("user"):
            st.markdown(user_msg["content"])
        st.session_state.pending_user_message = None

        if round_count < 10:
            # Recupera o ricostruisce la ChatSession
            chat = st.session_state.get("gemini_chat")
            if chat is None:
                # Se la sessione è andata persa (es. reload), ricreiamo la chat
                model = get_gemini_model()
                chat  = model.start_chat()
                # Re-invia il system prompt come contesto
                chat.send_message(
                    f"{system_prompt}\n\n"
                    "Continue the ongoing discussion. "
                    "Below is the conversation so far (for context only):\n\n"
                    + "\n".join(
                        f"{'User' if m['role']=='user' else 'You'}: {m['content']}"
                        for m in st.session_state.messages[:-1]  # escludi l'ultimo
                    )
                )
                st.session_state.gemini_chat = chat

            with st.chat_message("assistant"):
                # Streaming della risposta
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

    # ------------------------------------------------------------------ #
    # PULSANTE DI FINE CONVERSAZIONE                                      #
    # ------------------------------------------------------------------ #
    user_msg_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
    if user_msg_count >= 2:
        st.markdown("---")
        st.markdown("*Scroll down and proceed to the next section.*")
        if st.button("End Discussion & Continue"):
            st.session_state.phase = 6
            scroll_to_top()
            st.rerun()

# ============================================================================
# PHASE 6 — ATTENTION CHECK
# ============================================================================
elif st.session_state.phase == 6:
    pos=st.session_state.phase
    st.markdown("**Which of the following best describes the main topic discussed with the AI?**")
    options = [n["title"] for n in st.session_state.sampled_norms] + ["None of the above / I don't remember"]
    st.radio("Select one:", options, index=None, key="att_check_response", label_visibility="collapsed")
    if st.button("Continue"):
        if not st.session_state.get("att_check_response"):
            st.warning("Please select an answer before continuing.")
            st.stop()
        st.session_state.att_check_response_saved = st.session_state.att_check_response
        st.session_state.phase = 7
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 7 — FINAL APPROPRIATENESS RATINGS
# ============================================================================
elif st.session_state.phase == 7:
    pos=st.session_state.phase
    st.markdown("We ask you again to rate, on a scale from 0 (completely inappropriate) to 100 (completely appropriate), the appropriateness of these behaviors.")

    final_opinions = {}
    for i, norm in enumerate(st.session_state.sampled_norms):
        title       = norm["title"]
        initial_val = st.session_state.initial_opinion.get(title, 50)
        st.markdown(f"**How appropriate or inappropriate is it to {title}?**")
        final_opinions[title] = labeled_slider(" ", key=f"final_slider_{i}", default=initial_val)

    if st.button("Continue"):
        st.session_state.final_opinion = final_opinions
        st.session_state.phase = 8
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 8 — FINAL EXPECTED OTHERS' RATINGS
# ============================================================================
elif st.session_state.phase == 8:
    pos=st.session_state.phase
    st.markdown("""We will now ask you again what you think the other participants of this study from the UK have on average rated the appropriateness of these behaviors from 0 (completely inappropriate) to 100 (completely appropriate).

We will calculate the mean responses provided by the other participants the second time they were asked and compare them with the estimate you provided. If your estimate is correct (±3), you will receive an additional bonus of £0.50. Only one behavior will be randomly selected for payment.""")

    opinions_others_final = {}
    for i, norm in enumerate(st.session_state.sampled_norms):
        st.markdown(f"**{norm['title']}**")
        st.markdown("Other respondents' average appropriateness rating:")
        opinions_others_final[norm['title']] = labeled_slider(" ", key=f"group_final_slider_{i}", default=50)

    if st.button("Continue"):
        st.session_state.opinions_others_final = opinions_others_final
        st.session_state.phase = 9
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 9 — TIGHTNESS SCALE
# ============================================================================
elif st.session_state.phase == 9:
    pos=st.session_state.phase
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
        st.session_state.phase = 10
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 10 — CONVERSATION PERCEPTION
# ============================================================================
elif st.session_state.phase == 10:
    pos=st.session_state.phase
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

    def _render_7pt(items, header):
        st.markdown(f"#### {header}")
        for label, key in items:
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

    st.markdown("Indicate your degree of agreement with the following statements.")
    st.markdown("*Scale: 1 = Totally disagree — 7 = Totally agree*")
    _render_7pt(involvement_items, "Involvement — The messages I read during the conversation with the AI:")
    _render_7pt(threat_items,      "Perceived Threat — The messages I read during the conversation with the AI:")
    _render_7pt(source_items,      "Evaluation of the Source — To what extent the source of these messages is:")

    if st.button("Continue"):
        all_keys = [k for _, k in involvement_items + threat_items + source_items]
        missing  = [k for k in all_keys if not st.session_state.get(k)]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        st.session_state.involvement_responses = {l: st.session_state[k] for l, k in involvement_items}
        st.session_state.threat_responses      = {l: st.session_state[k] for l, k in threat_items}
        st.session_state.source_responses      = {l: st.session_state[k] for l, k in source_items}
        st.session_state.phase = 11
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 11 — PURPOSE OF STUDY
# ============================================================================
elif st.session_state.phase == 11:
    pos=st.session_state.phase
    st.markdown("**What do you think is the purpose of this study?**")
    st.text_area("Your answer:", height=150, key="purpose_text", label_visibility="collapsed")

    if st.button("Continue"):
        response = st.session_state.get("purpose_text", "").strip()
        if not response:
            st.warning("Please write your answer before continuing.")
            st.stop()
        st.session_state.purpose_text_saved = response
        st.session_state.phase = 12
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 12 — DEMOGRAPHIC QUESTIONS
# ============================================================================
elif st.session_state.phase == 12:
    pos=st.session_state.phase
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
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 13 — DEBRIEFING
# ============================================================================
elif st.session_state.phase == 13:
    pos=st.session_state.phase
    st.markdown("## Debriefing")
    st.markdown("""Our study focuses on a type of artificial intelligence (AI) called a "large language model" or LLM. An LLM is a type of AI that can engage you in a conversation. We set out to measure whether LLMs could persuade people to change their judgments about the appropriateness of everyday social behaviors. This is because we are interested in seeing if it is possible to use LLMs as tools for social persuasion, that is, to influence how people think about what is or is not appropriate behavior.

When you interact with an LLM, you provide it with a "query" (an excerpt of text) and it generates a response. This response is based on the knowledge it has learned during its training. An LLM is still a machine learning system, and its knowledge is limited by the data it was trained on. It might not always provide the most accurate or up-to-date information, and it can sometimes generate responses that don't make perfect sense. However, as AI technology advances, these models continue to improve in their understanding and generation of human language.

Recent research has shown that LLMs have developed the ability to generate persuasive messages. This has raised concerns about their potential to influence how people perceive and evaluate social norms. We displayed these messages to you and other participants to observe how you may react to them. We were particularly interested in whether, after interacting with an LLM, you might report a different view on the appropriateness of everyday behaviors.

If you felt that your views were changed or influenced by the conversation, we encourage you to reflect on how and why this happened. It is important to understand that the model was designed to present arguments in a persuasive manner, and your responses contribute to our understanding of how AI can be used to impact judgments about social norms.

To reiterate, in this experiment, the messages that you were exposed to were written by AI (in the form of an LLM).

We hope that our research can contribute to a better understanding of how to make these models safer and reduce the risk of their misuse. We appreciate the time you spent participating in this experiment. You can learn more about LLMs by clicking *(TBD)*. If you have any further questions, please reach out to the researchers at *(TBD)*. As a reminder, you have the right to withdraw your responses by contacting the researcher with your Prolific ID through e-mail or through Prolific's anonymous messaging system.""")

    if st.button("Continue"):
        st.session_state.phase = 14
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 14 — FINAL COMMENTS  +  SINGLE SAVE TO GOOGLE SHEETS
# ============================================================================
elif st.session_state.phase == 14 and not st.session_state.data_saved:
    pos=st.session_state.phase
    st.markdown("You may optionally leave any comments about the study in the box below.")
    st.text_area("Comments (optional):", height=120, key="final_comments", label_visibility="collapsed")

    if st.button("Finish & Submit"):
        demographics    = st.session_state.get("demographics", {})
        total_duration  = time.time() - st.session_state.start_time
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
        ]

        try:
            save_to_google_sheets(row)
        except Exception as e:
            st.error(f"There was an error saving your data: {e}. Please contact the researchers before closing this page.")
            st.stop()

        st.session_state.data_saved = True
        st.session_state.phase = 15
        scroll_to_top()
        st.rerun()

# ============================================================================
# PHASE 15 — THANK YOU & PROLIFIC REDIRECT
# ============================================================================
elif st.session_state.phase >= 15:
    pos=st.session_state.phase
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