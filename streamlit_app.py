import streamlit as st
import time
from datetime import datetime

st.set_page_config(page_title="Editor con Auto-Save", layout="wide")

# Inizializza lo stato della sessione
if 'code_content' not in st.session_state:
    st.session_state.code_content = ""
if 'last_save_time' not in st.session_state:
    st.session_state.last_save_time = None
if 'save_history' not in st.session_state:
    st.session_state.save_history = []

st.title("📝 Editor di Codice con Auto-Save")
st.markdown("*Il contenuto viene salvato automaticamente ogni secondo*")

# Area di testo per il codice
code = st.text_area(
    "Scrivi il tuo codice qui:",
    value=st.session_state.code_content,
    height=400,
    key="code_editor",
    placeholder="Inizia a scrivere il tuo codice..."
)

# Colonne per il layout
col1, col2 = st.columns([3, 1])

with col1:
    # Auto-refresh ogni secondo
    placeholder = st.empty()
    
    # Controlla se il contenuto è cambiato
    if code != st.session_state.code_content:
        st.session_state.code_content = code
        current_time = datetime.now().strftime("%H:%M:%S")
        st.session_state.last_save_time = current_time
        
        # Aggiungi alla cronologia
        st.session_state.save_history.append({
            'time': current_time,
            'length': len(code)
        })
        
        # Mantieni solo gli ultimi 10 salvataggi
        if len(st.session_state.save_history) > 10:
            st.session_state.save_history.pop(0)
    
    if st.session_state.last_save_time:
        placeholder.success(f"✅ Ultimo salvataggio: {st.session_state.last_save_time}")
    
    # Auto-refresh ogni secondo
    time.sleep(1)
    st.rerun()

with col2:
    st.subheader("📊 Info")
    st.metric("Caratteri", len(st.session_state.code_content))
    st.metric("Righe", st.session_state.code_content.count('\n') + 1 if st.session_state.code_content else 0)
    
    if st.session_state.save_history:
        st.subheader("🕐 Cronologia")
        for save in reversed(st.session_state.save_history[-5:]):
            st.text(f"{save['time']} - {save['length']} car.")

# Pulsante per scaricare il codice
if st.session_state.code_content:
    st.download_button(
        label="💾 Scarica Codice",
        data=st.session_state.code_content,
        file_name=f"code_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain"
    )