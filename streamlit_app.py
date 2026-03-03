import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI
import json
import os
import time
import random
from collections import defaultdict

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
NORMS = load_json("norms.json")

# ============================================================================
# GOOGLE SHEETS HELPERS
# ============================================================================
def check_prolific_id_exists(sheet, prolific_id):
    values = sheet.col_values(1)
    return prolific_id.lower() in [v.lower() for v in values[1:]]

def get_least_used_combination(sheet, prompts, norms):
    data = sheet.get_all_values()
    counts = defaultdict(int)
    for p in prompts:
        for n in norms:
            counts[(p, n)] = 0
    for row in data[1:]:
        if len(row) >= 3 and (row[1], row[2]) in counts:
            counts[(row[1], row[2])] += 1
    min_count = min(counts.values())
    return random.choice([k for k, v in counts.items() if v == min_count])

def save_to_google_sheets(sheet, row):
    sheet.append_row(row, value_input_option="RAW")

# ============================================================================
# SECRETS / CLIENTS
# ============================================================================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
sheet = gspread.authorize(creds).open_by_url(
    st.secrets["google_sheet_url"]
).sheet1

openai_client = OpenAI(api_key=st.secrets["openai_api_key"])

# ============================================================================
# PROLIFIC ID CHECK AT THE VERY START
# ============================================================================
prolific_id = st.query_params.get("PROLIFIC_PID", "")
if not prolific_id:
    st.error("Please access this study via Prolific to continue.")
    st.stop()

if "prolific_id" not in st.session_state:
    st.session_state.prolific_id = prolific_id

if "pid_checked" not in st.session_state:
    st.session_state.pid_checked = True
    if check_prolific_id_exists(sheet, prolific_id):
        st.error("This Prolific ID has already completed the study. You cannot participate again.")
        st.stop()

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
if "session_initialized" not in st.session_state:
    DEFAULTS = {
        "phase": 0,
        "messages": [],
        "greeting_sent": False,
        "conversation_ended": False,
        "data_saved": False,
        "generate_assistant": False,
        "comp_response": None,
        "engagement_text": None,
    }
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.session_state["session_initialized"] = True

# ============================================================================
# PHASE 0 — CONSENT FORM  (Pagina 1)
# ============================================================================
if st.session_state.phase == 0:
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

    if consent is not None:
        if consent == "I agree":
            if st.button("Continue"):
                st.session_state.phase = 0.5
                st.rerun()
        else:
            st.warning("Thank you for your time. You cannot proceed without consenting to participate. You may close this window.")
            st.stop()

# ============================================================================
# PHASE 0.5 — DATA QUALITY CHECK  (Pagina 1, seconda parte)
# ============================================================================
elif st.session_state.phase == 0.5:
    st.markdown("We care about the quality of our survey data. For us to fully understand your opinions, it is important that you provide careful answers to each question in this survey.")
    st.markdown("**Do you commit to thoughtfully provide your best answers to the questions in this survey?**")

    quality = st.radio(
        "Your answer:",
        options=[
            "I will try to provide my best answers",
            "I will not provide my best answers",
            "I can't promise either way"
        ],
        index=None,
        key="quality_radio"
    )

    if quality is not None:
        if quality == "I will try to provide my best answers":
            if st.button("Continue"):
                st.session_state.phase = 1
                st.rerun()
        else:
            st.warning("Thank you for your time. We require committed participants to ensure data quality. You may close this window.")
            st.stop()

