import streamlit as st
import pandas as pd
from openai import OpenAI
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# Show title and description.
# Connessione a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Funzione per caricare i dati da Google Sheets
def load_users_data():
    try:
        df = conn.read(worksheet="users", usecols=list(range(4)))
        return df.to_dict('records')
    except:
        return []

# Funzione per salvare i dati su Google Sheets
def save_users_data(users_list):
    df = pd.DataFrame(users_list)
    conn.update(
        worksheet="users",
        data=df,
    )

# Inizializza session state per i dati utente
if "user_data_collected" not in st.session_state:
    st.session_state.user_data_collected = False
if "user_info" not in st.session_state:
    st.session_state.user_info = {"nome": "", "cognome": "", "età": ""}

# Se i dati non sono stati raccolti, mostra il form
if not st.session_state.user_data_collected:
    st.subheader("📋 Benvenuto! Per iniziare, compilare il modulo:")
    
    with st.form("user_info_form"):
        nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
        cognome = st.text_input("Cognome", placeholder="Inserisci il tuo cognome")
        eta = st.number_input("Età", min_value=1, max_value=150, step=1, value=18)
        
        submitted = st.form_submit_button("Inizia a chattare")
        
        if submitted:
            if nome and cognome:
                # Salva i dati in session state
                st.session_state.user_info = {
                    "nome": nome,
                    "cognome": cognome,
                    "età": int(eta),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Salva i dati in Google Sheets
                users_list = load_users_data()
                users_list.append(st.session_state.user_info)
                save_users_data(users_list)
                
                st.session_state.user_data_collected = True
                st.rerun()
            else:
                st.error("Per favore, inserisci nome e cognome!")

else:
    # Mostra i dati dell'utente
    st.success(f"✅ Benvenuto, {st.session_state.user_info['nome']} {st.session_state.user_info['cognome']}!")
    
    # Crea il client OpenAI
    client = OpenAI(api_key=openai_api_key)
    
    # Inizializza session state per i messaggi
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Mostra i messaggi della chat
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Input per la chat
    if prompt := st.chat_input("Dimmi qualcosa..."):
        # Aggiungi il messaggio dell'utente
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Genera risposta
        stream = client.chat.completions.create(
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
    
    # Button per logout
    st.divider()
    if st.button("🔄 Logout"):
        st.session_state.user_data_collected = False
        st.session_state.messages = []
        st.rerun()