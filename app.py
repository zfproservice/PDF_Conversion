import io
import json
import urllib.error
import urllib.request
import pandas as pd
import pymupdf
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="PDF to Excel Converter", page_icon="📊", layout="centered"
)

st.title("📄 PDF to Excel Converter (Multi-AI Powered)")
st.write(
    "Upload a PDF service form, select your preferred AI provider, and"
    " convert it into an interactive table and Excel spreadsheet."
)

# AI Provider Selection (Including OpenRouter)
ai_provider = st.selectbox(
    "Select AI Provider",
    [
        "OpenRouter (Universal - Recommended)",
        "Mistral AI (Direct)",
        "Google Gemini (Direct)",
    ],
)

uploaded_file = st.file_uploader("Upload your PDF document", type=["pdf"])

if uploaded_file is not None:
  if st.button("🚀 Convert to Excel", type="primary"):
    with st.spinner(f"Extracting text and processing with {ai_provider}..."):
      try:
        # 1. Extract text from PDF locally using PyMuPDF
        extracted_text = ""
        with pymupdf.open(stream=uploaded_file.read(), filetype="pdf") as doc:
          for page_num, page in enumerate(doc):
            extracted_text += (
                f"\n--- Page {page_num + 1} ---\n" + page.get_text()
            )

        if not extracted_text.strip():
          raise Exception(
              "No text could be extracted from this PDF. It may be a scanned"
              " image format."
          )

        # 2. Build structured extraction prompt
        prompt = f"""
                Analyze the following extracted text from a field service PDF record. 
                Extract all tabular data and records into a valid JSON array of objects.
                
                Rules:
                1. Output MUST be a valid JSON array of objects representing rows.
                2. Extract all headers accurately (e.g., S/N, Customer, Model / Spec No, Serial No, Vehicle No, OEM, Travelling Start, Travelling End, Working Start, Working End, Report No, Date, Depot, Need to Down, Remarks).
                3. Resolve any ditto marks (") or repeated elements from previous rows with the actual text values.
                4. Return ONLY raw JSON text without any markdown code block wrappers like ```json.
                
                Document Content:
                {extracted_text}
                """

        content = ""
        url = ""
        payload = {}
        headers = {}

        # 3. Route request based on selected provider
        if "OpenRouter" in ai_provider:
          if "OPENROUTER_API_KEY" not in st.secrets:
            st.error("OPENROUTER_API_KEY missing from Streamlit secrets.")
            st.stop()
          api_key = st.secrets["OPENROUTER_API_KEY"].strip()

          url = "[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)"
          payload = {
              "model": "mistralai/mistral-small-latest",
              "messages": [{"role": "user", "content": prompt}],
          }
          headers = {
              "Authorization": f"Bearer {api_key}",
              "Content-Type": "application/json",
              "HTTP-Referer": "[https://streamlit.io](https://streamlit.io)",
              "X-Title": "PDF to Excel Converter",
          }

        elif "Mistral" in ai_provider:
          if "MISTRAL_API_KEY" not in st.secrets:
            st.error("MISTRAL_API_KEY missing from Streamlit secrets.")
            st.stop()
          api_key = st.secrets["MISTRAL_API_KEY"].strip()

          url = "[https://api.mistral.ai/v1/chat/completions](https://api.mistral.ai/v1/chat/completions)"
          payload = {
              "model": "mistral-small-latest",
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.1,
          }
          headers = {
              "Authorization": f"Bearer {api_key}",
              "Content-Type": "application/json",
          }

        else:  # Google Gemini (Direct)
          if "GEMINI_API_KEY" not in st.secrets:
            st.error("GEMINI_API_KEY missing from Streamlit secrets.")
            st.stop()
          api_key = st.secrets["GEMINI_API_KEY"].strip()

          url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}"
          payload = {
              "contents": [{
                  "parts": [{"text": prompt}]
              }]
          }
          headers = {"Content-Type": "application/json"}

        # Bulletproof URL sanitization
        url = url.strip("[]'\" \n\t")

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data_bytes, headers=headers, method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as response:
          res_json = json.loads(response.read().decode("utf-8"))

          if "OpenRouter" in ai_provider or "Mistral" in ai_provider:
            content = res_json["choices"][0]["message"]["content"].strip()
          else:
            content = (
                res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            )

        # Clean markdown wrappers if returned by the model
        if content.startswith("```"):
          content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        if content.lower().startswith("json"):
          content = content[4:].strip()

        # Parse into Pandas DataFrame
        data = json.loads(content)
        df = pd.DataFrame(data)

        st.success("Successfully converted PDF to Excel!")
        st.dataframe(df, use_container_width=True)

        # 4. Generate Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
          df.to_excel(writer, index=False, sheet_name="Extracted Records")
        excel_bytes = output.getvalue()
        file_name = uploaded_file.name.replace(".pdf", ".xlsx")

        st.download_button(
            label="📥 Download Excel File",
            data=excel_bytes,
            file_name=file_name,
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

      except urllib.error.HTTPError as http_err:
        error_body = (
            http_err.read().decode("utf-8") if hasattr(http_err, "read") else ""
        )
        st.error(
            f"HTTP Error {http_err.code}: {http_err.reason}\n\nServer Details:"
            f" {error_body}"
        )
      except Exception as e:
        st.error(f"An error occurred during conversion: {e}")