# ============================================================================
# PHASE 1 — BACKGROUND QUESTION  (Pagina 2)
# ============================================================================
elif st.session_state.phase == 1:
    now = time.time()
    if "page_load_time" not in st.session_state:
        st.session_state.page_load_time = now
    if "engagement_first_interaction" not in st.session_state:
        st.session_state.engagement_first_interaction = None

    st.markdown("Please answer the question below in a few sentences. There is no right or wrong answer.")
    st.markdown("**If you could change one thing about the world, what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.**")

    def engagement_interaction_callback():
        if st.session_state.engagement_first_interaction is None:
            st.session_state.engagement_first_interaction = time.time()

    text = st.text_area(
        "Your answer:",
        height=180,
        key="engagement_text",
        on_change=engagement_interaction_callback,
        label_visibility="collapsed"
    )

    if st.button("Continue"):
        response = st.session_state.get("engagement_text", "").strip()
        if not response:
            st.warning("Please provide a response before continuing.")
            st.stop()
        st.session_state["engagement_text_saved"] = response
        st.session_state.engagement_word_count = len(response.split())

        now2 = time.time()
        st.session_state.parallel_engagement_time = now2 - st.session_state.page_load_time
        st.session_state.sequential_engagement_time = now2 - st.session_state.page_load_time
        st.session_state.interaction_engagement_time = (
            (now2 - st.session_state.engagement_first_interaction)
            if st.session_state.engagement_first_interaction else None
        )
        st.session_state.phase = 2
        st.rerun()

# ============================================================================
# PHASE 2 — INITIAL APPROPRIATENESS RATINGS  (Pagina 3)
# ============================================================================
elif st.session_state.phase == 2:
    if "prompt_key" not in st.session_state:
        prompt_key, norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
        st.session_state.prompt_key = prompt_key
        st.session_state.norm_key = norm_key
        st.session_state.start_time = time.time()

    if "sampled_norms" not in st.session_state:
        norm_data = NORMS[st.session_state.norm_key]
        new_norms = {k: v for k, v in NORMS.items() if k != st.session_state.norm_key}
        sampled_extra = random.sample(list(new_norms.values()), min(4, len(new_norms)))
        sampled_norms = sampled_extra + [norm_data]
        random.shuffle(sampled_norms)
        st.session_state.sampled_norms = sampled_norms

    sampled_norms = st.session_state.sampled_norms

    st.markdown("""From various sources in our everyday lives we have all developed a subjective "impression" or "feeling" for the appropriateness of any given behavior in a particular situation. In this study, we are interested in your judgment of the appropriateness of some particular behaviors in some particular settings.

Your task in each case is simply to rate, on a scale from 0 (completely inappropriate) to 100 (completely appropriate), the appropriateness of the particular behavior in the situation that is given.""")

    opinions = {}
    for i, norm in enumerate(sampled_norms):
        st.markdown(f"**How appropriate or inappropriate is it to {norm['title']}?**")
        opinions[norm['title']] = st.slider(
            f"0 = Completely inappropriate — 100 = Completely appropriate",
            0, 100, 50,
            key=f"slider_{i}",
            label_visibility="visible"
        )

    if st.button("Continue"):
        st.session_state.initial_opinion = opinions
        st.session_state.phase = 3
        st.rerun()

# ============================================================================
# PHASE 3 — EXPECTED OTHERS' RATINGS  (Pagina 4)
# ============================================================================
elif st.session_state.phase == 3:
    sampled_norms = st.session_state.sampled_norms

    st.markdown("""We will now ask you what you think the other participants of this study from the UK have on average rated the appropriateness of these behaviors from 0 (completely inappropriate) to 100 (completely appropriate).

We will calculate the mean responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct (±3), you will receive an additional bonus of £0.50. Only one behavior will be randomly selected for payment.""")

    opinions_others = {}
    for i, norm in enumerate(sampled_norms):
        st.markdown(f"**{norm['title']}**")
        st.markdown("Other respondents' average appropriateness rating:")
        opinions_others[norm['title']] = st.slider(
            f"0 = Completely inappropriate — 100 = Completely appropriate",
            0, 100, 50,
            key=f"group_opinion_slider_{i}",
            label_visibility="visible"
        )

    if st.button("Continue"):
        st.session_state.opinions_others = opinions_others
        st.session_state.phase = 4
        st.rerun()

# ============================================================================
# PHASE 4 — INSTRUCTIONS FOR CONVERSATION  (Pagina 5)
# ============================================================================
elif st.session_state.phase == 4:
    st.markdown("""Now, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The purpose of this dialogue is to see how humans and AI interact. Please be open and honest in your responses. Remember that the AI is neutral and non-judgmental, and your participation is confidential. When the conversation begins, you should see an AI icon with chat bubbles "..." indicating it's generating responses. It can sometimes take up to 30s. If you don't see any icons or if it's taking too long to generate responses, try refreshing the page. If you run into further issues, please let us know.

Please read each AI message thoroughly, and you may have to scroll down to read its full message. You will be asked some questions about your interaction. You will have to write at least 2 messages to the AI, up to a maximum of 10.

When the conversation is over, you should see a message at the bottom: **Scroll down and proceed to the next section.**""")

    if st.button("Start Conversation"):
        st.session_state.phase = 5
        st.rerun()

