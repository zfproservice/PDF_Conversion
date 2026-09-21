import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import io
import json
import time
import base64
import requests

st.set_page_config(page_title="PDF to Excel Converter", page_icon="📊", layout="centered")

st.title("📄 PDF to Editable Excel Converter")
st.write("Upload a PDF tracking form or record. The app will extract table data, auto-fill ditto marks (`\"`), and generate an Excel spreadsheet. It includes free fallbacks if primary servers are busy.")

# Retrieve API Keys from Streamlit Secrets or sidebar input
gemini_api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None
openrouter_api_key = st.secrets.get("OPENROUTER_API_KEY") if "OPENROUTER_API_KEY" in st.secrets else None

with st.sidebar:
    st.header("Settings")
    if not gemini_api_key:
        gemini_api_key = st.text_input("Enter Gemini API Key (Primary):", type="password")
        st.caption("Get a free key from [Google AI Studio](https://aistudio.google.com).")
    
    if not openrouter_api_key:
        openrouter_api_key = st.text_input("Enter OpenRouter API Key (Optional Fallback):", type="password")
        st.caption("Get a free key from [OpenRouter](https://openrouter.ai).")

uploaded_file = st.file_uploader("Upload your PDF document", type=["pdf"])

def clean_and_fill_df(df: pd.DataFrame) -> pd.DataFrame:
    """Replaces ditto marks and fills down missing values from above rows."""
    df = df.replace(to_replace=r'^\s*["\u201c\u201d\u201e\u201f\u2033\u2036]\s*$', value=None, regex=True)
    df = df.ffill()
    return df

def df_to_excel(df: pd.DataFrame) -> bytes:
    """Converts DataFrame into formatted Excel file in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Extracted Records')
        
        worksheet = writer.sheets['Extracted Records']
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
            
    return output.getvalue()

def fallback_openrouter_extract(pdf_bytes, prompt, key):
    """Fallback extractor using OpenRouter's auto-router free vision model."""
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openrouter/free",  # Automatically routes to an active free vision-capable model
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:application/pdf;base64,{base64_pdf}"},
                },
            ],
        }],
    }
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]

if uploaded_file and gemini_api_key:
    if st.button("Convert to Excel", type="primary"):
        with st.status("Processing PDF file...", expanded=True) as status:
            progress_bar = st.progress(0)
            
            try:
                # Step 1: Read PDF
                st.write("📖 Reading uploaded PDF file...")
                progress_bar.progress(15)
                
                client = genai.Client(api_key=gemini_api_key)
                pdf_bytes = uploaded_file.read()

                prompt = """
                Extract all tabular data from this PDF document into structured JSON format.
                
                Rules:
                1. Output MUST be a valid JSON array of objects representing rows.
                2. Extract all headers accurately (e.g., S/N, Customer, Model / Spec No, Serial No, Vehicle No, OEM, Travelling Start, Travelling End, Working Start, Working End, Report No, Date, Depot, Need to Down, Remarks).
                3. If a cell contains a ditto mark (") or represents repeated text from the row above, output the actual repeated string value directly.
                4. Do not wrap the response in markdown code blocks like ```json. Return ONLY raw JSON text.
                """

                # Step 2: Extract data using Gemini AI with stable production models
                st.write("🤖 Extracting table data using Gemini AI...")
                progress_bar.progress(35)

                max_attempts = 3
                raw_text = None
                success = False
                
                for attempt in range(max_attempts):
                    for model_name in ['gemini-2.5-flash', 'gemini-2.5-pro']:
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=[
                                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                                    prompt
                                ]
                            )
                            raw_text = response.text
                            success = True
                            break
                        except Exception as e:
                            if "503" not in str(e) and "404" not in str(e):
                                raise e
                    
                    if success:
                        break
                        
                    if attempt < max_attempts - 1:
                        wait_time = 4 * (2 ** attempt)
                        st.write(f"⏳ Gemini servers busy. Waiting {wait_time}s before retry {attempt + 2}/{max_attempts}...")
                        time.sleep(wait_time)
                
                # Step 2.5: OpenRouter Fallback
                if not success:
                    if openrouter_api_key:
                        st.write("⚠️ Gemini models unavailable. Initiating free OpenRouter fallback...")
                        raw_text = fallback_openrouter_extract(pdf_bytes, prompt, openrouter_api_key)
                    else:
                        raise Exception("Gemini models are currently overloaded/unavailable. Please add an OpenRouter API key in sidebar settings for free backup fallback, or try again later.")

                # Step 3: Parse and clean data
                st.write("🧹 Cleaning extracted data & resolving ditto marks...")
                progress_bar.progress(70)

                raw_text = raw_text.strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
                if raw_text.lower().startswith("json"):
                    raw_text = raw_text[4:].strip()
                
                data = json.loads(raw_text)
                df = pd.DataFrame(data)

                # Post-processing
                df = clean_and_fill_df(df)

                # Step 4: Formatting Excel document
                st.write("📊 Generating formatted Excel file...")
                progress_bar.progress(90)
                
                excel_bytes = df_to_excel(df)
                file_name = uploaded_file.name.replace(".pdf", ".xlsx")

                # Step 5: Finish
                progress_bar.progress(100)
                status.update(label="✅ Conversion Complete!", state="complete", expanded=False)

                st.success("Successfully converted PDF to Excel!")
                
                st.subheader("Data Preview")
                st.dataframe(df)

                st.download_button(
                    label="📥 Download Excel File",
                    data=excel_bytes,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                status.update(label="❌ Conversion Failed", state="error", expanded=True)
                st.error(f"An error occurred during conversion: {str(e)}")

elif uploaded_file and not gemini_api_key:
    st.warning("Please enter your Gemini API Key in the sidebar to proceed.")