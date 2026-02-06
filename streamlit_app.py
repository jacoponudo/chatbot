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
    
    .opinion-container {
        background: white;
        padding: 2.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb;
        margin-bottom: 2rem;
    }
    
    .end-conversation-btn {
        background: #dc2626 !important;
        margin-top: 1rem;
    }
    
    @media (max-width: 1200px) {
        .final-phase-container {
            flex-direction: column;
        }
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# CARICAMENTO PROMPTS E NORMS DA FILE JSON ESTERNO
# ============================================================================
def load_json_from_file(file_path, item_name="items"):
    """
    Carica dati da un file JSON esterno.
    
    Args:
        file_path (str): Percorso del file JSON
        item_name (str): Nome degli item da caricare (per messaggi di errore)
    
    Returns:
        dict: Dizionario con i dati caricati, oppure vuoto se errore
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
    
    Args:
        sheet: Google Sheet object
        prolific_id (str): Prolific ID da verificare
    
    Returns:
        bool: True se il Prolific ID esiste già, False altrimenti
    """
    try:
        # Ottieni tutti i valori dalla prima colonna (Prolific ID)
        all_values = sheet.col_values(1)
        
        # Rimuovi l'intestazione (prima riga)
        if len(all_values) > 1:
            existing_ids = all_values[1:]
        else:
            existing_ids = []
        
        # Verifica se il Prolific ID esiste già (case-insensitive)
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
    
    Args:
        sheet: Google Sheet object
        prompts_dict (dict): Dizionario dei prompt disponibili
        norms_dict (dict): Dizionario delle norme disponibili
    
    Returns:
        tuple: (prompt_key, norm_key) della combinazione meno utilizzata
    """
    try:
        # Ottieni tutti i dati dal foglio (escludendo l'intestazione)
        all_data = sheet.get_all_values()
        
        # Inizializza il contatore delle combinazioni
        combination_counts = defaultdict(int)
        
        # Crea tutte le possibili combinazioni
        for prompt_key in prompts_dict.keys():
            for norm_key in norms_dict.keys():
                combination_counts[(prompt_key, norm_key)] = 0
        
        # Conta le combinazioni esistenti nel Google Sheet
        # Colonne: Prolific ID (0), Prompt (1), Norm (3)
        if len(all_data) > 1:  # Se ci sono dati oltre l'intestazione
            for row in all_data[1:]:  # Salta l'intestazione
                if len(row) >= 4:
                    prompt_key = row[1]  # Colonna Prompt
                    norm_key = row[3]    # Colonna Norm
                    
                    # Incrementa il contatore solo se la combinazione è valida
                    if prompt_key in prompts_dict and norm_key in norms_dict:
                        combination_counts[(prompt_key, norm_key)] += 1
        
        # Trova la combinazione con la frequenza minima
        min_count = min(combination_counts.values())
        least_used_combinations = [
            combo for combo, count in combination_counts.items() 
            if count == min_count
        ]
        
        # Se ci sono più combinazioni con la stessa frequenza minima, scegline una casualmente
        selected_combination = random.choice(least_used_combinations)
        
        st.info(f"📊 Combinazione selezionata automaticamente: Prompt='{selected_combination[0]}', Norm='{selected_combination[1]}' (usata {min_count} volte)")
        
        return selected_combination
    
    except Exception as e:
        st.error(f"❌ Errore nell'analisi delle frequenze: {str(e)}")
        # In caso di errore, ritorna la prima combinazione disponibile
        return (list(prompts_dict.keys())[0], list(norms_dict.keys())[0])


# ============================================================================
# SALVATAGGIO CONVERSAZIONE IN JSON
# ============================================================================
def save_conversation_to_json(user_info, prompt_data, norm_data, messages, filename=None):
    """
    Salva la conversazione in un file JSON.
    
    Args:
        user_info (dict): Informazioni dell'utente
        prompt_data (dict): Dati del prompt selezionato
        norm_data (dict): Dati della norma selezionata
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
                "norm_title": norm_data['title'],
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
def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, norm_key, norm_data, messages, 
                          initial_opinion=None, final_opinion=None, argumentation=None, 
                          word_tracking=None, final_chat_messages=None):
    """
    Salva i dati su Google Sheets.
    """
    try:
        conversation_json = json.dumps(messages, ensure_ascii=False, indent=2)
        final_chat_json = json.dumps(final_chat_messages or [], ensure_ascii=False, indent=2)
        
        # Formatta il word tracking in modo leggibile
        word_tracking_formatted = ""
        if word_tracking:
            sorted_tracking = sorted(word_tracking.items())
            word_tracking_formatted = json.dumps(
                {f"second_{i}": count for i, count in sorted_tracking},
                ensure_ascii=False,
                indent=2
            )
        
        sheet.append_row([
            user_info["prolific_id"],
            prompt_key,
            prompt_data["title"],
            norm_key,
            norm_data["title"],
            str(initial_opinion) if initial_opinion is not None else "",
            str(final_opinion) if final_opinion is not None else "",
            conversation_json,
            argumentation or "",
            word_tracking_formatted,
            final_chat_json,
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
    if "norm_selected" not in st.session_state:
        st.session_state.norm_selected = False
    if "initial_opinion_collected" not in st.session_state:
        st.session_state.initial_opinion_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "greeting_sent" not in st.session_state:
        st.session_state.greeting_sent = False
    if "conversation_phase" not in st.session_state:
        st.session_state.conversation_phase = "initial_greeting"
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
    if "final_argumentation" not in st.session_state:
        st.session_state.final_argumentation = None
    if "final_chat_messages" not in st.session_state:
        st.session_state.final_chat_messages = []
    if "final_chat_greeting_sent" not in st.session_state:
        st.session_state.final_chat_greeting_sent = False
    if "word_tracking" not in st.session_state:
        st.session_state.word_tracking = defaultdict(int)
    if "last_check_time" not in st.session_state:
        st.session_state.last_check_time = time.time()
    if "message_count" not in st.session_state:
        st.session_state.message_count = 0
    if "final_opinion_collected" not in st.session_state:
        st.session_state.final_opinion_collected = False
    
    # Verifica se i file sono stati caricati
    if not PROMPTS:
        st.markdown("""
        <div class="error">
            <strong>Errore Critico:</strong> Impossibile caricare i prompt dal file prompts.json.
            Verifica che il file sia presente nella directory dell'applicazione.
        </div>
        """, unsafe_allow_html=True)
        st.stop()
    
    if not NORMS:
        st.markdown("""
        <div class="error">
            <strong>Errore Critico:</strong> Impossibile caricare le norme dal file norms.json.
            Verifica che il file sia presente nella directory dell'applicazione.
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
                    # VERIFICA SE IL PROLIFIC ID ESISTE GIÀ
                    if check_prolific_id_exists(sheet, prolific_id):
                        st.markdown("""
                        <div class="warning">
                            ⚠️ <strong>This Prolific ID has already been used.</strong>
                            <br>If you believe this is an error, please contact the researcher.
                            <br>Otherwise, please use a different Prolific ID.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # Trova la combinazione Prompt-Norm meno utilizzata
                        selected_prompt_key, selected_norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
                        
                        # Salva le informazioni dell'utente e le assegnazioni
                        st.session_state.user_info = {
                            "prolific_id": prolific_id,
                            "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        st.session_state.selected_prompt_key = selected_prompt_key
                        st.session_state.selected_norm_key = selected_norm_key
                        st.session_state.user_data_collected = True
                        st.session_state.prompt_selected = True
                        st.session_state.norm_selected = True
                        st.rerun()
                else:
                    st.markdown("<div class='error'>Please fill in all fields to continue.</div>", unsafe_allow_html=True)
    
    # PHASE 2: Prompt and Norm Auto-Selected - Direct to Initial Opinion
    # (Le fasi di selezione manuale sono state rimosse, si passa direttamente alla raccolta dell'opinione iniziale)
    
    # PHASE 3: Initial Opinion Collection
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
            "Rate your agreement (1 = Strongly Disagree, 7 = Strongly Agree)",
            min_value=1,
            max_value=7,
            value=4,
            key="initial_opinion_slider"
        )
        
        if st.button("Continue to Conversation", key="submit_initial_opinion", use_container_width=True, type="primary"):
            st.session_state.initial_opinion = initial_opinion
            st.session_state.initial_opinion_collected = True
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # PHASE 4: Chat with OpenAI
    elif not st.session_state.conversation_ended:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        norm_key = st.session_state.selected_norm_key
        norm_data = NORMS[norm_key]

        st.markdown(f"""
        <div class="success-badge">
            Welcome back, <strong>{user_info['prolific_id']}</strong>. 
            <br>Topic: <strong>{prompt_data['title']}</strong> | Norm: <strong>{norm_data['title']}</strong>
            <br>Initial Opinion: <strong>{st.session_state.initial_opinion}/7</strong>
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
            st.session_state.conversation_phase = "opinion_measurement"
        
        # Display messages with timestamps
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
        
        # Conta i messaggi dell'utente (esclusi quelli dell'assistente)
        user_message_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
        
        # Mostra il pulsante per terminare la conversazione dopo 3 messaggi scambiati
        # (3 messaggi utente = 3 scambi completi considerando che l'assistente risponde sempre)
        if user_message_count >= 3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🛑 End Conversation and Proceed", key="end_conversation_btn", use_container_width=True):
                st.session_state.conversation_ended = True
                st.rerun()
        
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
            
            st.rerun()
    
    # PHASE 5: Final Opinion Collection
    elif not st.session_state.final_opinion_collected:
        user_info = st.session_state.user_info
        prompt_data = PROMPTS[st.session_state.selected_prompt_key]
        norm_data = NORMS[st.session_state.selected_norm_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Conversation completed! Now let's collect your final opinion.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div class='opinion-container'>", unsafe_allow_html=True)
        st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 1.5rem;'>Final Opinion</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #666; margin-bottom: 2rem;'>After the conversation, please indicate your current opinion on: <strong>{norm_data['title']}</strong></p>", unsafe_allow_html=True)
        
        final_opinion = st.slider(
            "Rate your agreement (1 = Strongly Disagree, 7 = Strongly Agree)",
            min_value=1,
            max_value=7,
            value=st.session_state.initial_opinion,  # Default al valore iniziale
            key="final_opinion_slider"
        )
        
        st.markdown(f"<p style='color: #999; font-size: 0.9rem; margin-top: 1rem;'>Your initial opinion was: <strong>{st.session_state.initial_opinion}/7</strong></p>", unsafe_allow_html=True)
        
        if st.button("Submit Final Opinion and Continue", key="submit_final_opinion", use_container_width=True, type="primary"):
            st.session_state.final_opinion = final_opinion
            st.session_state.final_opinion_collected = True
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # PHASE 6: Final Phase - Argumentation + Optional Chat
    else:
        user_info = st.session_state.user_info
        prompt_key = st.session_state.selected_prompt_key
        prompt_data = PROMPTS[prompt_key]
        norm_key = st.session_state.selected_norm_key
        norm_data = NORMS[norm_key]
        
        st.markdown(f"""
        <div class="success-badge">
            Final Phase: Write your argumentation
            <br>Initial Opinion: <strong>{st.session_state.initial_opinion}/7</strong> → Final Opinion: <strong>{st.session_state.final_opinion}/7</strong>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Due colonne: form e chat
        col_form, col_assistant = st.columns([1, 1])
        
        with col_form:
            st.markdown("<h3 style='margin-bottom: 1.5rem;'>Your Argumentation</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='color: #666; margin-bottom: 1rem;'>Write a brief argumentation about: <strong>{norm_data['title']}</strong></p>", unsafe_allow_html=True)
            
            argumentation = st.text_area(
                "Your argumentation:",
                height=300,
                placeholder="Write your thoughts here...",
                key="final_argumentation_area"
            )
            
            if st.button("📤 Submit and Complete", key="submit_final", use_container_width=True, type="primary"):
                if argumentation.strip():
                    st.session_state.final_argumentation = argumentation
                    
                    # Salva tutto
                    save_conversation_to_json(user_info, prompt_data, norm_data, st.session_state.messages)
                    success = save_to_google_sheets(
                        sheet,
                        user_info,
                        prompt_key,
                        prompt_data,
                        norm_key,
                        norm_data,
                        st.session_state.messages,
                        initial_opinion=st.session_state.initial_opinion,
                        final_opinion=st.session_state.final_opinion,
                        argumentation=argumentation,
                        word_tracking=dict(st.session_state.word_tracking),
                        final_chat_messages=st.session_state.final_chat_messages
                    )
                    
                    if success:
                        st.markdown("""
                            <div class="success-badge">
                                ✅ Thank you for your participation! Your responses have been recorded.
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)
        
        with col_assistant:
            st.markdown("### AI Assistant")
            st.markdown("<p style='color: #666; font-size: 0.9rem; margin-bottom: 1rem;'>Need help? Ask the assistant anything!</p>", unsafe_allow_html=True)
            
            # Create OpenAI client
            openai_client = OpenAI(api_key=openai_api_key)
            
            # System prompt per la chat finale
            final_chat_system_prompt = f"""You are a helpful assistant helping the user write their final argumentation about the norm: "{norm_data['title']}". 
            Provide helpful suggestions, ask clarifying questions, and help them organize their thoughts. 
            Be supportive and encouraging."""
            
            # Send initial greeting if not sent
            if not st.session_state.final_chat_greeting_sent:
                initial_greeting = "Hello! I'm here to help you write your argumentation. Feel free to ask me questions or request suggestions!"
                st.session_state.final_chat_messages.append({
                    "role": "assistant",
                    "content": initial_greeting,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                st.session_state.final_chat_greeting_sent = True
            
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