# ============================================================================
# PHASE 5 — CONVERSATION WITH LLM  (Pagina 6)
# ============================================================================
elif st.session_state.phase == 5:
    prompt_data = PROMPTS[st.session_state.prompt_key]
    norm_data = NORMS[st.session_state.norm_key]
    initial_opinion_treatment = st.session_state.initial_opinion.get(norm_data["title"], 50)
    system_prompt = prompt_data["system_prompt_template"].replace(
        "{NORM_DESCRIPTION}", norm_data["title"]
    ).replace("{INITIAL_OPINION}", str(initial_opinion_treatment))

    if not st.session_state.greeting_sent:
        reply = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Start the discussion"}
            ]
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply.choices[0].message.content,
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.greeting_sent = True
        st.rerun()

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    if "pending_user_message" not in st.session_state:
        st.session_state.pending_user_message = None

    if user_input := st.chat_input("Type your response here"):
        st.session_state.pending_user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        }
        st.rerun()

    if st.session_state.pending_user_message:
        user_msg = st.session_state.pending_user_message
        st.session_state.messages.append(user_msg)
        with st.chat_message("user"):
            st.markdown(user_msg["content"])
        st.session_state.pending_user_message = None

        if round_count < 10:
            with st.chat_message("assistant"):
                stream = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": system_prompt}] +
                             [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                    stream=True
                )
                reply_text = st.write_stream(stream)

            st.session_state.messages.append({
                "role": "assistant",
                "content": reply_text,
                "timestamp": datetime.now().isoformat()
            })
            st.rerun()
        else:
            final_message = "Thank you for your thoughtful responses! The discussion is now complete. Please scroll down and proceed to the next section."
            st.session_state.messages.append({
                "role": "assistant",
                "content": final_message,
                "timestamp": datetime.now().isoformat()
            })
            st.rerun()

    user_msgs = [m for m in st.session_state.messages if m["role"] == "user"]
    if len(user_msgs) >= 2 and st.session_state.phase == 5:
        st.markdown("---")
        st.markdown("*Scroll down and proceed to the next section.*")
        if st.button("End Discussion & Continue"):
            st.session_state.phase = 6
            st.rerun()

# ============================================================================
# PHASE 6 — ATTENTION CHECK  (Pagina 7)
# ============================================================================
elif st.session_state.phase == 6:
    norm_data = NORMS[st.session_state.norm_key]

    # Build comprehension question from last assistant message
    last_assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    last_ai_text = last_assistant_msgs[-1]["content"] if last_assistant_msgs else ""

    st.markdown("""Please read the following excerpt from your conversation with the AI and answer the question below.""")

    if last_ai_text:
        st.info(f"**AI's last message:**\n\n{last_ai_text}")

    st.markdown("**Which of the following best describes the main topic discussed with the AI?**")

    att_check_options = [norm["title"] for norm in st.session_state.sampled_norms] + ["None of the above / I don't remember"]
    att_check_response = st.radio(
        "Select one:",
        att_check_options,
        key="att_check_response",
        label_visibility="collapsed"
    )

    if st.button("Continue"):
        st.session_state["att_check_response_saved"] = st.session_state.get("att_check_response", "")
        st.session_state.phase = 7
        st.rerun()

