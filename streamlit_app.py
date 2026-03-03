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
# COMPREHENSION QUESTION (MASKED ATTENTION CHECK)
# ============================================================================
COMPREHENSION_QUESTION = {
    "question": '''People get their news from a variety of sources, and in today’s world reliance on on-line news sources is increasingly common. 
    To show that you’ve read this much, please select “Television or print news only” as your answer.''',
    "options": [
        "On-line sources only",
        "Mostly on-line sources with some television and print news",
        "About half on-line sources",
        "Mostly television or print news with some on-line sources",
        "Television or print news only"
    ],
    "correct": "Television or print news only"
}

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

# Check PID only at the start
if "pid_checked" not in st.session_state:
    st.session_state.pid_checked = True
    if check_prolific_id_exists(sheet, prolific_id):
        st.error("This Prolific ID has already completed the study. You cannot participate again.")
        st.stop()

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
# ----------------------------
# Session state defaults (only run once)
# ----------------------------
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
# PHASE 0 — CONSENT FORM
# ============================================================================
if st.session_state.phase == 0:
    st.markdown("## Thank you for joining our study!")
    st.markdown("""
**Before proceeding, please read carefully the information reported below.**

**Aim of the Study**
You are being invited to participate in a study of social norms. The purpose of this study is to analyze everyday norms – i.e., norms about behavior that many people perform regularly, and most people could perform if they wanted to – and to understand how people engage in conversations about these topics with an advanced AI.

**What will I be asked to do?**
If you agree to take part, you will be asked to answer a set of survey questions related to social norms. These include questions about how appropriate you and other people think behaviors are in different settings. Concerning questions about how other people perceive behaviors, you will receive a bonus payment if you make a correct guess. Next, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The study should take approximately *(da definire)* minutes to complete.

**Can I change my mind?**
Participation is voluntary and you can decline to participate in the research or any aspects of the research at any time without penalty. You may withdraw by simply closing the browser on the computer. It will not be possible for you to withdraw after the completion of the survey because your responses are anonymous.

**Risks and benefits**
There are no direct benefits to you as a participant. Study results will help inform the scholarly understanding of AI conversations about everyday norms work. There is a risk that some of the questions may be sensitive and/or could cause you psychological distress. You don't have to answer any questions you don't want to. There are questions where you will receive a bonus payment of £0.50 if you answer correctly (two questions, for a maximum of £1).

**Privacy and data**
The data that you provide will be anonymous so your responses cannot be linked back to you. The study data will be stored on an encrypted server at *(da definire)*. The anonymous dataset will be stored indefinitely and shared with other researchers for research and teaching purposes. We plan to publish the results of this study in academic journals and present them at conferences.

**Any questions?**
If you have any questions about the research, please contact *(da definire)*.

By clicking "I agree" below you are indicating that you have read this information and agree to participate in this research study.
""")

    consent = st.radio(
        "Do you agree to participate?",
        options=["I agree", "I do not agree"],
        index=None,
        key="consent_radio"
    )

    if consent == "I agree":
        if st.button("Continue"):
            st.session_state.phase = 0.5
            st.rerun()
    elif consent == "I do not agree":
        st.warning("Thank you for your time. You cannot proceed without consenting to participate.")
        st.stop()

# ============================================================================
# PHASE 0.5 — DATA QUALITY CHECK
# ============================================================================
elif st.session_state.phase == 0.5:
    st.markdown("## Before we begin")
    st.markdown("""
We care about the quality of our survey data. For us to fully understand your opinions, it is important that you provide careful answers to each question in this survey.

**Do you commit to thoughtfully provide your best answers to the questions in this survey?**
""")

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

    if quality == "I will try to provide my best answers":
        if st.button("Continue"):
            st.session_state.phase = 1
            st.rerun()
    elif quality in ["I will not provide my best answers", "I can't promise either way"]:
        st.warning("Thank you for your time. We require committed participants to ensure data quality.")
        st.stop()

# ============================================================================
# PHASE 1 — WELCOME & INSTRUCTIONS
# ============================================================================
elif st.session_state.phase == 1:
    st.markdown("## Welcome")
    st.markdown("""
    Thank you for taking part in this study.

    You will:
    - Answer a few short questions
    - Have a brief discussion with an AI system
    - Share your opinion before and after the discussion

    Please complete the study in one sitting and respond thoughtfully.
    """)
    if st.button("Begin"):
        st.session_state.phase = 2
        st.rerun()

