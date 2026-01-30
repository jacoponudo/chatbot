import streamlit as st
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

# Custom CSS (same as main app)
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

# Initialize session state
if "final_argumentation" not in st.session_state:
    st.session_state.final_argumentation = None
if "final_chat_messages" not in st.session_state:
    st.session_state.final_chat_messages = []
if "word_tracking" not in st.session_state:
    st.session_state.word_tracking = defaultdict(int)
if "last_check_time" not in st.session_state:
    st.session_state.last_check_time = time.time()

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Test Settings")
    
    use_mock_api = st.checkbox(
        "Use Mock API Response",
        value=True,
        help="If unchecked, requires valid OpenAI API key"
    )
    
    if not use_mock_api:
        api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        if not api_key:
            st.warning("⚠️ API key required to use real OpenAI API")
    
    st.markdown("---")
    st.markdown("### 📊 Current State")
    st.json({
        "Final Argumentation": st.session_state.final_argumentation[:50] + "..." if st.session_state.final_argumentation else None,
        "Chat Messages Count": len(st.session_state.final_chat_messages),
        "Word Tracking": dict(st.session_state.word_tracking)
    })

# Main content
st.markdown(f"""
<div class="success-badge">
    Testing Phase 4 - Final Argumentation Form + Lateral Chat
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

def track_words_callback():
    """Callback silenzioso che traccia le parole ogni secondo"""
    current_time = time.time()
    current_text = st.session_state.get("argumentation_input", "")
    word_count = len(current_text.split()) if current_text.strip() else 0
    
    # Arrotonda il tempo al secondo più vicino
    second_bucket = int(current_time)
    
    # Salva il conteggio delle parole per quel secondo
    st.session_state.word_tracking[second_bucket] = word_count
    st.session_state.last_check_time = current_time

with col_form:
    st.markdown("### Your Response")
    
    # Text area for argumentation
    argumentation = st.text_area(
        "Your argumentation:",
        placeholder="Type your explanation here...",
        height=300,
        label_visibility="collapsed",
        key="argumentation_input",
        on_change=track_words_callback
    )
    
    # Form only for submit button
    with st.form("final_argumentation_form"):
        submitted = st.form_submit_button("Submit and Complete", use_container_width=True)

    if submitted:
        if argumentation.strip():
            st.session_state.final_argumentation = argumentation
            
            # Final tracking
            track_words_callback()
            
            # Print tracking (visible in logs/debug)
            st.success("✅ Argumentation saved!")
            print("📊 WORD TRACKING PER SECONDO:")
            for second, word_count in sorted(st.session_state.word_tracking.items()):
                print(f"  Secondo {second}: {word_count} parole")
            
            # Display summary
            st.markdown("### 📋 Response Summary")
            st.write(f"**Word count:** {len(argumentation.split())} words")
            st.write(f"**Character count:** {len(argumentation)} characters")
            
            # Show word tracking
            with st.expander("📊 Word Tracking by Second"):
                tracking_data = dict(sorted(st.session_state.word_tracking.items()))
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
                    st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
    
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
                
In a real scenario, the AI would provide a thoughtful response about why drinking during a job interview is inappropriate. 
This could include points about professionalism, respect for the interviewer, health and safety considerations, etc."""
                response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Real OpenAI API
                if not use_mock_api and 'api_key' not in locals():
                    st.error("❌ API key required for real responses")
                    response_text = "Error: API key not provided"
                    response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    openai_client = OpenAI(api_key=api_key if not use_mock_api else "dummy")
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
st.markdown("## 📥 Export Test Data")

col1, col2 = st.columns(2)

with col1:
    if st.button("📋 Copy Session State", use_container_width=True):
        session_data = {
            "final_argumentation": st.session_state.final_argumentation,
            "final_chat_messages": st.session_state.final_chat_messages,
            "word_tracking": dict(st.session_state.word_tracking),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        st.json(session_data)

with col2:
    if st.button("🔄 Reset All Data", use_container_width=True):
        st.session_state.final_argumentation = None
        st.session_state.final_chat_messages = []
        st.session_state.word_tracking = defaultdict(int)
        st.session_state.last_check_time = time.time()
        st.success("✅ All data reset!")
        st.rerun()

# Display current session state at the bottom
with st.expander("🔍 Full Session State (Debug Info)"):
    debug_data = {
        "final_argumentation": st.session_state.final_argumentation,
        "final_chat_messages_count": len(st.session_state.final_chat_messages),
        "word_tracking": dict(st.session_state.word_tracking),
        "last_check_time": st.session_state.last_check_time
    }
    st.json(debug_data)