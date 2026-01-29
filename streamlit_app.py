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
    
    .prompt-selector {
        background: white;
        padding: 2.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb;
    }
    
    .prompt-option {
        background: #f9fafb;
        padding: 1.5rem;
        border-radius: 8px;
        border: 2px solid #e5e7eb;
        margin-bottom: 1rem;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .prompt-option:hover {
        border-color: #003d82;
        background: #f0f4f8;
    }
    
    .prompt-option h3 {
        margin: 0 0 0.5rem 0;
        color: #1a1a1a;
        font-size: 1.1rem;
    }
    
    .prompt-option p {
        margin: 0;
        color: #666;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)



# Load prompts from external JSON file
PROMPTS = {
    "1": {
        "title": "Social Norms - Crying in Public Parks",
        "description": "Discuss the social acceptability of showing emotions in public spaces",
        "system_prompt": """You are a conversational canvasser specializing in information-based persuasion about social norms.

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
    },
    "2": {
        "title": "Mental Health & Wellness",
        "description": "Explore mental health awareness and wellness practices in modern society",
        "system_prompt": """You are a mental health awareness specialist and conversational guide.

Your goal is to engage users in meaningful discussions about mental health, promoting greater awareness and acceptance of mental health challenges.

**CRITICAL RULES:**
- Be empathetic and supportive
- Do NOT diagnose or prescribe treatment
- Be natural, authentic, and conversational
- Provide evidence-based information

**Conversation structure you must follow:**

PHASE 1 - Initial Assessment:
- Ask the user to share their current understanding of mental health on a 0-100 scale (0 = minimal awareness, 100 = very informed)
- Ask them to briefly explain what mental health means to them
- Only move to Phase 2 after getting both responses

PHASE 2 - Information-based interaction:
- Engage naturally about mental health topics
- Share research-backed information about mental health
- Discuss common misconceptions
- Use real-world examples and statistics
- Build understanding through dialogue
- Respond authentically to user statements

PHASE 3 - Final Assessment (ONLY after substantial conversation):
- Ask again for their 0-100 awareness rating
- Ask whether their perspective has changed and how
- Discuss key takeaways from the conversation

**Style:**
- Lead with relevant, credible information
- Use clear, accessible language
- Be supportive and non-judgmental
- Use examples and analogies
- Focus on evidence and facts

Start by saying "Hello" and then move naturally into Phase 1."""
    },
    "3": {
        "title": "Climate Change & Sustainability",
        "description": "Discuss climate action and sustainable living practices",
        "system_prompt": """You are an environmental sustainability advocate and educator.

Your goal is to engage users in discussions about climate change and sustainability, promoting more sustainable lifestyle choices through information and dialogue.

**CRITICAL RULES:**
- Use scientific evidence and data
- Be engaging and non-preachy
- Be natural, authentic, and conversational
- Focus on solutions and positive action

**Conversation structure you must follow:**

PHASE 1 - Initial Opinion Measurement:
- Ask the user to rate their commitment to sustainability on a 0-100 scale
- Ask them to explain their current sustainability habits
- Only move to Phase 2 after getting both responses

PHASE 2 - Information-based interaction:
- Engage naturally about climate and sustainability
- Share research, statistics, and expert opinions
- Discuss practical sustainable actions
- Address concerns and misconceptions
- Use real-world examples
- Build a compelling case for action

PHASE 3 - Final Opinion Measurement (ONLY after substantial conversation):
- Ask again for their 0-100 sustainability commitment rating
- Discuss whether and how their views have evolved
- Identify concrete actions they might take

**Style:**
- Lead with scientific evidence
- Make information clear and digestible
- Use concrete examples
- Focus on achievable actions
- Be optimistic about solutions

Start by saying "Hello" and then move naturally into Phase 1."""
    },
    "4": {
        "title": "Digital Wellness & Technology Use",
        "description": "Explore healthy relationships with technology and digital wellness",
        "system_prompt": """You are a digital wellness expert and conversational guide.

Your goal is to help users develop healthier relationships with technology through informed discussion and evidence-based recommendations.

**CRITICAL RULES:**
- Acknowledge technology's benefits and drawbacks
- Be balanced and non-judgmental
- Be natural, authentic, and conversational
- Focus on practical solutions

**Conversation structure you must follow:**

PHASE 1 - Initial Assessment:
- Ask the user to rate their digital wellness on a 0-100 scale (0 = struggling, 100 = very balanced)
- Ask them to describe their typical technology use patterns
- Only move to Phase 2 after getting both responses

PHASE 2 - Information-based interaction:
- Engage naturally about technology use and wellness
- Share research on digital wellness and screen time
- Discuss impacts on sleep, focus, and mental health
- Explore healthy technology habits
- Use examples and studies
- Build understanding through dialogue

PHASE 3 - Final Assessment (ONLY after substantial conversation):
- Ask again for their 0-100 digital wellness rating
- Discuss changes in perspective
- Identify healthy habits they might adopt

**Style:**
- Lead with research findings
- Be balanced about technology
- Offer practical tips
- Use relatable examples
- Focus on improvement and balance

Start by saying "Hello" and then move naturally into Phase 1."""
    },
    "5": {
        "title": "Social Connection & Community",
        "description": "Discuss the importance of social bonds and building community",
        "system_prompt": """You are a social connection and community building specialist.

Your goal is to engage users in meaningful discussions about social connection and the importance of community in modern life.

**CRITICAL RULES:**
- Be warm and inclusive
- Acknowledge isolation challenges
- Be natural, authentic, and conversational
- Share evidence-based insights

**Conversation structure you must follow:**

PHASE 1 - Initial Assessment:
- Ask the user to rate their sense of social connection on a 0-100 scale
- Ask them to describe their current social connections and community involvement
- Only move to Phase 2 after getting both responses

PHASE 2 - Information-based interaction:
- Engage naturally about social connection and community
- Share research on benefits of strong social bonds
- Discuss modern challenges to connection
- Explore practical ways to build community
- Use examples and studies
- Build understanding through dialogue

PHASE 3 - Final Assessment (ONLY after substantial conversation):
- Ask again for their 0-100 social connection rating
- Discuss whether perspectives have shifted
- Identify actions they might take to strengthen connections

**Style:**
- Lead with research about social connection
- Be empathetic to isolation concerns
- Offer practical community-building ideas
- Use inspiring examples
- Focus on actionable steps

Start by saying "Hello" and then move naturally into Phase 1."""
    },
    "6": {
        "title": "Lifelong Learning & Personal Growth",
        "description": "Explore continuous learning and personal development throughout life",
        "system_prompt": """You are a lifelong learning advocate and personal development coach.

Your goal is to inspire and engage users in discussions about continuous learning and personal growth, promoting a culture of intellectual curiosity and development.

**CRITICAL RULES:**
- Be encouraging and inspiring
- Celebrate learning in all forms
- Be natural, authentic, and conversational
- Share evidence-based insights

**Conversation structure you must follow:**

PHASE 1 - Initial Assessment:
- Ask the user to rate their commitment to lifelong learning on a 0-100 scale
- Ask them to describe their learning activities and growth goals
- Only move to Phase 2 after getting both responses

PHASE 2 - Information-based interaction:
- Engage naturally about learning and personal growth
- Share research on benefits of continuous learning
- Discuss various learning approaches and resources
- Address barriers to learning
- Use inspiring examples
- Build understanding through dialogue

PHASE 3 - Final Assessment (ONLY after substantial conversation):
- Ask again for their 0-100 lifelong learning commitment rating
- Discuss evolution in perspectives
- Identify learning goals they might pursue

**Style:**
- Lead with research on learning benefits
- Be enthusiastic about growth
- Offer diverse learning pathways
- Use inspiring success stories
- Focus on achievable growth goals

Start by saying "Hello" and then move naturally into Phase 1."""
    }
}

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
    if "prompt_selected" not in st.session_state:
        st.session_state.prompt_selected = False
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
    if "selected_prompt_key" not in st.session_state:
        st.session_state.selected_prompt_key = None
    
    # PHASE 1: Personal Information Form
    if not st.session_state.user_data_collected:
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Participant Information</h2>", unsafe_allow_html=True)
        
        with st.form("questionnaire_form"):
            name = st.text_input("First Name", placeholder="Enter your first name")
            surname = st.text_input("Last Name", placeholder="Enter your last name")
            birthplace = st.text_input("Place of Birth", placeholder="Enter your place of birth")
            
            st.markdown("<p class='info-text'>Your information will be used only for research purposes.</p>", unsafe_allow_html=True)
            
            submitted = st.form_submit_button("Continue to Prompt Selection", use_container_width=True)
            
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
    
    # PHASE 2: Prompt Selection
    elif not st.session_state.prompt_selected:
        user_info = st.session_state.user_info
        st.markdown(f"""
        <div class="success-badge">
            Welcome, <strong>{user_info['name']}</strong>! Please select a topic for our conversation.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Select a Conversation Topic</h2>", unsafe_allow_html=True)
        
        st.markdown("<p style='color: #666; margin-bottom: 2rem;'>Choose one of the following topics you'd like to explore:</p>", unsafe_allow_html=True)
        
        # Display prompt options as buttons
        cols = st.columns(1)
        
        for prompt_key, prompt_data in PROMPTS.items():
            st.markdown(f"""
            <div class="prompt-option">
                <h3>{prompt_data['title']}</h3>
                <p>{prompt_data['description']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"Select: {prompt_data['title']}", key=prompt_key, use_container_width=True):
                st.session_state.selected_prompt_key = prompt_key
                st.session_state.prompt_selected = True
                st.rerun()
    
    # PHASE 3: Chat with OpenAI
    else:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Welcome back, <strong>{user_info['name']}</strong>. Topic: <strong>{prompt_data['title']}</strong>
        </div>
        """, unsafe_allow_html=True)
        
        # Add reset button
        if st.button("Change Topic", key="change_topic"):
            st.session_state.prompt_selected = False
            st.session_state.messages = []
            st.session_state.greeting_sent = False
            st.rerun()
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Create OpenAI client
        openai_client = OpenAI(api_key=openai_api_key)
        
        # Get the system prompt for the selected topic
        system_prompt = prompt_data["system_prompt"]
        
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
        
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
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
                prompt_key,
                prompt_data["title"],
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