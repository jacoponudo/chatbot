import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from openai import OpenAI
import json

st.title("📋 Questionario + Chat")

try:
    # Carica le credenziali e l'URL da secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["google_sheet_url"]
    openai_api_key = st.secrets["openai_api_key"]
    
    # Configura le credenziali con gli scope corretti
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client_sheets = gspread.authorize(creds)
    
    # Apri il foglio
    spreadsheet = client_sheets.open_by_url(sheet_url)
    sheet = spreadsheet.sheet1
    
    # Inizializza session state
    if "user_data_collected" not in st.session_state:
        st.session_state.user_data_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # FASE 1: Questionario
    if not st.session_state.user_data_collected:
        st.subheader("📋 Compilare il questionario")
        
        with st.form("questionnaire_form"):
            nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
            cognome = st.text_input("Cognome", placeholder="Inserisci il tuo cognome")
            luogo_nascita = st.text_input("Luogo di nascita", placeholder="Inserisci il luogo di nascita")
            
            submitted = st.form_submit_button("Inizia la chat")
            
            if submitted:
                if nome and cognome and luogo_nascita:
                    st.session_state.user_info = {
                        "nome": nome,
                        "cognome": cognome,
                        "luogo_nascita": luogo_nascita,
                        "data_inizio": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state.user_data_collected = True
                    st.rerun()
                else:
                    st.error("Compila tutti i campi!")
    
    # FASE 2: Chat con OpenAI
    else:
        user_info = st.session_state.user_info
        st.success(f"✅ Benvenuto, {user_info['nome']} {user_info['cognome']}!")
        st.write(f"Luogo di nascita: {user_info['luogo_nascita']}")
        st.divider()
        
        # Crea il client OpenAI
        openai_client = OpenAI(api_key=openai_api_key)
        
        # Mostra i messaggi della chat
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Input per la chat
        if prompt := st.chat_input("Scrivi il tuo messaggio..."):
            # Aggiungi il messaggio dell'utente
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Genera risposta da OpenAI
            stream = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                stream=True,
            )
            
            # Stream della risposta
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
            
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Salva automaticamente ogni scambio
            conversation_json = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
            sheet.append_row([
                user_info["nome"],
                user_info["cognome"],
                user_info["luogo_nascita"],
                conversation_json,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        
        # Button per logout
        # Button per logout
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Logout"):
                st.session_state.user_data_collected = False
                st.session_state.messages = []
                st.rerun()
        
        with col2:
            if st.button("📊 Mostra salvate"):
                st.subheader("Chat salvate")
                data = sheet.get_all_records()
                if data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Nessuna chat salvata ancora")

except KeyError as e:
    st.error(f"Errore: Configura nel secrets.toml: 'gcp_service_account', 'google_sheet_url' e 'openai_api_key'")
except Exception as e:
    st.error(f"Errore: {e}")