# ============================================================================
# PHASE 1 — COMPREHENSION + BACKGROUND (SAME PAGE, 3 TIMERS)
# ============================================================================
elif st.session_state.phase == 1:
    # =========================
    # INITIALIZE TIMERS
    # =========================
    now = time.time()

    if "page_load_time" not in st.session_state:
        st.session_state.page_load_time = now  # Parallel timer baseline

    if "comp_start_time_seq" not in st.session_state:
        st.session_state.comp_start_time_seq = now  # Sequential Q1 start

    if "comp_first_interaction" not in st.session_state:
        st.session_state.comp_first_interaction = None

    if "engagement_start_time_seq" not in st.session_state:
        st.session_state.engagement_start_time_seq = None

    if "engagement_first_interaction" not in st.session_state:
        st.session_state.engagement_first_interaction = None

    # =========================
    # PLACEHOLDERS
    # =========================
    comp_container = st.empty()
    engagement_container = st.empty()


    # =========================
    # QUESTION 1 — COMPREHENSION
    # =========================

    def comp_interaction_callback():
        if st.session_state.comp_first_interaction is None:
            st.session_state.comp_first_interaction = time.time()

        # Start Q2 sequential timer once Q1 answered
        if st.session_state.engagement_start_time_seq is None:
            st.session_state.engagement_start_time_seq = time.time()

    st.markdown("---")
    with comp_container.container():
        st.markdown("## Background Questions")
        st.markdown('''In this section, you will answer two brief questions. Please: \n- Read each question carefully.\n- Select or write the response that best reflects your view. \n- Respond thoughtfully and independently. \nAfter clicking continue, you will proceed to the next part of the study.''')
        st.markdown("---")
        st.markdown("### Question 1")
        st.markdown(COMPREHENSION_QUESTION["question"])
        response = st.radio(
            COMPREHENSION_QUESTION["question"],
            COMPREHENSION_QUESTION["options"],
            key="comp_response",
            on_change=comp_interaction_callback,
            label_visibility="collapsed"
        )


    # =========================
    # QUESTION 2 — BACKGROUND
    # =========================
    if st.session_state.get("comp_response"):

        with engagement_container.container():
            st.markdown("---")
            st.markdown("### Question 2")
            st.markdown("If you could change one thing about the world what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.")
            def engagement_interaction_callback():
                if st.session_state.engagement_first_interaction is None:
                    st.session_state.engagement_first_interaction = time.time()

            text = st.text_area(
                "If you could change one thing about the world what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.",
                height=150,
                key="engagement_text",
                on_change=lambda: st.session_state.update({"engagement_first_interaction": time.time()}),
                label_visibility="collapsed"
            )

    else:
        engagement_container.empty()
        st.info("Please answer the first question to continue.")

    # =========================
    # SUBMIT BUTTON
    # =========================
    if st.button("Continue"):
        # Force-save responses to session state
        st.session_state["comp_response_saved"] = st.session_state.get("comp_response", "")
        st.session_state["engagement_text_saved"] = st.session_state.get("engagement_text", "")

        # Validation
        if not st.session_state["comp_response_saved"]:
            st.warning("Please answer the first question before continuing.")
            st.stop()

        if st.session_state["engagement_text_saved"] == "":
            st.warning("Please provide a response to the second question before continuing.")
            st.stop()

        now = time.time()

        # -------- PARALLEL --------
        parallel_comp_time = now - st.session_state.page_load_time
        parallel_engagement_time = now - st.session_state.page_load_time

        # -------- SEQUENTIAL --------
        sequential_comp_time = now - st.session_state.comp_start_time_seq

        sequential_engagement_time = None
        if st.session_state.engagement_start_time_seq:
            sequential_engagement_time = (
                now - st.session_state.engagement_start_time_seq
            )

        # -------- INTERACTION --------
        interaction_comp_time = None
        if st.session_state.comp_first_interaction:
            interaction_comp_time = (
                now - st.session_state.comp_first_interaction
            )

        interaction_engagement_time = None
        if st.session_state.engagement_first_interaction:
            interaction_engagement_time = (
                now - st.session_state.engagement_first_interaction
            )

        # Save responses
        st.session_state.comp_correct = (
            st.session_state.comp_response == COMPREHENSION_QUESTION["correct"]
        )

        st.session_state.engagement_word_count = len(
            st.session_state.get("engagement_text_saved", "").split()
        )

        # Store ALL timing variables
        st.session_state.parallel_comp_time = parallel_comp_time
        st.session_state.parallel_engagement_time = parallel_engagement_time
        st.session_state.sequential_comp_time = sequential_comp_time
        st.session_state.sequential_engagement_time = sequential_engagement_time
        st.session_state.interaction_comp_time = interaction_comp_time
        st.session_state.interaction_engagement_time = interaction_engagement_time

        st.session_state.phase = 2
        st.rerun()

