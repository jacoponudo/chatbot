import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
from openai import OpenAI
import time
from collections import defaultdict

# Page configuration
st.set_page_config(
    page_title="Test Phase 4 - Final Argumentation",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
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
</style>
""", unsafe_allow_html=True)

# ============================================================================
# FUNZIONI DI SALVATAGGIO
# ============================================================================

def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, messages, argumentation, word_tracking=None, final_chat_messages=None):
    """
    Salva i dati su Google Sheets.
    """
    try:
        conversation_json = json.dumps(messages, ensure_ascii=False, indent=2)
        final_chat_json = json.dumps(final_chat_messages or [], ensure_ascii=False, indent=2)
        
        # Formatta il word tracking in modo leggibile
        word_tracking_formatted = ""
        if word_tracking:
            # Ordina per timestamp per una sequenza cronologica
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
            conversation_json,
            argumentation,
            word_tracking_formatted,
            final_chat_json,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception as e:
        st.error(f"❌ Errore nel salvataggio su Google Sheets: {str(e)}")
        return False


def save_conversation_to_json(user_info, prompt_data, messages, filename=None):
    """
    Salva la conversazione in un file JSON.
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
# CONFIGURAZIONE GOOGLE SHEETS
# ============================================================================

def init_google_sheets():
    """Inizializza la connessione a Google Sheets"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        sheet_url = st.secrets["google_sheet_url"]
        
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client_sheets = gspread.authorize(creds)
        
        spreadsheet = client_sheets.open_by_url(sheet_url)
        sheet = spreadsheet.sheet1
        
        return sheet, True
    except KeyError:
        return None, False
    except Exception as e:
        st.error(f"❌ Errore di connessione: {str(e)}")
        return None, False


# Initialize session state
if "final_argumentation" not in st.session_state:
    st.session_state.final_argumentation = None
if "final_chat_messages" not in st.session_state:
    st.session_state.final_chat_messages = []
if "word_tracking" not in st.session_state:
    st.session_state.word_tracking = {}  # Dict con timestamp come chiave
if "last_tracked_second" not in st.session_state:
    st.session_state.last_tracked_second = None
if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "prolific_id": "TEST_USER_001",
        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
if "sheet_connected" not in st.session_state:
    st.session_state.sheet_connected = False

# Tentare la connessione a Google Sheets
sheet, is_connected = init_google_sheets()
st.session_state.sheet_connected = is_connected

# Sidebar per settings
with st.sidebar:
    st.header("⚙️ Test Settings")
    
    st.markdown("### 🔗 Database Connection")
    if st.session_state.sheet_connected:
        st.markdown("<div class='success-badge'>✅ Connected to Google Sheets</div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='warning'>
            ⚠️ Not connected to Google Sheets<br>
            Make sure secrets.toml is configured
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    use_mock_api = st.checkbox(
        "Use Mock API Response",
        value=True,
        help="If unchecked, requires valid OpenAI API key"
    )
    
    api_key = None
    if not use_mock_api:
        api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        if not api_key:
            st.warning("⚠️ API key required to use real OpenAI API")
    
    st.markdown("---")
    
    # Edit user info
    st.markdown("### 👤 User Info")
    prolific_id = st.text_input(
        "Prolific ID",
        value=st.session_state.user_info["prolific_id"]
    )
    st.session_state.user_info["prolific_id"] = prolific_id
    
    st.markdown("---")
    st.markdown("### 📊 Current State")
    st.json({
        "Prolific ID": st.session_state.user_info["prolific_id"],
        "Final Argumentation Words": len(st.session_state.final_argumentation.split()) if st.session_state.final_argumentation else 0,
        "Chat Messages Count": len(st.session_state.final_chat_messages),
        "Word Tracking Seconds": len(st.session_state.word_tracking)
    })

# Main content
st.markdown(f"""
<div class="success-badge">
    Testing Phase 4 - Word Tracking con Granularità al Secondo
</div>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Final Question</h2>", unsafe_allow_html=True)

st.markdown("""
<p style='color: #666; margin-bottom: 1.5rem; font-size: 1rem;'>
    Please explain in detail why you believe it is <strong>not correct to drink during a job interview</strong>. 
    Share your reasoning and any relevant considerations.
</p>
""", unsafe_allow_html=True)

# Create two columns: form on left, AI Assistant on right
col_form, col_assistant = st.columns([2, 1])

# PLACEHOLDER per il tracciamento ogni secondo
placeholder_tracking = st.empty()

def track_words_every_second():
    """
    Traccia il numero di parole OGNI SECONDO.
    Ogni secondo che passa, registra quante parole sono presenti nel text area.
    """
    current_time = time.time()
    current_second = int(current_time)  # Timestamp arrotondato al secondo
    
    # Leggi il testo attuale
    current_text = st.session_state.get("argumentation_input", "")
    current_word_count = len(current_text.split()) if current_text.strip() else 0
    
    # Se non abbiamo ancora tracciato questo secondo, registralo
    if current_second not in st.session_state.word_tracking:
        st.session_state.word_tracking[current_second] = current_word_count
        
        # Debug: mostra nel terminale
        print(f"⏱️ [{datetime.fromtimestamp(current_second).strftime('%H:%M:%S')}] Parole registrate al secondo {current_second}: {current_word_count}")
    else:
        # Aggiorna il conteggio per questo secondo (nel caso in cui sia stato riaperto)
        st.session_state.word_tracking[current_second] = current_word_count
    
    # Mostra il tracking corrente
    sorted_tracking = sorted(st.session_state.word_tracking.items())
    tracking_display = {f"second_{int(ts)}": count for ts, count in sorted_tracking}
    
    with placeholder_tracking:
        st.markdown(f"""
        <div style='background: #f0f4f8; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;'>
            <strong>📊 Real-time Word Tracking (per second):</strong><br>
            <code>{json.dumps(tracking_display, indent=2)}</code>
        </div>
        """, unsafe_allow_html=True)

with col_form:
    st.markdown("### Your Response")
    
    # Text area for argumentation
    argumentation = st.text_area(
        "Your argumentation:",
        placeholder="Type your explanation here...",
        height=300,
        label_visibility="collapsed",
        key="argumentation_input",
        on_change=track_words_every_second
    )
    
    # Aggiorna il tracking ogni volta che l'utente digita
    track_words_every_second()
    
    # Form only for submit button
    with st.form("final_argumentation_form"):
        submitted = st.form_submit_button("Submit and Save to Database", use_container_width=True)

    if submitted:
        if argumentation.strip():
            st.session_state.final_argumentation = argumentation
            
            # Tracciamento finale al momento del submit
            track_words_every_second()
            
            st.markdown(f"""
            <div class="success-badge">
                ✅ Argumentation saved! ({len(argumentation.split())} words)
            </div>
            """, unsafe_allow_html=True)
            
            # Print tracking to console
            print("\n" + "="*60)
            print("📊 FINAL WORD TRACKING BY SECOND:")
            print("="*60)
            for second, word_count in sorted(st.session_state.word_tracking.items()):
                readable_time = datetime.fromtimestamp(second).strftime("%H:%M:%S")
                print(f"  [{readable_time}] Second {second}: {word_count} words")
            print("="*60 + "\n")
            
            # Try to save to database
            if st.session_state.sheet_connected:
                # Mock data for testing
                mock_prompt_data = {
                    "title": "Why not drink during job interview",
                    "description": "A discussion about professional conduct"
                }
                mock_messages = [
                    {"role": "assistant", "content": "Why do you think it's inappropriate to drink during a job interview?"},
                    {"role": "user", "content": "It's unprofessional."}
                ]
                
                success = save_to_google_sheets(
                    sheet,
                    st.session_state.user_info,
                    "norm_test",
                    mock_prompt_data,
                    mock_messages,
                    argumentation,
                    word_tracking=st.session_state.word_tracking,
                    final_chat_messages=st.session_state.final_chat_messages
                )
                
                if success:
                    st.markdown("""
                        <div class="success-badge">
                            ✅ Data saved to Google Sheets successfully!
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Also save locally
                    filename = save_conversation_to_json(
                        st.session_state.user_info,
                        mock_prompt_data,
                        mock_messages
                    )
                    if filename:
                        st.info(f"📁 Local copy saved: {filename}")
                else:
                    st.markdown("<div class='error'>❌ Failed to save to Google Sheets</div>", unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class='warning'>
                        ⚠️ Google Sheets not connected. Data NOT saved to database.
                        <br>Please configure secrets.toml to enable database saving.
                    </div>
                """, unsafe_allow_html=True)
            
            # Display summary
            st.markdown("### 📋 Response Summary")
            st.write(f"**Word count:** {len(argumentation.split())} words")
            st.write(f"**Character count:** {len(argumentation)} characters")
            st.write(f"**Seconds tracked:** {len(st.session_state.word_tracking)} seconds")
            
            # Show detailed word tracking
            with st.expander("📊 Detailed Word Tracking by Second"):
                tracking_data = {}
                for ts, count in sorted(st.session_state.word_tracking.items()):
                    readable_time = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    tracking_data[f"{readable_time} (ts:{ts})"] = count
                st.json(tracking_data)
        else:
            st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)

