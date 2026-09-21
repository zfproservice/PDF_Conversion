import base64
import io
import json
import pandas as pd
import requests
import streamlit as st

# Streamlit Page Setup
st.set_page_config(
    page_title="PDF to Excel Converter (Mistral Powered)", layout="centered"
)

st.title("📄 PDF to Excel Converter (Powered by Mistral AI)")
st.markdown(
    "Upload your scanned service records or forms (PDF). Mistral's vision model"
    " will extract the tabular data, resolve any ditto marks (`\"`), and"
    " convert it into an interactive table and Excel file."
)

# Automatically check Streamlit Secrets first
mistral_api_key = (
    st.secrets.get("MISTRAL_API_KEY")
    if "MISTRAL_API_KEY" in st.secrets
    else None
)

# Sidebar Configuration (Only show input box if secret is not found)
with st.sidebar:
  st.header("⚙️ Configuration")
  if not mistral_api_key:
    mistral_api_key = st.text_input(
        "Mistral API Key",
        type="password",
        help="Get your free key from console.mistral.ai",
    )
    st.caption("No secret detected. Please enter your key above.")
  else:
    st.success("🔒 API Key loaded securely from Secrets!")

# File Uploader
uploaded_file = st.file_uploader(
    "Upload Scanned PDF Document", type=["pdf"], accept_multiple_files=False
)

if uploaded_file and mistral_api_key:
  pdf_bytes = uploaded_file.read()

  if st.button("🚀 Extract Data & Convert to Excel", type="primary"):
    with st.spinner("Processing scanned PDF with Mistral Vision API..."):
      try:
        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

        prompt = (
            "Analyze this scanned document/form carefully. Extract all table rows"
            " and field records into a valid JSON array of objects containing"
            " clear key-value pairs. If there are quotation marks or ditto"
            " marks (\") representing repeated values from the row above,"
            " resolve and fill them in with the actual value they represent."
            " Return ONLY valid JSON without any surrounding explanation."
        )

        headers = {
            "Authorization": f"Bearer {mistral_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "mistral-small-latest",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": (
                            f"data:application/pdf;base64,{base64_pdf}"
                        ),
                    },
                ],
            }],
            "temperature": 0.1,
        }

        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()

        result_json = response.json()
        content = result_json["choices"][0]["message"]["content"]

        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
          cleaned_content = cleaned_content[7:]
        if cleaned_content.endswith("```"):
          cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()

        data = json.loads(cleaned_content)
        df = pd.DataFrame(data)

        st.success("Data extracted successfully!")
        st.dataframe(df, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
          df.to_excel(writer, index=False, sheet_name="Extracted Records")
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Download Excel File",
            data=excel_data,
            file_name="extracted_service_records.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

      except requests.exceptions.RequestException as req_err:
        st.error(f"API Connection Error: {req_err}")
      except json.JSONDecodeError:
        st.error(
            "Failed to parse model output as JSON. Raw response from model:"
        )
        st.code(content)
      except Exception as e:
        st.error(f"An unexpected error occurred: {e}")

elif uploaded_file and not mistral_api_key:
  st.warning(
      "⚠️ Please provide your Mistral API Key via Streamlit Secrets or the"
      " sidebar to proceed."
  )