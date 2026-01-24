import streamlit as st
import gspread
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import json

st.title("📝 Salva il Tuo Nome")

# Input delle credenziali JSON
st.write("Incolla qui le tue credenziali Google Service Account (JSON)")
credentials_json = st.text_area("Credenziali JSON", height=200)

# Input Google Sheets URL
sheet_url = st.text_input("Google Sheets URL", placeholder="https://docs.google.com/spreadsheets/d/...")

if not credentials_json or not sheet_url:
    st.info("Inserisci credenziali e URL per continuare")
else:
    try:
        # Carica le credenziali
        creds_dict = json.loads(credentials_json)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Apri il foglio
        sheet = client.open_by_url(sheet_url).worksheet("Sheet1")
        
        # Form per inserire il nome
        with st.form("name_form"):
            nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
            email = st.text_input("Email", placeholder="Inserisci la tua email")
            
            submitted = st.form_submit_button("Salva")
            
            if submitted:
                if nome and email:
                    sheet.append_row([
                        nome,
                        email,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ])
                    st.success(f"✅ Nome '{nome}' salvato!")
                else:
                    st.error("Compila tutti i campi!")
        
        # Mostra i dati
        st.divider()
        st.subheader("📊 Dati salvati")
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nessun dato ancora")
            
    except json.JSONDecodeError:
        st.error("JSON non valido")
    except Exception as e:
        st.error(f"Errore: {e}")