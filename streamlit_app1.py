import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import time

# Page configuration
st.set_page_config(
    page_title="Everyday Norm Experiment - Phase 4",
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
    
    .debug-info {
        background: #f3f4f6;
        padding: 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        color: #666;
        margin-top: 1rem;
    }
    
    .timer-display {
        background: #003d82;
        color: white;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        font-size: 1.1rem;
        font-weight: 600;
        text-align: center;
        margin-bottom: 1rem;
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


def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, argumentation, text_tracking, final_chat_messages):
    """Salva i dati su Google Sheets"""
    try:
        final_chat_json = json.dumps(final_chat_messages or [], ensure_ascii=False, indent=2)
        
        # Formatta il text tracking in JSON strutturato
        text_tracking_json = ""
        if text_tracking:
            formatted_tracking = {}
            for timestamp, text_data in sorted(text_tracking.items()):
                readable_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                formatted_tracking[readable_time] = {
                    "timestamp": timestamp,
                    "text": text_data["text"],
                    "word_count": text_data["word_count"],
                    "char_count": text_data["char_count"]
                }
            
            text_tracking_json = json.dumps(formatted_tracking, ensure_ascii=False, indent=2)
        
        sheet.append_row([
            user_info["prolific_id"],
            prompt_key,
            prompt_data["title"],
            argumentation,
            text_tracking_json,
            final_chat_json,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception as e:
        print(f"❌ Errore nel salvataggio: {str(e)}")
        return False


# ============================================================================
# INITIALIZE SESSION STATE
# ============================================================================

# Inizializza il timer PRIMA di tutto
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    print(f"⏱️ Timer started at {datetime.now().strftime('%H:%M:%S')}")

if "last_save_time" not in st.session_state:
    st.session_state.last_save_time = time.time()

if "final_argumentation" not in st.session_state:
    st.session_state.final_argumentation = None
if "final_chat_messages" not in st.session_state:
    st.session_state.final_chat_messages = []
if "text_tracking" not in st.session_state:
    st.session_state.text_tracking = {}
if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "prolific_id": "TEST_USER_001",
        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
if "sheet_connected" not in st.session_state:
    st.session_state.sheet_connected = False
if "selected_prompt_key" not in st.session_state:
    st.session_state.selected_prompt_key = "norm_test"
if "is_submitted" not in st.session_state:
    st.session_state.is_submitted = False
if "current_text" not in st.session_state:
    st.session_state.current_text = ""

# Tentare la connessione a Google Sheets
sheet, is_connected = init_google_sheets()
st.session_state.sheet_connected = is_connected

# ============================================================================
# TRACKING LOGIC - AUTOMATIC SAVE OGNI SECONDO
# ============================================================================

def auto_save_text():
    """Salva automaticamente il testo corrente ogni secondo"""
    current_time = time.time()
    elapsed_since_last_save = current_time - st.session_state.last_save_time
    
    # Salva ogni secondo
    if elapsed_since_last_save >= 1.0 and not st.session_state.is_submitted:
        current_second = int(current_time)
        text_content = st.session_state.current_text
        
        word_count = len(text_content.split()) if text_content.strip() else 0
        char_count = len(text_content)
        
        # Salva snapshot
        st.session_state.text_tracking[current_second] = {
            "text": text_content,
            "word_count": word_count,
            "char_count": char_count
        }
        
        st.session_state.last_save_time = current_time
        
        readable_time = datetime.fromtimestamp(current_second).strftime("%H:%M:%S")
        print(f"💾 [{readable_time}] Auto-saved: {word_count} words, {char_count} chars")
        
        return True
    return False

# ============================================================================
# UI
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

# Create two columns
col_form, col_debug = st.columns([2, 1])

with col_form:
    # Timer display
    elapsed_time = int(time.time() - st.session_state.start_time)
    minutes = elapsed_time // 60
    seconds = elapsed_time % 60
    
    st.markdown(f"""
    <div class="timer-display">
        ⏱️ Time Elapsed: {minutes:02d}:{seconds:02d}
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### Your Response")
    
    # Text area for argumentation
    argumentation = st.text_area(
        "Your argumentation:",
        value=st.session_state.current_text,
        placeholder="Type your explanation here...",
        height=300,
        label_visibility="collapsed",
        key="argumentation_input"
    )
    
    # Aggiorna il testo corrente nel session state
    st.session_state.current_text = argumentation
    
    # Submit button
    if st.button("Submit and Complete", type="primary", use_container_width=True):
        if argumentation.strip():
            st.session_state.final_argumentation = argumentation
            st.session_state.is_submitted = True
            
            # Salva l'ultimo snapshot prima del submit
            current_second = int(time.time())
            st.session_state.text_tracking[current_second] = {
                "text": argumentation,
                "word_count": len(argumentation.split()),
                "char_count": len(argumentation)
            }
            
            # Print final summary
            print("\n" + "="*60)
            print("📊 FINAL SUBMISSION:")
            print("="*60)
            print(f"User: {st.session_state.user_info['prolific_id']}")
            print(f"Total words: {len(argumentation.split())}")
            print(f"Total time: {elapsed_time}s")
            print(f"Snapshots saved: {len(st.session_state.text_tracking)}")
            print("="*60 + "\n")
            
            # Save to Google Sheets
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
                    st.session_state.text_tracking,
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
                        ❌ Database connection error. Please contact the researcher.
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)

with col_debug:
    st.markdown("### Debug Info")
    
    current_time = time.time()
    elapsed = current_time - st.session_state.start_time
    time_since_save = current_time - st.session_state.last_save_time
    
    st.markdown(f"""
    <div class="debug-info">
        <strong>⏱️ Tracking Status</strong><br>
        Total time: {int(elapsed)}s<br>
        Since last save: {time_since_save:.1f}s<br>
        Total snapshots: {len(st.session_state.text_tracking)}<br>
        Current words: {len(argumentation.split())}<br>
        Current chars: {len(argumentation)}<br>
        Status: {'✅ Submitted' if st.session_state.is_submitted else '🔄 Active'}
    </div>
    """, unsafe_allow_html=True)
    
    # Mostra ultimi 10 snapshot
    if st.session_state.text_tracking:
        st.markdown("**Last 10 snapshots:**")
        recent = sorted(st.session_state.text_tracking.items())[-10:]
        for timestamp, data in recent:
            readable_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            st.markdown(f"`{readable_time}`: {data['word_count']} words, {data['char_count']} chars")

# ============================================================================
# AUTO-SAVE MECHANISM - Esegui il salvataggio automatico
# ============================================================================

if not st.session_state.is_submitted:
    # Prova a salvare (se è passato almeno 1 secondo)
    was_saved = auto_save_text()
    
    # Forza il rerun dopo 1 secondo usando st.rerun() con timer
    time.sleep(0.1)  # Piccolo delay per evitare loop troppo veloci
    st.rerun()