# ============================================================================
# PHASE 7 — FINAL APPROPRIATENESS RATINGS  (Pagina 8)
# ============================================================================
elif st.session_state.phase == 7:
    sampled_norms = st.session_state.sampled_norms
    initial_opinions = st.session_state.initial_opinion

    st.markdown("We ask you again to rate, on a scale from 0 (completely inappropriate) to 100 (completely appropriate), the appropriateness of these behaviors.")

    final_opinions = {}
    for i, norm in enumerate(sampled_norms):
        title = norm["title"]
        initial_value = initial_opinions.get(title, 50)
        st.markdown(f"**How appropriate or inappropriate is it to {title}?**")
        final_opinions[title] = st.slider(
            "0 = Completely inappropriate — 100 = Completely appropriate",
            0, 100,
            initial_value,
            key=f"final_slider_{i}",
            label_visibility="visible"
        )

    if st.button("Continue"):
        st.session_state.final_opinion = final_opinions
        st.session_state.phase = 8
        st.rerun()

# ============================================================================
# PHASE 8 — FINAL EXPECTED OTHERS' RATINGS  (Pagina 9)
# ============================================================================
elif st.session_state.phase == 8:
    sampled_norms = st.session_state.sampled_norms

    st.markdown("""We will now ask you again what you think the other participants of this study from the UK have on average rated the appropriateness of these behaviors from 0 (completely inappropriate) to 100 (completely appropriate).

We will calculate the mean responses provided by the other participants the second time they were asked and compare them with the estimate you provided. If your estimate is correct (±3), you will receive an additional bonus of £0.50. Only one behavior will be randomly selected for payment.""")

    opinions_others_final = {}
    for i, norm in enumerate(sampled_norms):
        st.markdown(f"**{norm['title']}**")
        st.markdown("Other respondents' average appropriateness rating:")
        opinions_others_final[norm['title']] = st.slider(
            "0 = Completely inappropriate — 100 = Completely appropriate",
            0, 100, 50,
            key=f"group_opinion_final_slider_{i}",
            label_visibility="visible"
        )

    if st.button("Continue"):
        st.session_state.opinions_others_final = opinions_others_final
        st.session_state.phase = 9
        st.rerun()

# ============================================================================
# PHASE 9 — TIGHTNESS SCALE  (Pagina 10)
# ============================================================================
elif st.session_state.phase == 9:
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

    scale_labels = ["Strongly disagree", "Moderately disagree", "Slightly disagree", "Slightly agree", "Moderately agree", "Strongly agree"]
    scale_values = [1, 2, 3, 4, 5, 6]

    tightness_responses = {}
    for i, item in enumerate(tightness_items):
        st.markdown(f"**{item}**")
        cols = st.columns(6)
        selected = st.session_state.get(f"tight_{i}", None)
        for j, (label, val) in enumerate(zip(scale_labels, scale_values)):
            with cols[j]:
                if st.button(label, key=f"tight_{i}_{val}", use_container_width=True,
                             type="primary" if selected == val else "secondary"):
                    st.session_state[f"tight_{i}"] = val
                    st.rerun()
        if selected:
            tightness_responses[item] = selected
        st.markdown("")

    st.markdown("---")
    tightness_open = st.text_area(
        "Is there anything you would like to add or do you want to clarify about your answers?",
        height=100,
        key="tightness_open"
    )

    if st.button("Continue"):
        # Check all items answered
        missing = [i for i in range(len(tightness_items)) if not st.session_state.get(f"tight_{i}")]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        for i, item in enumerate(tightness_items):
            tightness_responses[item] = st.session_state.get(f"tight_{i}")
        st.session_state.tightness_responses = tightness_responses
        st.session_state.tightness_open = st.session_state.get("tightness_open", "")
        st.session_state.phase = 10
        st.rerun()

