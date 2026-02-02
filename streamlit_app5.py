import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import json

st.set_page_config(page_title="Editor con Auto-Save", layout="wide")

# Inizializza lo stato della sessione
if 'code_content' not in st.session_state:
    st.session_state.code_content = ""
if 'last_save_time' not in st.session_state:
    st.session_state.last_save_time = None
if 'save_history' not in st.session_state:
    st.session_state.save_history = []
if 'save_counter' not in st.session_state:
    st.session_state.save_counter = 0

# Funzione callback per il salvataggio
def save_code():
    current_time = datetime.now().strftime("%H:%M:%S")
    st.session_state.last_save_time = current_time
    st.session_state.save_counter += 1
    
    # Aggiungi alla cronologia
    st.session_state.save_history.append({
        'time': current_time,
        'length': len(st.session_state.code_editor)
    })
    
    # Mantieni solo gli ultimi 10 salvataggi
    if len(st.session_state.save_history) > 10:
        st.session_state.save_history.pop(0)

st.title("📝 Editor di Codice con Auto-Save")
st.markdown("*Il contenuto viene salvato automaticamente ogni secondo*")

# Colonne per il layout
col1, col2 = st.columns([3, 1])

with col1:
    # Area di testo per il codice con callback
    code = st.text_area(
        "Scrivi il tuo codice qui:",
        value=st.session_state.code_content,
        height=400,
        key="code_editor",
        placeholder="Inizia a scrivere il tuo codice...",
        on_change=save_code
    )
    
    # JavaScript per triggare il submit ogni secondo
    components.html(
        f"""
        <script>
        const textarea = window.parent.document.querySelector('textarea[aria-label="Scrivi il tuo codice qui:"]');
        
        if (textarea) {{
            let lastValue = textarea.value;
            
            setInterval(() => {{
                if (textarea.value !== lastValue) {{
                    lastValue = textarea.value;
                    
                    // Simula un evento di cambio
                    const event = new Event('input', {{ bubbles: true }});
                    textarea.dispatchEvent(event);
                    
                    // Trigghera il blur per forzare Streamlit a registrare il cambio
                    textarea.blur();
                    setTimeout(() => textarea.focus(), 10);
                }}
            }}, 1000);
        }}
        </script>
        """,
        height=0
    )
    
    if st.session_state.last_save_time:
        st.success(f"✅ Ultimo salvataggio: {st.session_state.last_save_time} (Salvataggi: {st.session_state.save_counter})")

with col2:
    st.subheader("📊 Info")
    st.metric("Caratteri", len(st.session_state.code_editor if 'code_editor' in st.session_state else ""))
    st.metric("Righe", (st.session_state.code_editor.count('\n') + 1) if 'code_editor' in st.session_state and st.session_state.code_editor else 0)
    
    if st.session_state.save_history:
        st.subheader("🕐 Cronologia")
        for save in reversed(st.session_state.save_history[-5:]):
            st.text(f"{save['time']} - {save['length']} car.")

# Pulsante per scaricare il codice
if st.session_state.code_editor:
    st.download_button(
        label="💾 Scarica Codice",
        data=st.session_state.code_editor,
        file_name=f"code_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain"
    )
