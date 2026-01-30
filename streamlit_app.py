import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI
import json
import os

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
    
    .timestamp {
        font-size: 0.8rem;
        color: #999;
        margin-top: 0.5rem;
    }
    
    [data-testid="stTextArea"] textarea {
        border: 1.5px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        font-size: 0.95rem !important;
        font-family: 'Segoe UI', Trebuchet MS, sans-serif;
    }
    
    [data-testid="stTextArea"] textarea:focus {
        border-color: #003d82 !important;
        box-shadow: 0 0 0 3px rgba(0, 61, 130, 0.1) !important;
    }
    
    .final-phase-container {
        display: flex;
        gap: 2rem;
        margin-top: 2rem;
    }
    
    .form-column {
        flex: 1;
        min-width: 300px;
    }
    
    .chat-column {
        flex: 1;
        min-width: 300px;
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        max-height: 600px;
        display: flex;
        flex-direction: column;
    }
    
    .chat-messages {
        flex: 1;
        overflow-y: auto;
        margin-bottom: 1rem;
    }
    
    @media (max-width: 1200px) {
        .final-phase-container {
            flex-direction: column;
        }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# CARICAMENTO PROMPTS DA FILE JSON ESTERNO
# ============================================================================
def load_prompts_from_file(file_path="prompts.json"):
    """
    Carica i prompt da un file JSON esterno.
    
    Args:
        file_path (str): Percorso del file JSON (default: "prompts.json")
    
    Returns:
        dict: Dizionario con i prompt caricati, oppure vuoto se errore
    """
    try:
        if not os.path.exists(file_path):
            st.error(f"❌ File prompts.json non trovato in {file_path}")
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        return prompts
    
    except json.JSONDecodeError as e:
        st.error(f"❌ Errore nel parsing del JSON: {str(e)}")
        return {}
    except Exception as e:
        st.error(f"❌ Errore nel caricamento del file: {str(e)}")
        return {}


PROMPTS = load_prompts_from_file("prompts.json")


# ============================================================================
# SALVATAGGIO CONVERSAZIONE IN JSON
# ============================================================================
def save_conversation_to_json(user_info, prompt_data, messages, filename=None):
    """
    Salva la conversazione in un file JSON.
    
    Args:
        user_info (dict): Informazioni dell'utente
        prompt_data (dict): Dati del prompt selezionato
        messages (list): Lista dei messaggi della conversazione
        filename (str): Nome del file (default: generato automaticamente)
    """
    try:
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{user_info['prolific_id']}_{timestamp}.json"
        
        conversation_data = {
            "metadata": {
                "prolific_id": user_info['prolific_id'],
                "prompt_title": prompt_data['title'],
                "prompt_description": prompt_data['description'],
                "start_date": user_info['start_date'],
                "end_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_messages": len(messages)
            },
            "messages": messages
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, ensure_ascii=False, indent=2)
        
        return filename
    
    except Exception as e:
        st.error(f"❌ Errore nel salvataggio della conversazione: {str(e)}")
        return None


# ============================================================================
# SALVATAGGIO SU GOOGLE SHEETS
# ============================================================================
def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, messages, argumentation):
    """
    Salva i dati su Google Sheets.
    
    Args:
        sheet: Sheet object di gspread
        user_info (dict): Informazioni dell'utente
        prompt_key (str): Chiave del prompt selezionato
        prompt_data (dict): Dati del prompt
        messages (list): Lista dei messaggi
        argumentation (str): Testo dell'argomentazione finale
    
    Returns:
        bool: True se il salvataggio è riuscito, False altrimenti
    """
    try:
        conversation_json = json.dumps(messages, ensure_ascii=False, indent=2)
        sheet.append_row([
            user_info["prolific_id"],
            prompt_key,
            prompt_data["title"],
            conversation_json,
            argumentation,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception as e:
        st.error(f"❌ Errore nel salvataggio su Google Sheets: {str(e)}")
        return False


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
    if "conversation_ended" not in st.session_state:
        st.session_state.conversation_ended = False
    if "final_argumentation" not in st.session_state:
        st.session_state.final_argumentation = None
    if "final_chat_messages" not in st.session_state:
        st.session_state.final_chat_messages = []
    if "final_chat_greeting_sent" not in st.session_state:
        st.session_state.final_chat_greeting_sent = False
    
    # Verifica se i prompt sono stati caricati
    if not PROMPTS:
        st.markdown("""
        <div class="error">
            <strong>Errore Critico:</strong> Impossibile caricare i prompt dal file JSON.
            Verifica che il file prompts.json sia presente nella directory dell'applicazione.
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    
    # PHASE 1: Personal Information Form
    if not st.session_state.user_data_collected:
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Participant Information</h2>", unsafe_allow_html=True)
        
        with st.form("questionnaire_form"):
            prolific_id = st.text_input("Prolific ID", placeholder="Enter your Prolific ID")
            
            st.markdown("<p class='info-text'>Your information will be used only for research purposes.</p>", unsafe_allow_html=True)
            
            submitted = st.form_submit_button("Continue to Prompt Selection", use_container_width=True)
            
            if submitted:
                if prolific_id:
                    st.session_state.user_info = {
                        "prolific_id": prolific_id,
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
            Welcome, <strong>{user_info['prolific_id']}</strong>! Please select a topic for our conversation.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Select a Conversation Topic</h2>", unsafe_allow_html=True)
        
        st.markdown("<p style='color: #666; margin-bottom: 2rem;'>Choose one of the following topics you'd like to explore:</p>", unsafe_allow_html=True)
        
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
    elif not st.session_state.conversation_ended:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Welcome back, <strong>{user_info['prolific_id']}</strong>. Topic: <strong>{prompt_data['title']}</strong>
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
            st.session_state.messages.append({
                "role": "assistant",
                "content": initial_message,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            st.session_state.greeting_sent = True
            st.session_state.conversation_phase = "opinion_measurement"
        
        # Display messages with timestamps
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
        
        # Chat input
        st.markdown("<br>", unsafe_allow_html=True)
        if prompt := st.chat_input("Your response..."):
            # Add user message with timestamp
            st.session_state.messages.append({
                "role": "user",
                "content": prompt,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            with st.chat_message("user"):
                st.markdown(prompt)
                st.markdown(f"<div class='timestamp'>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)
            
            # Generate response from OpenAI
            messages_for_api = [{"role": "system", "content": system_prompt}] + [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ]
            
            stream = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages_for_api,
                stream=True,
            )
            
            # Stream response
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
                        # Check if conversation should end (LLM responds with ABRACADABRA)
            if "ABRACADABRA" in response:
                st.session_state.conversation_ended = True
                st.rerun()
            
            response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f"<div class='timestamp'>{response_timestamp}</div>", unsafe_allow_html=True)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "timestamp": response_timestamp
            })
    
    # PHASE 4: Final Argumentation Form + Lateral Chat
    else:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Thank you for the conversation, <strong>{user_info['prolific_id']}</strong>!
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Final Question</h2>", unsafe_allow_html=True)
        
        st.markdown("""
        <p style='color: #666; margin-bottom: 1.5rem; font-size: 1rem;'>
            Please explain in detail why you believe it is <strong>not correct to drink during a job interview</strong>. 
            Share your reasoning and any relevant considerations.
        </p>
        """, unsafe_allow_html=True)
        
        # Create OpenAI client for final chat
        openai_client = OpenAI(api_key=openai_api_key)
        final_chat_system_prompt = "You are a helpful assistant. Answer questions about the topic discussed: why it's not correct to drink during a job interview. Be supportive and provide insights."
        
        # Create two columns: form on left, AI Assistant on right
        col_form, col_assistant = st.columns([2, 1])
        
        with col_form:
            st.markdown("### Your Response")
            with st.form("final_argumentation_form"):
                argumentation = st.text_area(
                    "Your argumentation:",
                    placeholder="Type your explanation here...",
                    height=300,
                    label_visibility="collapsed"
                )
                
                submitted = st.form_submit_button("Submit and Complete", use_container_width=True)
                
                if submitted:
                    if argumentation.strip():
                        st.session_state.final_argumentation = argumentation
                        
                        # Save conversation to JSON locally
                        save_conversation_to_json(user_info, prompt_data, st.session_state.messages)
                        
                        # Save to Google Sheets only now
                        success = save_to_google_sheets(
                            sheet,
                            user_info,
                            prompt_key,
                            prompt_data,
                            st.session_state.messages,
                            argumentation
                        )
                        
                        if success:
                            st.markdown("""
                            <div class="success-badge">
                                ✅ Thank you for your participation! Your responses have been recorded.
                            </div>
                            """, unsafe_allow_html=True)
                            
                            st.markdown("""
                            <p style='color: #666; margin-top: 2rem; font-size: 0.95rem;'>
                                Your data has been saved and will be used for research purposes only.
                            </p>
                            """, unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)
        
        with col_assistant:
            st.markdown("### AI Assistant")
            
            # Display chat messages
            chat_container = st.container(border=True, height=400)
            with chat_container:
                for message in st.session_state.final_chat_messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                        st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
            
            # Chat input
            if final_chat_prompt := st.chat_input("Ask something...", key="final_chat_input"):
                # Add user message
                st.session_state.final_chat_messages.append({
                    "role": "user",
                    "content": final_chat_prompt,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                # Generate response from OpenAI
                messages_for_api = [{"role": "system", "content": final_chat_system_prompt}] + [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.final_chat_messages
                ]
                
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages_for_api,
                    stream=False,
                )
                
                response_text = response.choices[0].message.content
                response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                st.session_state.final_chat_messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": response_timestamp
                })
                
                st.rerun()

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