import streamlit as st
import pandas as pd
from openai import OpenAI
from datetime import datetime

# Show title and description.
st.title("💬 Chatbot")
st.write(
    "This is a simple chatbot that uses OpenAI's GPT-3.5 model to generate responses. "
    "To use this app, you need to provide an OpenAI API key, which you can get [here](https://platform.openai.com/account/api-keys). "
    "You can also learn how to build this app step by step by [following our tutorial](https://docs.streamlit.io/develop/tutorials/llms/build-conversational-apps)."
)

# Ask user for their OpenAI API key
openai_api_key = st.text_input("OpenAI API Key", type="password")

if not openai_api_key:
    st.info("Please add your OpenAI API key to continue.", icon="🗝️")
else:
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
                        "età": eta,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
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
        
        # Sezione per salvare i dati in DataFrame
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Salva dati in CSV"):
                # Crea DataFrame dai dati dell'utente
                df = pd.DataFrame([st.session_state.user_info])
                
                # Salva in CSV
                filename = f"/workspaces/chatbot/data/utenti_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df.to_csv(filename, index=False, encoding='utf-8')
                st.success(f"✅ Dati salvati in {filename}")
                st.dataframe(df, use_container_width=True)
        
        with col2:
            if st.button("🔄 Logout"):
                st.session_state.user_data_collected = False
                st.session_state.messages = []
                st.rerun()