# ============================================================================
# PHASE 3 — INITIAL OPINION
# ============================================================================
elif st.session_state.phase == 2:
    if "prompt_key" not in st.session_state:
        prompt_key, norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
        st.session_state.prompt_key = prompt_key
        st.session_state.norm_key = norm_key
        st.session_state.start_time = time.time()

    # Store sampled & shuffled norms only once
    if "sampled_norms" not in st.session_state:
        norm_data = NORMS[st.session_state.norm_key]

        # Remove current norm and sample 2 more
        new_norms = {k: v for k, v in NORMS.items() if k != st.session_state.norm_key}
        sampled_norms = random.sample(list(new_norms.values()), 2)
        sampled_norms.append(norm_data)  # append the original norm object
        random.shuffle(sampled_norms)

        st.session_state.sampled_norms = sampled_norms
    else:
        sampled_norms = st.session_state.sampled_norms

    st.markdown("## Your Initial Opinion")
    st.markdown("We ask you to indicate how appropriate you consider each of the following behaviors, where 0 means very inappropriate and 100 means highly appropriate.")
    opinions = {}

    # Loop over stored sampled norms
    for i, norm in enumerate(sampled_norms):
        opinions[norm['title']] = st.slider(
            f"**{norm['title']}**",
            0, 100, 50,
            key=f"slider_{i}",
        )

    if st.button("Continue"):
        st.session_state.initial_opinion = opinions
        st.session_state.phase = 3
        st.rerun() 

#PHASE 3 - GROUP OPINION
elif st.session_state.phase == 3:  
    st.markdown("## How do you rate others’ opinion?")
    st.markdown("We ask you to indicate what do you think the other participants of this study have on average reported as an answer to the appropiateness of the following behaviors, where 0 means very inappropriate and 100 means highly appropriate.\nWe will calculate the responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct, you will receive an additional bonus of £1/£0.50.")
    sampled_norms = st.session_state.sampled_norms
    opinions_others = {}
    for i, norm in enumerate(sampled_norms):
        opinions_others[norm['title']] = st.slider(
            f"**{norm['title']}**",
            0, 100, 50,
            key=f"group_opinion_slider_{i}",
        )

    if st.button("Continue"):
        st.session_state.opinions_others = opinions_others
        st.session_state.phase = 4  # move to pre-conversation phase
        st.rerun()

#PHASE 4 - INSTRUCTIONS FOR CONVERSATION
elif st.session_state.phase == 4:
    st.markdown("## Instructions for Conversation")
    st.markdown('''Next, you will participate in a conversation with an advanced AI about some of the topics and opinions that you have already answered questions about earlier. The purpose of this dialogue is to see how humans and AI interact. Please be open and honest in your responses. Remember that the AI is neutral and non-judgmental, and your participation is confidential. When the conversation begins, you should see an AI icon with chat bubbles "..." indicating it's generating responses. It can sometimes take up to 30s. If you don't see any icons or if it's taking too long to generate responses, try refreshing the page. If you run into further issues, please let us know.\n Please read each AI message thoroughly, as you may have to scroll down to read its full message. You will be asked some questions about your interaction.\n After a minimum of 3 conversational rounds you can exit the conversation and proceed to the next section. You can have a maximum of 10 rounds of conversation.''')
    if st.button("Start Conversation"):
        st.session_state.phase = 5  # move to conversation phase
        st.rerun()


