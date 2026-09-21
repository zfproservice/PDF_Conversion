import os
import streamlit as st
import pymupdf  # PyMuPDF for robust PDF text extraction
from mistralai import Mistral

# Page configuration
st.set_page_config(
    page_title="Mistral Assistant",
    page_icon="🤖",
    layout="centered"
)

# Initialize Mistral client using Streamlit Secrets (Sidebar settings removed)
if "MISTRAL_API_KEY" in st.secrets:
    api_key = st.secrets["MISTRAL_API_KEY"]
else:
    st.error("MISTRAL_API_KEY not found in Streamlit secrets. Please configure it in your `.streamlit/secrets.toml` file.")
    st.stop()

client = Mistral(api_key=api_key)

st.title("🤖 Mistral AI Assistant")
st.write("Upload a document or ask a question to get started.")

# File uploader for documents/PDFs
uploaded_file = st.file_uploader("Upload a PDF document", type=["pdf"])

extracted_text = ""
if uploaded_file is not None:
    try:
        # Open PDF with PyMuPDF (fitz) and extract text to prevent 422 API errors
        with pymupdf.open(stream=uploaded_file.read(), filetype="pdf") as doc:
            for page_num, page in enumerate(doc):
                extracted_text += f"\n--- Page {page_num + 1} ---\n" + page.get_text()
        st.success(f"Successfully extracted text from {uploaded_file.name}!")
    except Exception as e:
        st.error(f"Error reading PDF: {e}")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle user chat input
if prompt := st.chat_input("What would you like to know about your document or query?"):
    # Combine prompt with extracted PDF text if a document was uploaded
    full_prompt = prompt
    if extracted_text:
        full_prompt = f"Here is the document content:\n{extracted_text}\n\nUser Query: {prompt}"

    # Append user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call Mistral Chat Completions API
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Format messages for Mistral API
                api_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                api_messages.append({"role": "user", "content": full_prompt})

                response = client.chat.complete(
                    model="mistral-small-latest",
                    messages=api_messages
                )
                
                assistant_response = response.choices[0].message.content
                st.markdown(assistant_response)
                
                # Append assistant response to history
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            
            except Exception as e:
                st.error(f"API Error: {e}")