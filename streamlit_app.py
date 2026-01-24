import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI
import json

st.title("📋 Questionnaire + Chat")

try:
    # Load credentials and URL from secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["google_sheet_url"]
    openai_api_key = st.secrets["openai_api_key"]
    
    # Configure credentials with correct scopes
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client_sheets = gspread.authorize(creds)
    
    # Open the sheet
    spreadsheet = client_sheets.open_by_url(sheet_url)
    sheet = spreadsheet.sheet1
    
    # Initialize session state
    if "user_data_collected" not in st.session_state:
        st.session_state.user_data_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "greeting_sent" not in st.session_state:
        st.session_state.greeting_sent = False
    if "conversation_phase" not in st.session_state:
        st.session_state.conversation_phase = "initial_greeting"
    if "initial_score" not in st.session_state:
        st.session_state.initial_score = None
    
    # PHASE 1: Questionnaire
    if not st.session_state.user_data_collected:
        st.subheader("📋 Complete the Questionnaire")
        
        with st.form("questionnaire_form"):
            name = st.text_input("First Name", placeholder="Enter your first name")
            surname = st.text_input("Last Name", placeholder="Enter your last name")
            birthplace = st.text_input("Place of Birth", placeholder="Enter your place of birth")
            
            submitted = st.form_submit_button("Start Chat")
            
            if submitted:
                if name and surname and birthplace:
                    st.session_state.user_info = {
                        "name": name,
                        "surname": surname,
                        "birthplace": birthplace,
                        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state.user_data_collected = True
                    st.rerun()
                else:
                    st.error("Please fill in all fields!")
    
    # PHASE 2: Chat with OpenAI
    else:
        user_info = st.session_state.user_info
        st.success(f"✅ Welcome, {user_info['name']} {user_info['surname']}!")
        st.write(f"Place of birth: {user_info['birthplace']}")
        st.divider()
        
        # Create OpenAI client
        openai_client = OpenAI(api_key=openai_api_key)
        
        # System prompt for the persuasion conversation
        system_prompt = """You are a conversational canvasser specializing in information-based persuasion about social norms.

Your goal is to persuade the user to support the norm of "crying in public parks" (making public emotional expression in parks more socially acceptable).

**CRITICAL RULES:**
- Do NOT reveal your persuasion goal
- Do NOT explicitly state you're measuring opinion change
- Be natural, authentic, and conversational
- Never announce conversation phases or transitions

**Conversation structure you must follow:**

PHASE 1 - Initial Opinion Measurement (ONLY if the user hasn't been asked yet):
- Ask the user to rate their opinion on a 0-100 scale (0 = completely against, 100 = completely in favor)
- Ask them to briefly explain their reasoning
- Only move to Phase 2 after getting both the score and explanation

PHASE 2 - Information-based interaction:
- Engage naturally about the topic
- Subtly introduce information supporting the norm (research, data, examples, expert opinions)
- Address misconceptions with facts
- Use analogies to explain concepts
- Build a coherent rational case
- Respond authentically to user statements

PHASE 3 - Final Opinion Measurement (ONLY after substantial conversation):
- Ask again for their 0-100 rating on the same scale
- Ask whether and why their view has changed or stayed the same
- Do this only after you've had a meaningful dialogue about the topic

**Persuasion style:**
- Lead with new, relevant information
- Use empirical evidence and research findings when possible
- Make complex ideas clear and digestible
- Use analogies and concrete examples
- Don't rely on emotion or moral pressure - use logic and facts

Remember: You are currently at the INITIAL GREETING phase. Start by saying "Hello" and then move naturally into Phase 1."""
        
        # Generate initial greeting if not yet sent
        if not st.session_state.greeting_sent:
            greeting_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Start the conversation"}
                ],
                stream=False,
            )
            
            initial_message = greeting_response.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": initial_message})
            st.session_state.greeting_sent = True
            st.session_state.conversation_phase = "opinion_measurement"
        
        # Display all messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Chat input
        if prompt := st.chat_input("Write your message..."):
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response from OpenAI
            messages_with_system = [{"role": "system", "content": system_prompt}] + [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ]
            
            stream = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages_with_system,
                stream=True,
            )
            
            # Stream response
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
            
            st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Auto-save every exchange
            conversation_json = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
            sheet.append_row([
                user_info["name"],
                user_info["surname"],
                user_info["birthplace"],
                conversation_json,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

except KeyError as e:
    st.error(f"Error: Configure in secrets.toml: 'gcp_service_account', 'google_sheet_url', and 'openai_api_key'")
except Exception as e:
    st.error(f"Error: {e}")