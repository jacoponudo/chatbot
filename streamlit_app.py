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
    
    button[kind="secondary"] {
        background: #ffffff !important;
        color: #4b5563 !important;
        border: 1px solid #d1d5db !important;
        padding: 0.6rem 1.25rem !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        transition: all 0.2s ease;
    }
    
    button[kind="secondary"]:hover {
        background: #f9fafb !important;
        border-color: #9ca3af !important;
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
    
    .warning {
        background: #fffbeb;
        color: #92400e;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #f59e0b;
        font-size: 0.95rem;
    }
    
    .info-text {
        color: #666;
        font-size: 0.9rem;
        margin-top: 1rem;
    }
    
    .opinion-container {
        background: white;
        padding: 2.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }
    
    .timestamp {
        font-size: 0.8rem;
        color: #999;
        margin-top: 0.5rem;
    }
    
    .message-counter {
        background: #f3f4f6;
        color: #6b7280;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        font-size: 0.85rem;
        text-align: center;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# CARICAMENTO PROMPTS E NORMS DA FILE JSON ESTERNO
# ============================================================================
def load_json_from_file(file_path, item_name="items"):
    """
    Carica dati da un file JSON esterno.
    """
    try:
        if not os.path.exists(file_path):
            st.error(f"❌ File {file_path} non trovato")
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    
    except json.JSONDecodeError as e:
        st.error(f"❌ Errore nel parsing del JSON {file_path}: {str(e)}")
        return {}
    except Exception as e:
        st.error(f"❌ Errore nel caricamento del file {file_path}: {str(e)}")
        return {}


PROMPTS = load_json_from_file("prompts.json", "prompts")
NORMS = load_json_from_file("norms.json", "norms")


# ============================================================================
# VERIFICA PROLIFIC ID
# ============================================================================
def check_prolific_id_exists(sheet, prolific_id):
    """
    Verifica se un Prolific ID esiste già nel Google Sheet.
    """
    try:
        all_values = sheet.col_values(1)
        
        if len(all_values) > 1:
            existing_ids = all_values[1:]
        else:
            existing_ids = []
        
        return prolific_id.strip().lower() in [id.strip().lower() for id in existing_ids]
    
    except Exception as e:
        st.error(f"❌ Errore nella verifica del Prolific ID: {str(e)}")
        return False


# ============================================================================
# ANALISI FREQUENZE COMBINAZIONI PROMPT-NORM
# ============================================================================
def get_least_used_combination(sheet, prompts_dict, norms_dict):
    """
    Analizza il Google Sheet e trova la combinazione Prompt-Norm meno utilizzata.
    """
    try:
        all_data = sheet.get_all_values()
        
        combination_counts = defaultdict(int)
        
        # Crea tutte le possibili combinazioni
        for prompt_key in prompts_dict.keys():
            for norm_key in norms_dict.keys():
                combination_counts[(prompt_key, norm_key)] = 0
        
        # Conta le combinazioni esistenti nel Google Sheet
        if len(all_data) > 1:
            for row in all_data[1:]:
                if len(row) >= 3:
                    prompt_key = row[1]
                    norm_key = row[2]
                    
                    if prompt_key in prompts_dict and norm_key in norms_dict:
                        combination_counts[(prompt_key, norm_key)] += 1
        
        # Trova la combinazione con la frequenza minima
        min_count = min(combination_counts.values())
        least_used_combinations = [
            combo for combo, count in combination_counts.items() 
            if count == min_count
        ]
        
        selected_combination = random.choice(least_used_combinations)
        
        return selected_combination
    
    except Exception as e:
        st.error(f"❌ Errore nell'analisi delle frequenze: {str(e)}")
        return (list(prompts_dict.keys())[0], list(norms_dict.keys())[0])


# ============================================================================
# SALVATAGGIO SU GOOGLE SHEETS - VERSIONE CORRETTA
# ============================================================================
def save_to_google_sheets(sheet, user_info, prompt_key, norm_key, messages, 
                          initial_opinion=None, final_opinion=None):
    """
    Salva i dati su Google Sheets.
    CORREZIONE: Gestisce correttamente i valori None e converte tutto in stringe.
    """
    try:
        # Converti la conversazione in JSON
        conversation_json = json.dumps(messages, ensure_ascii=False, indent=2)
        
        # Prepara i dati assicurandosi che siano tutti stringhe
        row_data = [
            str(user_info.get("prolific_id", "")),
            str(prompt_key),
            str(norm_key),
            str(initial_opinion) if initial_opinion is not None else "",
            conversation_json,
            str(final_opinion) if final_opinion is not None else "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        
        # Debug: mostra i dati che stai per salvare
        st.write("DEBUG - Dati da salvare:", row_data)
        
        # Append row with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sheet.append_row(row_data, value_input_option='RAW')
                st.success("✅ Dati salvati con successo!")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    st.warning(f"Tentativo {attempt + 1} fallito, riprovo...")
                    time.sleep(2)
                else:
                    raise e
        
        return False
        
    except Exception as e:
        st.error(f"❌ Errore nel salvataggio su Google Sheets: {str(e)}")
        st.error(f"Tipo di errore: {type(e).__name__}")
        import traceback
        st.error(f"Traceback completo:\n{traceback.format_exc()}")
        return False


# ============================================================================
# MAIN APP
# ============================================================================

try:
    # Load credentials and URL from secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["google_sheet_url"]
    openai_api_key = st.secrets["openai_api_key"]
    
    # Configure credentials with correct scopes
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client_sheets = gspread.authorize(creds)
    
    # Open the sheet
    spreadsheet = client_sheets.open_by_url(sheet_url)
    sheet = spreadsheet.sheet1
    
    # VERIFICA: Controlla se il foglio è accessibile
    try:
        headers = sheet.row_values(1)
        st.sidebar.success(f"✅ Connesso a Google Sheets")
        st.sidebar.info(f"Headers: {headers}")
    except Exception as e:
        st.sidebar.error(f"❌ Errore accesso sheet: {e}")
    
    # Initialize session state
    if "user_data_collected" not in st.session_state:
        st.session_state.user_data_collected = False
    if "initial_opinion_collected" not in st.session_state:
        st.session_state.initial_opinion_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "greeting_sent" not in st.session_state:
        st.session_state.greeting_sent = False
    if "initial_opinion" not in st.session_state:
        st.session_state.initial_opinion = None
    if "final_opinion" not in st.session_state:
        st.session_state.final_opinion = None
    if "selected_prompt_key" not in st.session_state:
        st.session_state.selected_prompt_key = None
    if "selected_norm_key" not in st.session_state:
        st.session_state.selected_norm_key = None
    if "conversation_ended" not in st.session_state:
        st.session_state.conversation_ended = False
    if "final_opinion_collected" not in st.session_state:
        st.session_state.final_opinion_collected = False
    if "data_saved" not in st.session_state:
        st.session_state.data_saved = False
    
    # Verifica se i file sono stati caricati
    if not PROMPTS:
        st.markdown("""
        <div class="error">
            <strong>Errore Critico:</strong> Impossibile caricare i prompt dal file prompts.json.
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    
    if not NORMS:
        st.markdown("""
        <div class="error">
            <strong>Errore Critico:</strong> Impossibile caricare le norme dal file norms.json.
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    
    # PHASE 1: Personal Information Form
    if not st.session_state.user_data_collected:
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Participant Information</h2>", unsafe_allow_html=True)
        
        with st.form("questionnaire_form"):
            prolific_id = st.text_input("Prolific ID", placeholder="Enter your Prolific ID")
            
            st.markdown("<p class='info-text'>Your information will be used only for research purposes.</p>", unsafe_allow_html=True)
            st.markdown("<p class='info-text'>A topic and norm will be automatically assigned to you based on experimental balance.</p>", unsafe_allow_html=True)
            
            submitted = st.form_submit_button("Continue", use_container_width=True)
            
            if submitted:
                if prolific_id:
                    if check_prolific_id_exists(sheet, prolific_id):
                        st.markdown("""
                        <div class="warning">
                            ⚠️ <strong>This Prolific ID has already been used.</strong>
                            <br>If you believe this is an error, please contact the researcher.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        selected_prompt_key, selected_norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
                        
                        st.session_state.user_info = {
                            "prolific_id": prolific_id,
                            "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.selected_prompt_key = selected_prompt_key
                        st.session_state.selected_norm_key = selected_norm_key
                        st.session_state.user_data_collected = True
                        st.rerun()
                else:
                    st.markdown("<div class='error'>Please fill in all fields to continue.</div>", unsafe_allow_html=True)
    
    # PHASE 2: Initial Opinion Collection
    elif not st.session_state.initial_opinion_collected:
        user_info = st.session_state.user_info
        prompt_data = PROMPTS[st.session_state.selected_prompt_key]
        norm_data = NORMS[st.session_state.selected_norm_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Topic: <strong>{prompt_data['title']}</strong> | Norm: <strong>{norm_data['title']}</strong>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div class='opinion-container'>", unsafe_allow_html=True)
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 1.5rem;'>Initial Opinion</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #666; margin-bottom: 2rem;'>Before starting the conversation, please indicate your current opinion on: <strong>{norm_data['title']}</strong></p>", unsafe_allow_html=True)
        
        initial_opinion = st.slider(
            "Rate your agreement (1 = Strongly Disagree, 100 = Strongly Agree)",
            min_value=1,
            max_value=100,
            value=50,
            key="initial_opinion_slider"
        )
        
        if st.button("Continue to Conversation", key="submit_initial_opinion", use_container_width=True, type="primary"):
            st.session_state.initial_opinion = initial_opinion
            st.session_state.initial_opinion_collected = True
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # PHASE 3: Chat with OpenAI
    elif not st.session_state.conversation_ended:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        norm_key = st.session_state.selected_norm_key
        norm_data = NORMS[norm_key]

        st.markdown(f"""
        <div class="success-badge">
            Topic: <strong>{prompt_data['title']}</strong> | Norm: <strong>{norm_data['title']}</strong>
            <br>Initial Opinion: <strong>{st.session_state.initial_opinion}/100</strong>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Create OpenAI client
        openai_client = OpenAI(api_key=openai_api_key)
        
        # Get the system prompt template and inject the selected norm
        system_prompt_template = prompt_data.get("system_prompt_template", prompt_data.get("system_prompt", ""))
        system_prompt = system_prompt_template.replace("{NORM_DESCRIPTION}", norm_data["title"])
        
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
        
        # Display messages with timestamps
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
        
        # Conta i messaggi dell'utente
        user_message_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
        
        # Check if user has reached 10 messages - automatically end conversation
        if user_message_count >= 10:
            st.session_state.conversation_ended = True
            st.rerun()
        
        # Show end button after 3 messages
        if user_message_count >= 3:
            if st.button("End Conversation", key="end_conversation_btn", use_container_width=True, type="secondary"):
                st.session_state.conversation_ended = True
                st.rerun()
        
        # Chat input - only show if conversation hasn't ended
        st.markdown("<br>", unsafe_allow_html=True)
        if prompt := st.chat_input("Your response..."):
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
            
            response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f"<div class='timestamp'>{response_timestamp}</div>", unsafe_allow_html=True)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "timestamp": response_timestamp
            })
            
            st.rerun()
    
    # PHASE 4: Final Opinion Collection and Save
    elif not st.session_state.data_saved:
        user_info = st.session_state.user_info
        prompt_data = PROMPTS[st.session_state.selected_prompt_key]
        norm_data = NORMS[st.session_state.selected_norm_key]
        
        st.markdown("<div class='opinion-container'>", unsafe_allow_html=True)
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 1.5rem;'>Final Opinion</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #666; margin-bottom: 2rem;'>After the conversation, please indicate your current opinion on: <strong>{norm_data['title']}</strong></p>", unsafe_allow_html=True)
        
        final_opinion = st.slider(
            "Rate your agreement (1 = Strongly Disagree, 100 = Strongly Agree)",
            min_value=1,
            max_value=100,
            value=st.session_state.initial_opinion,
            key="final_opinion_slider"
        )
        
        st.markdown(f"<p style='color: #999; font-size: 0.9rem; margin-top: 1rem;'>Your initial opinion was: <strong>{st.session_state.initial_opinion}/100</strong></p>", unsafe_allow_html=True)
        
        if st.button("Submit and Complete", key="submit_final_opinion", use_container_width=True, type="primary"):
            st.session_state.final_opinion = final_opinion
            
            # Mostra un messaggio di caricamento
            with st.spinner("Saving your data..."):
                # Salva su Google Sheets
                success = save_to_google_sheets(
                    sheet,
                    user_info,
                    st.session_state.selected_prompt_key,
                    st.session_state.selected_norm_key,
                    st.session_state.messages,
                    initial_opinion=st.session_state.initial_opinion,
                    final_opinion=final_opinion
                )
                
                if success:
                    st.session_state.data_saved = True
                    time.sleep(1)  # Piccola pausa per mostrare il messaggio di successo
                    st.rerun()
                else:
                    st.error("❌ Errore nel salvataggio. Riprova o contatta il ricercatore.")
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # PHASE 5: Thank You
    else:
        st.markdown("""
        <div class="success-badge">
            ✅ Thank you for your participation! Your responses have been recorded.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div style="margin-top: 2rem; padding: 1.5rem; background: white; border-radius: 8px;">
            <h3>Summary of your session:</h3>
            <ul>
                <li>Prolific ID: {st.session_state.user_info.get('prolific_id', 'N/A')}</li>
                <li>Topic: {PROMPTS[st.session_state.selected_prompt_key]['title']}</li>
                <li>Norm: {NORMS[st.session_state.selected_norm_key]['title']}</li>
                <li>Initial Opinion: {st.session_state.initial_opinion}/100</li>
                <li>Final Opinion: {st.session_state.final_opinion}/100</li>
                <li>Messages exchanged: {len(st.session_state.messages)}</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

except KeyError as e:
    st.markdown(f"""
    <div class="error">
        <strong>Configuration Error:</strong> Missing key in secrets: {str(e)}
        <br>Please configure secrets.toml with all required fields.
    </div>
    """, unsafe_allow_html=True)
except Exception as e:
    st.markdown(f"""
    <div class="error">
        <strong>Error:</strong> {str(e)}
    </div>
    """, unsafe_allow_html=True)
    import traceback
    st.code(traceback.format_exc())