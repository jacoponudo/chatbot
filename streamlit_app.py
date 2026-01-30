import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
from openai import OpenAI
import time
import threading

# Page configuration
st.set_page_config(
    page_title="Everyday Norm Experiment - Phase 4",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
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
    
    .debug-box {
        background: #f0f4f8;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #3b82f6;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        max-height: 300px;
        overflow-y: auto;
        margin: 1rem 0;
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
    
    .error {
        background: #fef2f2;
        color: #991b1b;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

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
        print(f"❌ Errore di connessione: {str(e)}")
        return None, False


def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, argumentation, content_tracking, final_chat_messages):
    """
    Salva i dati su Google Sheets alla fine della sessione.
    """
    try:
        final_chat_json = json.dumps(final_chat_messages or [], ensure_ascii=False, indent=2)
        
        # Formatta il content tracking - converti timestamp a string
        content_tracking_formatted = json.dumps(
            {str(k): v for k, v in content_tracking.items()},
            ensure_ascii=False,
            indent=2
        )
        
        sheet.append_row([
            user_info["prolific_id"],
            prompt_key,
            prompt_data["title"],
            argumentation,
            content_tracking_formatted,
            final_chat_json,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception as e:
        print(f"❌ Errore nel salvataggio: {str(e)}")
        return False


# ============================================================================
# THREAD TRACKER - Traccia il contenuto completo ogni secondo
# ============================================================================

class ContentTracker(threading.Thread):
    def __init__(self, session_state):
        super().__init__(daemon=True)
        self.session_state = session_state
        self.is_running = False
        self.last_saved_second = None
        self.updates_count = 0
    
    def run(self):
        """Loop in background che traccia il contenuto completo ogni secondo"""
        self.is_running = True
        print("✅ ContentTracker thread started")
        
        while self.is_running:
            try:
                current_time = time.time()
                current_second = int(current_time)
                
                # Se è un nuovo secondo, traccia il contenuto completo
                if current_second != self.last_saved_second:
                    content = self.session_state.get("argumentation_input", "")
                    
                    # Salva il contenuto COMPLETO per questo secondo
                    self.session_state.content_tracking[current_second] = content
                    self.updates_count += 1
                    
                    # Log
                    readable_time = datetime.fromtimestamp(current_second).strftime("%H:%M:%S")
                    word_count = len(content.split()) if content.strip() else 0
                    print(f"💾 [{readable_time}] Update #{self.updates_count}: {word_count} words")
                    
                    self.last_saved_second = current_second
                
                time.sleep(0.05)
            
            except Exception as e:
                print(f"❌ Tracker error: {str(e)}")
                time.sleep(1)
    
    def stop(self):
        """Ferma il tracker"""
        self.is_running = False
        print(f"⏹️ ContentTracker stopped after {self.updates_count} updates")


# Initialize session state
if "final_argumentation" not in st.session_state:
    st.session_state.final_argumentation = None
if "final_chat_messages" not in st.session_state:
    st.session_state.final_chat_messages = []
if "content_tracking" not in st.session_state:
    st.session_state.content_tracking = {}
if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "prolific_id": "TEST_USER_001",
        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
if "sheet_connected" not in st.session_state:
    st.session_state.sheet_connected = False
if "tracker" not in st.session_state:
    st.session_state.tracker = None
if "selected_prompt_key" not in st.session_state:
    st.session_state.selected_prompt_key = "norm_test"

# Tentare la connessione a Google Sheets
sheet, is_connected = init_google_sheets()
st.session_state.sheet_connected = is_connected

# Avvia tracker in background se non è già avviato
if st.session_state.tracker is None:
    st.session_state.tracker = ContentTracker(st.session_state)
    st.session_state.tracker.start()

# ============================================================================
# SIDEBAR - DEBUG INFO
# ============================================================================

with st.sidebar:
    st.header("🔍 DEBUG INFO")
    
    st.markdown("### 📊 Tracking Status")
    if st.session_state.tracker and st.session_state.tracker.is_running:
        st.success("✅ Tracker RUNNING")
    else:
        st.error("❌ Tracker STOPPED")
    
    st.metric("Seconds Tracked", len(st.session_state.content_tracking))
    st.metric("Database Connected", "✅ Yes" if st.session_state.sheet_connected else "❌ No")
    
    st.markdown("### 📋 Current Tracking")
    if st.session_state.content_tracking:
        # Mostra gli ultimi 5 update
        recent = dict(sorted(st.session_state.content_tracking.items())[-5:])
        st.write("**Last 5 updates:**")
        for ts, content in recent.items():
            readable_time = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            word_count = len(content.split()) if content.strip() else 0
            st.write(f"🔹 `{readable_time}` → **{word_count}** words")
    else:
        st.write("❌ No tracking data yet")
    
    st.markdown("---")
    
    st.markdown("### 👤 User Info")
    prolific_id = st.text_input(
        "Prolific ID",
        value=st.session_state.user_info["prolific_id"],
        key="sidebar_prolific_id"
    )
    st.session_state.user_info["prolific_id"] = prolific_id
    
    st.markdown("---")
    
    # Export tracking come JSON
    if st.session_state.content_tracking:
        st.markdown("### 📥 Export")
        tracking_json = json.dumps(
            {str(k): v for k, v in st.session_state.content_tracking.items()},
            ensure_ascii=False,
            indent=2
        )
        st.download_button(
            "📥 Download Tracking JSON",
            data=tracking_json,
            file_name=f"tracking_{st.session_state.user_info['prolific_id']}.json",
            mime="application/json"
        )

# ============================================================================
# MAIN UI
# ============================================================================

st.markdown(f"""
<div class="success-badge">
    Thank you for the conversation! Please provide your final thoughts below.
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

with col_form:
    st.markdown("### Your Response")
    
    # Text area for argumentation
    argumentation = st.text_area(
        "Your argumentation:",
        placeholder="Type your explanation here...",
        height=300,
        label_visibility="collapsed",
        key="argumentation_input"
    )
    
    # Debug: mostra il contenuto attuale
    with st.expander("🔍 Debug - Current Form Content"):
        current_content = st.session_state.get("argumentation_input", "")
        st.write(f"**Length:** {len(current_content)} characters")
        st.write(f"**Words:** {len(current_content.split()) if current_content.strip() else 0}")
        st.write(f"**Content:** `{current_content}`")
    
    # Form only for submit button
    with st.form("final_argumentation_form"):
        submitted = st.form_submit_button("Submit and Complete", use_container_width=True)

    if submitted:
        if argumentation.strip():
            st.session_state.final_argumentation = argumentation
            
            # Stop tracker
            if st.session_state.tracker:
                st.session_state.tracker.stop()
            
            # Print final summary
            print("\n" + "="*80)
            print("📊 FINAL SUBMISSION:")
            print("="*80)
            print(f"User: {st.session_state.user_info['prolific_id']}")
            print(f"Total words: {len(argumentation.split())}")
            print(f"Total seconds tracked: {len(st.session_state.content_tracking)}")
            print(f"\nContent tracking ({len(st.session_state.content_tracking)} entries):")
            for timestamp, content in sorted(st.session_state.content_tracking.items()):
                readable_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                word_count = len(content.split()) if content.strip() else 0
                print(f"  [{readable_time}] {word_count:2d} words | '{content}'")
            print("="*80 + "\n")
            
            # Try to save to database
            if st.session_state.sheet_connected:
                mock_prompt_data = {
                    "title": "Why not drink during job interview",
                    "description": "Professional conduct discussion"
                }
                
                success = save_to_google_sheets(
                    sheet,
                    st.session_state.user_info,
                    st.session_state.selected_prompt_key,
                    mock_prompt_data,
                    argumentation,
                    st.session_state.content_tracking,
                    st.session_state.final_chat_messages
                )
                
                if success:
                    st.markdown("""
                        <div class="success-badge">
                            ✅ Thank you for your participation! Your responses have been recorded.
                        </div>
                    """, unsafe_allow_html=True)
                    print("✅ Data saved to Google Sheets")
                else:
                    st.markdown("<div class='error'>❌ Error saving data. Please try again.</div>", unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class='error'>
                        ❌ Database connection error. Contact support.
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)

with col_assistant:
    st.markdown("### AI Assistant")
    
    chat_container = st.container(border=True, height=400)
    with chat_container:
        if not st.session_state.final_chat_messages:
            st.markdown("<p style='color: #999; text-align: center;'>No messages yet</p>", unsafe_allow_html=True)
        else:
            for message in st.session_state.final_chat_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
    
    if final_chat_prompt := st.chat_input("Ask something...", key="final_chat_input"):
        st.session_state.final_chat_messages.append({
            "role": "user",
            "content": final_chat_prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        response_text = "This is a response about professional conduct during interviews."
        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.session_state.final_chat_messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": response_timestamp
        })
        
        st.rerun()