# PHASE 5 — CONVERSATION
elif st.session_state.phase == 5:  
    prompt_data = PROMPTS[st.session_state.prompt_key]
    norm_data = NORMS[st.session_state.norm_key]
    initial_opinion_treatment = st.session_state.initial_opinion.get(norm_data["title"], 50)
    system_prompt = prompt_data["system_prompt_template"].replace(
        "{NORM_DESCRIPTION}", norm_data["title"]
    ).replace("{INITIAL_OPINION}", str(initial_opinion_treatment))
    #Print for debugging
    #st.write("System Prompt:", system_prompt)

    # Initial greeting
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

    # Display all messages
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    # Capture pending user input
    if "pending_user_message" not in st.session_state:
        st.session_state.pending_user_message = None

    if user_input := st.chat_input("Type your response here"):
        st.session_state.pending_user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        }
        st.rerun()  # rerun to render user message first

    # If pending user message, append and display it
    if st.session_state.pending_user_message:
        user_msg = st.session_state.pending_user_message
        st.session_state.messages.append(user_msg)
        with st.chat_message("user"):
            st.markdown(user_msg["content"])
        st.session_state.pending_user_message = None

        # Generate assistant response only if < 10 rounds
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
            # 10th round completed — final assistant message
            final_message = "Thank you for your thoughtful responses! The discussion is now complete. Please click the button below to proceed with the study."
            st.session_state.messages.append({
                "role": "assistant",
                "content": final_message,
                "timestamp": datetime.now().isoformat()
            })

            # Automatically move to next phase
            #st.session_state.phase = 5
            st.rerun()

    # Show "End Discussion" button after 3 rounds (before 10 rounds)
    if round_count >= 3 and st.session_state.phase == 5:
        if st.button("End Discussion"):
            st.session_state.phase = 6
            st.rerun()


# ============================================================================
# PHASE 6 — FINAL OPINION
# ============================================================================
elif st.session_state.phase == 6 and not st.session_state.data_saved:

    st.markdown("## Final Opinion")
    st.markdown("After the discussion, how appropriate do you consider this behaviors are? You can adjust the sliders to reflect any change in your opinion after the discussion, where 0 means very inappropriate and 100 means highly appropriate.")

    sampled_norms = st.session_state.sampled_norms
    initial_opinions = st.session_state.initial_opinion

    final_opinions = {}

    # Show sliders in SAME ORDER as Phase 3
    for i, norm in enumerate(sampled_norms):

        title = norm["title"]
        initial_value = initial_opinions.get(title, 50)

        final_opinions[title] = st.slider(
            f"**{title}**",
            0, 100,
            initial_value,  # ← initialize at original response
            key=f"final_slider_{i}"
        )

    if st.button("Continue"):
        st.session_state.final_opinion = final_opinions
        st.session_state.phase = 7  # move to final opinion phase
        st.rerun()

# PHASE 7 - FINAL GROUP OPINION
elif st.session_state.phase == 7:
    st.markdown("## How do you rate others’ opinion?")
    st.markdown("After the discussion, what do you think the other participants of this study have on average reported as an answer to the appropiateness of the following behaviors when asked a second time, where 0 means very inappropriate and 100 means highly appropriate.\nWe will calculate the responses provided by the other participants and compare them with the estimate you provided. If your estimate is correct, you will receive an additional bonus of £1/£0.50.")
    sampled_norms = st.session_state.sampled_norms
    opinions_others_final = {}
    for i, norm in enumerate(sampled_norms):
        opinions_others_final[norm['title']] = st.slider(
            f"**{norm['title']}**",
            0, 100, 50,
            key=f"group_opinion_final_slider_{i}",
        )

    if st.button("Continue"):
        st.session_state.opinions_others_final = opinions_others_final
        st.session_state.phase = 8  # move to final questionnaire phase
        st.rerun()