# ============================================================================
# PHASE 10 — CONVERSATION PERCEPTION  (Pagina 11)
# ============================================================================
elif st.session_state.phase == 10:
    st.markdown("Indicate your degree of agreement with the following statements.")

    st.markdown("#### Involvement")
    st.markdown("The messages I read during the conversation with the AI:")

    involvement_items = [
        ("They got me involved.", "involvement_0"),
        ("They seemed relevant to me.", "involvement_1"),
        ("They interested me.", "involvement_2"),
    ]

    involvement_responses = {}
    for label, key in involvement_items:
        st.markdown(f"**{label}**")
        cols = st.columns(7)
        for j in range(1, 8):
            with cols[j - 1]:
                col_label = str(j)
                if j == 1:
                    col_label = f"1\nTotally disagree"
                elif j == 7:
                    col_label = f"7\nTotally agree"
                selected = st.session_state.get(key)
                if st.button(str(j), key=f"{key}_{j}", use_container_width=True,
                             type="primary" if selected == j else "secondary"):
                    st.session_state[key] = j
                    st.rerun()
        if st.session_state.get(key):
            involvement_responses[label] = st.session_state[key]
        st.markdown("")

    st.markdown("#### Perceived Threat")
    st.markdown("The messages I read during the conversation with the AI:")

    threat_items = [
        ("They tried to manipulate me.", "threat_0"),
        ("They tried to pressure me.", "threat_1"),
        ("They undermined my sense of self-worth.", "threat_2"),
        ("They made me feel less than capable.", "threat_3"),
        ("They made me think I should change.", "threat_4"),
    ]

    threat_responses = {}
    for label, key in threat_items:
        st.markdown(f"**{label}**")
        cols = st.columns(7)
        for j in range(1, 8):
            with cols[j - 1]:
                selected = st.session_state.get(key)
                if st.button(str(j), key=f"{key}_{j}", use_container_width=True,
                             type="primary" if selected == j else "secondary"):
                    st.session_state[key] = j
                    st.rerun()
        if st.session_state.get(key):
            threat_responses[label] = st.session_state[key]
        st.markdown("")

    st.markdown("#### Evaluation of the Source")
    st.markdown("To what extent the source of these messages is:")

    source_items = [
        ("Reliable", "source_0"),
        ("Trusted", "source_1"),
        ("Honest", "source_2"),
        ("Competent", "source_3"),
        ("Expert", "source_4"),
        ("Informed", "source_5"),
    ]

    source_responses = {}
    for label, key in source_items:
        st.markdown(f"**{label}**")
        cols = st.columns(7)
        for j in range(1, 8):
            with cols[j - 1]:
                selected = st.session_state.get(key)
                if st.button(str(j), key=f"{key}_{j}", use_container_width=True,
                             type="primary" if selected == j else "secondary"):
                    st.session_state[key] = j
                    st.rerun()
        if st.session_state.get(key):
            source_responses[label] = st.session_state[key]
        st.markdown("")

    st.markdown("*Scale: 1 = Totally disagree — 7 = Totally agree*")

    if st.button("Continue"):
        all_keys = (
            [k for _, k in involvement_items] +
            [k for _, k in threat_items] +
            [k for _, k in source_items]
        )
        missing = [k for k in all_keys if not st.session_state.get(k)]
        if missing:
            st.warning("Please respond to all statements before continuing.")
            st.stop()
        st.session_state.involvement_responses = {l: st.session_state[k] for l, k in involvement_items}
        st.session_state.threat_responses = {l: st.session_state[k] for l, k in threat_items}
        st.session_state.source_responses = {l: st.session_state[k] for l, k in source_items}
        st.session_state.phase = 11
        st.rerun()

# ============================================================================
# PHASE 11 — PURPOSE OF STUDY  (Pagina 12)
# ============================================================================
elif st.session_state.phase == 11:
    st.markdown("**What do you think is the purpose of this study?**")

    purpose_text = st.text_area(
        "Please write your answer below:",
        height=150,
        key="purpose_text",
        label_visibility="collapsed"
    )

    if st.button("Continue"):
        response = st.session_state.get("purpose_text", "").strip()
        if not response:
            st.warning("Please write your answer before continuing.")
            st.stop()
        st.session_state.purpose_text = response
        st.session_state.phase = 12
        st.rerun()