with col_assistant:
    st.markdown("### AI Assistant")
    
    # Display chat messages
    chat_container = st.container(border=True, height=400)
    with chat_container:
        if not st.session_state.final_chat_messages:
            st.markdown("<p style='color: #999; text-align: center;'>No messages yet. Start a conversation!</p>", unsafe_allow_html=True)
        else:
            for message in st.session_state.final_chat_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
    
    # Chat input
    if final_chat_prompt := st.chat_input("Ask something...", key="final_chat_input"):
        # Add user message
        st.session_state.final_chat_messages.append({
            "role": "user",
            "content": final_chat_prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Generate response
        try:
            if use_mock_api:
                # Mock response for testing
                response_text = f"""This is a mock response to your question: "{final_chat_prompt[:50]}..."
                
In a real scenario, the AI would provide a thoughtful response about why drinking during a job interview is inappropriate."""
                response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Real OpenAI API
                if not api_key:
                    st.error("❌ API key required for real responses")
                    response_text = "Error: API key not provided"
                    response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    openai_client = OpenAI(api_key=api_key)
                    final_chat_system_prompt = "You are a helpful assistant. Answer questions about the topic discussed: why it's not correct to drink during a job interview. Be supportive and provide insights."
                    
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
        
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

# Footer with data export
st.markdown("---")
st.markdown("## 📥 Export & Reset")

col1, col2 = st.columns(2)

with col1:
    if st.button("📋 Export Session Data", use_container_width=True):
        session_data = {
            "user_info": st.session_state.user_info,
            "final_argumentation": st.session_state.final_argumentation,
            "word_tracking": st.session_state.word_tracking,
            "word_tracking_readable": {
                datetime.fromtimestamp(ts).strftime("%H:%M:%S"): count 
                for ts, count in sorted(st.session_state.word_tracking.items())
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        st.json(session_data)
        
        # Download as JSON
        json_str = json.dumps(session_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="Download as JSON",
            data=json_str,
            file_name=f"phase4_test_{st.session_state.user_info['prolific_id']}.json",
            mime="application/json"
        )

with col2:
    if st.button("🔄 Reset All Data", use_container_width=True):
        st.session_state.final_argumentation = None
        st.session_state.final_chat_messages = []
        st.session_state.word_tracking = {}
        st.success("✅ All data reset!")
        st.rerun()

# Display current session state at the bottom
with st.expander("🔍 Full Session State (Debug Info)"):
    debug_data = {
        "user_info": st.session_state.user_info,
        "final_argumentation_length": len(st.session_state.final_argumentation) if st.session_state.final_argumentation else 0,
        "word_tracking_entries": len(st.session_state.word_tracking),
        "word_tracking_data": st.session_state.word_tracking,
        "sheet_connected": st.session_state.sheet_connected
    }
    st.json(debug_data)