# PHASE 8 - ATTENTION CHECK
elif st.session_state.phase == 8:
    st.markdown("## What did you discuss with the AI?")
    st.markdown("Select the topic that you discussed with the AI in the conversation section. If you don't remember, please select the option that best matches your discussion.")
    att_check_options = [norm["title"] for norm in st.session_state.sampled_norms] + ["None of the above / I don't remember"]
    att_check_response = st.radio(
        "Which topic did you discuss with the AI?",
        att_check_options,
        key="att_check_response",
        label_visibility="collapsed"
    )

    if st.button("Continue"):
        st.session_state["att_check_response_saved"] = st.session_state.get("att_check_response", "")
        st.session_state.phase = 9  # move to final questionnaire phase
        st.rerun()

#Final Questionnaire (Multiple option questions)
elif st.session_state.phase == 9:
    st.markdown("## Final Questionnaire")
    st.markdown("###  Indicate your degree of agreement with the following statements (where 1 means strongly disagree and 7 means strongly agree).")
    st.markdown("---")
    st.markdown("#### The messages I read:")
    involvement_responses = {}
    for i, statement in enumerate(["Got me involved", "Seemed relevant to me", "Interested me"]):
        involvement_responses[statement] = st.slider(
            f"**{statement}**",
            1, 7, 4,
            key=f"involvement_slider_{i}"
        )
    st.markdown("---")
    st.markdown("#### The messages I read:")
    threat_responses = {}
    for i, statement in enumerate(["Tried to manipulate me", "Tried to pressure me", "Undermined my sense of self-worth", "Made me feel less than capable", "Made me think I should change"]):
        threat_responses[statement] = st.slider(
            f"**{statement}**",
            1, 7, 4,
            key=f"threat_slider_{i}"
        )

    st.markdown("---")
    st.markdown("#### To what extent the source of these messages is:")
    source_responses = {}
    for i, statement in enumerate(["Reliable", "Trusted", "Honest", "Competent", "Expert", "Informed"]):
        source_responses[statement] = st.slider(
            f"**{statement}**",
            1, 7, 4,
            key=f"source_slider_{i}"
        )


    if st.button("Submit Responses"):

        total_duration = time.time() - st.session_state.start_time

        user_word_count = sum(
            len(m["content"].split())
            for m in st.session_state.messages
            if m["role"] == "user"
        )

        row = [
            st.session_state.prolific_id,
            st.session_state.prompt_key,
            st.session_state.norm_key,
            json.dumps(st.session_state.initial_opinion, ensure_ascii=False),
            json.dumps(st.session_state.messages, ensure_ascii=False),
            json.dumps(st.session_state.final_opinion, ensure_ascii=False),  # ← store all final opinions
            json.dumps(st.session_state.opinions_others, ensure_ascii=False),
            json.dumps(st.session_state.opinions_others_final, ensure_ascii=False),
            str(st.session_state.get("att_check_response_saved", "")),
            json.dumps(involvement_responses, ensure_ascii=False),
            json.dumps(threat_responses, ensure_ascii=False),
            json.dumps(source_responses, ensure_ascii=False),
            str(st.session_state.get("comp_response_saved", "")),
            st.session_state.comp_correct,

            # Parallel
            st.session_state.parallel_comp_time,
            st.session_state.parallel_engagement_time,

            # Sequential
            st.session_state.sequential_comp_time,
            st.session_state.sequential_engagement_time,

            # Interaction
            st.session_state.interaction_comp_time,
            st.session_state.interaction_engagement_time,

            # Engagement content
            str(st.session_state.get("engagement_text_saved", "")),
            st.session_state.engagement_word_count,

            len([m for m in st.session_state.messages if m["role"] == "user"]),
            user_word_count,
            total_duration,
            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)

        st.session_state.data_saved = True
        st.session_state.phase = 10  # move to thank you phase
        st.rerun()
# ============================================================================
# PHASE 6 — THANK YOU & PROLIFIC REDIRECT
# ============================================================================
if st.session_state.phase >= 10:

    st.markdown("## Thank you for your participation")
    st.markdown("""
    Your responses have been successfully recorded.

    The link below will redirect you immediately to Prolific:""")

    # Replace with your actual Prolific completion code
    prolific_id = st.session_state.get("prolific_id", "")
    # Safe placeholder for testing; replace with your real Prolific completion code
    completion_base_url = "https://www.prolific.co/"
    completion_url = f"{completion_base_url}?PROLIFIC_PID={prolific_id}"

    st.markdown(f"[Return to Prolific immediately]({completion_url})", unsafe_allow_html=True)