# ============================================================================
# PHASE 12 — DEMOGRAPHIC QUESTIONS  (Pagina 13)
# ============================================================================
elif st.session_state.phase == 12:
    st.markdown("Please answer the following questions about yourself.")
    st.markdown("---")

    # Age
    age = st.selectbox(
        "How old are you, in years?",
        options=["Select..."] + list(range(18, 101)),
        key="demo_age"
    )

    # Location in UK
    uk_location = st.selectbox(
        "Where do you live (in the UK)?",
        options=["Select...", "England", "Wales", "Scotland", "Northern Ireland"],
        key="demo_location"
    )

    # Gender
    st.markdown("**What is your gender?**")
    gender = st.radio(
        "Gender:",
        options=["Male", "Female", "Other"],
        horizontal=True,
        key="demo_gender",
        label_visibility="collapsed"
    )

    # Student
    st.markdown("**Are you currently enrolled as a student?**")
    student = st.radio(
        "Student:",
        options=["Yes", "No"],
        horizontal=True,
        key="demo_student",
        label_visibility="collapsed"
    )

    # Education
    education = st.selectbox(
        "What is the highest level of education you have completed, or the highest degree you have received?",
        options=[
            "Select...",
            "Less than high school degree (less than 12 years in school)",
            "High school graduate (12 or more years in school)",
            "Some college but no degree",
            "Bachelor's/Associate degree",
            "Master's degree",
            "Doctoral degree"
        ],
        key="demo_education"
    )

    # Political orientation
    st.markdown("**Here is a 7-point scale on which the political views that people might hold are arranged from extremely liberal (left) to extremely conservative (right). Where would you place yourself on this scale?**")
    col1, col2, col3 = st.columns([1, 6, 1])
    with col1:
        st.markdown("Extremely liberal (left)")
    with col2:
        politics = st.slider(
            "Political orientation:",
            1, 7, 4,
            key="demo_politics",
            label_visibility="collapsed"
        )
    with col3:
        st.markdown("Extremely conservative (right)")

    # Social ladder
    st.markdown("""**Think of this ladder as representing where people stand in the UK. At the top of the ladder are the people who are the best off – those who have the most money, the most education, and the most respected jobs. At the bottom are the people who are the worst off – those who have the least money, least education, the least respected jobs, or no job. The higher up you are on this ladder, the closer you are to the people at the very top; the lower you are, the closer you are to the people at the very bottom.**

Where would you place yourself on this ladder?""")

    ladder = st.select_slider(
        "Social ladder position (1 = bottom, 10 = top):",
        options=list(range(1, 11)),
        value=5,
        key="demo_ladder",
        label_visibility="visible"
    )

    if st.button("Continue"):
        errors = []
        if age == "Select...":
            errors.append("Please select your age.")
        if uk_location == "Select...":
            errors.append("Please select where you live in the UK.")
        if education == "Select...":
            errors.append("Please select your education level.")
        if errors:
            for e in errors:
                st.warning(e)
            st.stop()

        st.session_state.demographics = {
            "age": age,
            "uk_location": uk_location,
            "gender": gender,
            "student": student,
            "education": education,
            "politics": politics,
            "social_ladder": ladder
        }
        st.session_state.phase = 13
        st.rerun()

# ============================================================================
# PHASE 13 — DEBRIEFING  (Pagina 14)
# ============================================================================
elif st.session_state.phase == 13:
    st.markdown("## Debriefing")
    st.markdown("""Our study focuses on a type of artificial intelligence (AI) called a "large language model" or LLM. An LLM is a type of AI that can engage you in a conversation. We set out to measure whether LLMs could persuade people to change their judgments about the appropriateness of everyday social behaviors. This is because we are interested in seeing if it is possible to use LLMs as tools for social persuasion, that is, to influence how people think about what is or is not appropriate behavior.

When you interact with an LLM, you provide it with a "query" (an excerpt of text) and it generates a response. This response is based on the knowledge it has learned during its training. An LLM is still a machine learning system, and its knowledge is limited by the data it was trained on. It might not always provide the most accurate or up-to-date information, and it can sometimes generate responses that don't make perfect sense. However, as AI technology advances, these models continue to improve in their understanding and generation of human language.

Recent research has shown that LLMs have developed the ability to generate persuasive messages. This has raised concerns about their potential to influence how people perceive and evaluate social norms. We displayed these messages to you and other participants to observe how you may react to them. We were particularly interested in whether, after interacting with an LLM, you might report a different view on the appropriateness of everyday behaviors.

If you felt that your views were changed or influenced by the conversation, we encourage you to reflect on how and why this happened. It is important to understand that the model was designed to present arguments in a persuasive manner, and your responses contribute to our understanding of how AI can be used to impact judgments about social norms.

To reiterate, in this experiment, the messages that you were exposed to were written by AI (in the form of an LLM).

We hope that our research can contribute to a better understanding of how to make these models safer and reduce the risk of their misuse. We appreciate the time you spent participating in this experiment. You can learn more about LLMs by clicking *(TBD)*. If you have any further questions, please reach out to the researchers at *(TBD)*. As a reminder, you have the right to withdraw your responses by contacting the researcher with your Prolific ID through e-mail or through Prolific's anonymous messaging system.""")

    if st.button("Continue"):
        st.session_state.phase = 14
        st.rerun()

