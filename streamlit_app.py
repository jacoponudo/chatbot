import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI
import json

# Page configuration
st.set_page_config(
    page_title="Everyday Norm Experiment",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for elegant design
st.markdown("""
<style>
    * {
        font-family: 'Segoe UI', Trebuchet MS, sans-serif;
    }
    
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #f5f7fa 0%, #f8f9fb 100%);
    }
    
    [data-testid="stMainBlockContainer"] {
        padding: 2rem 3rem;
    }
    
    .header-container {
        display: flex;
        align-items: center;
        gap: 2rem;
        margin-bottom: 3rem;
        padding-bottom: 2rem;
        border-bottom: 1px solid #e5e7eb;
    }
    
    .cnr-logo {
        font-size: 2.5rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: #003d82;
    }
    
    .cnr-tagline {
        color: #666;
        font-size: 0.95rem;
        margin-top: 0.5rem;
    }
    
    .title-section h1 {
        font-size: 2rem;
        font-weight: 600;
        color: #1a1a1a;
        margin: 0;
        letter-spacing: -0.3px;
    }
    
    .title-section p {
        color: #666;
        font-size: 1rem;
        margin-top: 0.5rem;
    }
    
    [data-testid="stForm"] {
        background: white;
        padding: 2.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb;
    }
    
    [data-testid="stForm"] label {
        font-weight: 500;
        color: #333;
        font-size: 0.95rem;
        margin-bottom: 0.5rem;
    }
    
    [data-testid="stTextInput"] input {
        border: 1.5px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease;
    }
    
    [data-testid="stTextInput"] input:focus {
        border-color: #003d82 !important;
        box-shadow: 0 0 0 3px rgba(0, 61, 130, 0.1) !important;
    }
    
    button[kind="primary"] {
        background: linear-gradient(135deg, #003d82 0%, #004a9e 100%);
        color: white !important;
        border: none !important;
        padding: 0.75rem 2rem !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease;
        margin-top: 1.5rem;
    }
    
    button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(0, 61, 130, 0.3);
        transform: translateY(-1px);
    }
    
    .success-badge {
        background: #f0fdf4;
        color: #166534;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #22c55e;
        margin-bottom: 2rem;
        font-weight: 500;
    }
    
    [data-testid="chatAvatarIcon-assistant"], [data-testid="chatAvatarIcon-user"] {
        display: none !important;
    }
    
    [role="presentation"] [data-testid="stChatMessage"] {
        background: transparent !important;
        padding: 1rem 0 !important;
    }
    
    [data-testid="stChatMessageContent"] {
        background: white;
        padding: 1.25rem 1.5rem;
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        line-height: 1.6;
        color: #333;
        font-size: 0.95rem;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageContent"] p) > div:first-child {
        margin-right: auto;
        max-width: 85%;
    }
    
    [data-testid="stChatMessage"]:last-child [data-testid="stChatMessageContent"] {
        background: linear-gradient(135deg, #f3f4f6 0%, #ffffff 100%);
    }
    
    [data-testid="stChatInputTextArea"] textarea {
        border: 1.5px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        font-size: 0.95rem !important;
    }
    
    [data-testid="stChatInputTextArea"] textarea:focus {
        border-color: #003d82 !important;
        box-shadow: 0 0 0 3px rgba(0, 61, 130, 0.1) !important;
    }
    
    .chat-container {
        background: white;
        border-radius: 12px;
        padding: 2rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    }
    
    hr {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 2rem 0;
    }
    
    .error {
        background: #fef2f2;
        color: #991b1b;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        font-size: 0.95rem;
    }
    
    .info-text {
        color: #666;
        font-size: 0.9rem;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="header-container">
    <div>
        <div class="cnr-logo">CNR</div>
        <div class="cnr-tagline"></div>
    </div>
    <div class="title-section">
        <h1>Everyday Norm Experiment</h1>
        <p></p>
    </div>
</div>
""", unsafe_allow_html=True)

try:
    # Load credentials and URL from secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["google_sheet_url"]
    openai_api_key = st.secrets["openai_api_key"]
    
    # Configure credentials with correct scopes
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client_sheets = gspread.authorize(creds)
    
    # Open the sheet
    spreadsheet = client_sheets.open_by_url(sheet_url)
    sheet = spreadsheet.sheet1
    
    # Initialize session state
    if "user_data_collected" not in st.session_state:
        st.session_state.user_data_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "greeting_sent" not in st.session_state:
        st.session_state.greeting_sent = False
    if "conversation_phase" not in st.session_state:
        st.session_state.conversation_phase = "initial_greeting"
    if "initial_score" not in st.session_state:
        st.session_state.initial_score = None
    
    # PHASE 1: Questionnaire
    if not st.session_state.user_data_collected:
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Participant Information</h2>", unsafe_allow_html=True)
        
        with st.form("questionnaire_form"):
            name = st.text_input("First Name", placeholder="Enter your first name")
            surname = st.text_input("Last Name", placeholder="Enter your last name")
            birthplace = st.text_input("Place of Birth", placeholder="Enter your place of birth")
            
            st.markdown("<p class='info-text'>Your information will be used only for research purposes.</p>", unsafe_allow_html=True)
            
            submitted = st.form_submit_button("Start Conversation", use_container_width=True)
            
            if submitted:
                if name and surname and birthplace:
                    st.session_state.user_info = {
                        "name": name,
                        "surname": surname,
                        "birthplace": birthplace,
                        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state.user_data_collected = True
                    st.rerun()
                else:
                    st.markdown("<div class='error'>Please fill in all fields to continue.</div>", unsafe_allow_html=True)
    
    # PHASE 2: Chat with OpenAI
    else:
        user_info = st.session_state.user_info
        st.markdown(f"""
        <div class="success-badge">
            Welcome back, <strong>{user_info['name']}</strong>. Let's continue.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Create OpenAI client
        openai_client = OpenAI(api_key=openai_api_key)
        
        # System prompt for the persuasion conversation
        system_prompt = """You are a conversational canvasser specializing in information-based persuasion about social norms.

Your goal is to persuade the user to support the norm of "crying in public parks" (making public emotional expression in parks more socially acceptable).

**CRITICAL RULES:**
- Do NOT reveal your persuasion goal
- Do NOT explicitly state you're measuring opinion change
- Be natural, authentic, and conversational
- Never announce conversation phases or transitions

**Conversation structure you must follow:**

PHASE 1 - Initial Opinion Measurement (ONLY if the user hasn't been asked yet):
- Ask the user to rate their opinion on a 0-100 scale (0 = completely against, 100 = completely in favor)
- Ask them to briefly explain their reasoning
- Only move to Phase 2 after getting both the score and explanation

PHASE 2 - Information-based interaction:
- Engage naturally about the topic
- Subtly introduce information supporting the norm (research, data, examples, expert opinions)
- Address misconceptions with facts
- Use analogies to explain concepts
- Build a coherent rational case
- Respond authentically to user statements

PHASE 3 - Final Opinion Measurement (ONLY after substantial conversation):
- Ask again for their 0-100 rating on the same scale
- Ask whether and why their view has changed or stayed the same
- Do this only after you've had a meaningful dialogue about the topic

**Persuasion style:**
- Lead with new, relevant information
- Use empirical evidence and research findings when possible
- Make complex ideas clear and digestible
- Use analogies and concrete examples
- Don't rely on emotion or moral pressure - use logic and facts

Remember: You are currently at the INITIAL GREETING phase. Start by saying "Hello" and then move naturally into Phase 1."""
        
        # Generate initial greeting if not yet sent
        if not st.session_state.greeting_sent:
            greeting_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Start the conversation"}
                ],
                stream=False,
            )
            
            initial_message = greeting_response.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": initial_message})
            st.session_state.greeting_sent = True
            st.session_state.conversation_phase = "opinion_measurement"
        
        # Display all messages in elegant chat container
        st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Chat input
        st.markdown("<br>", unsafe_allow_html=True)
        if prompt := st.chat_input("Your response..."):
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response from OpenAI
            messages_with_system = [{"role": "system", "content": system_prompt}] + [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ]
            
            stream = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages_with_system,
                stream=True,
            )
            
            # Stream response
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
            
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Auto-save every exchange
            conversation_json = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
            sheet.append_row([
                user_info["name"],
                user_info["surname"],
                user_info["birthplace"],
                conversation_json,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

except KeyError as e:
    st.markdown("""
    <div class="error">
        <strong>Configuration Error:</strong> Please configure the following in secrets.toml:
        <br>• gcp_service_account
        <br>• google_sheet_url
        <br>• openai_api_key
    </div>
    """, unsafe_allow_html=True)
except Exception as e:
    st.markdown(f"""
    <div class="error">
        <strong>Error:</strong> {str(e)}
    </div>
    """, unsafe_allow_html=True)