# ============================================================================
# PHASE 14 — FINAL COMMENTS & SAVE DATA  (Pagina 15)
# ============================================================================
elif st.session_state.phase == 14 and not st.session_state.data_saved:
    st.markdown("You may optionally leave any comments about the study in the box below.")

    final_comments = st.text_area(
        "Comments (optional):",
        height=120,
        key="final_comments",
        label_visibility="collapsed"
    )

    if st.button("Finish & Submit"):
        total_duration = time.time() - st.session_state.start_time

        user_word_count = sum(
            len(m["content"].split())
            for m in st.session_state.messages
            if m["role"] == "user"
        )

        demographics = st.session_state.get("demographics", {})

        row = [
            st.session_state.prolific_id,
            st.session_state.prompt_key,
            st.session_state.norm_key,
            # Initial opinions (Pagina 3)
            json.dumps(st.session_state.initial_opinion, ensure_ascii=False),
            # Expected others' opinions (Pagina 4)
            json.dumps(st.session_state.opinions_others, ensure_ascii=False),
            # Conversation (Pagina 6)
            json.dumps(st.session_state.messages, ensure_ascii=False),
            # Attention check (Pagina 7)
            str(st.session_state.get("att_check_response_saved", "")),
            # Final opinions (Pagina 8)
            json.dumps(st.session_state.final_opinion, ensure_ascii=False),
            # Final expected others' opinions (Pagina 9)
            json.dumps(st.session_state.opinions_others_final, ensure_ascii=False),
            # Tightness (Pagina 10)
            json.dumps(st.session_state.get("tightness_responses", {}), ensure_ascii=False),
            str(st.session_state.get("tightness_open", "")),
            # Conversation perception (Pagina 11)
            json.dumps(st.session_state.get("involvement_responses", {}), ensure_ascii=False),
            json.dumps(st.session_state.get("threat_responses", {}), ensure_ascii=False),
            json.dumps(st.session_state.get("source_responses", {}), ensure_ascii=False),
            # Purpose of study (Pagina 12)
            str(st.session_state.get("purpose_text", "")),
            # Demographics (Pagina 13)
            str(demographics.get("age", "")),
            str(demographics.get("uk_location", "")),
            str(demographics.get("gender", "")),
            str(demographics.get("student", "")),
            str(demographics.get("education", "")),
            str(demographics.get("politics", "")),
            str(demographics.get("social_ladder", "")),
            # Background question (Pagina 2)
            str(st.session_state.get("engagement_text_saved", "")),
            st.session_state.get("engagement_word_count", 0),
            # Final comments (Pagina 15)
            str(st.session_state.get("final_comments", "")),
            # Conversation stats
            len([m for m in st.session_state.messages if m["role"] == "user"]),
            user_word_count,
            total_duration,
            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)
        st.session_state.data_saved = True
        st.session_state.phase = 15
        st.rerun()

# ============================================================================
# PHASE 15 — THANK YOU & PROLIFIC REDIRECT  (Fine studio)
# ============================================================================
if st.session_state.phase >= 15:
    st.markdown("## Thank you for participating.")
    st.markdown("""Your responses have been successfully recorded.

Please click the button below to finish the study and retrieve your Prolific completion code.""")

    prolific_id_val = st.session_state.get("prolific_id", "")
    completion_base_url = "https://www.prolific.co/"
    completion_url = f"{completion_base_url}?PROLIFIC_PID={prolific_id_val}"

    st.markdown(f"[**→ Return to Prolific to complete your submission**]({completion_url})", unsafe_allow_html=True)