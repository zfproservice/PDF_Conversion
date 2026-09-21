import io
import json
from mistralai import Mistral
import pandas as pd
import pymupdf  # PyMuPDF for robust PDF text extraction
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="PDF to Excel Converter", page_icon="📊", layout="centered"
)

# Load API key securely from Streamlit Secrets (No sidebar settings)
if "MISTRAL_API_KEY" in st.secrets:
  api_key = st.secrets["MISTRAL_API_KEY"]
else:
  st.error(
      "MISTRAL_API_KEY not found in Streamlit secrets. Please configure it in"
      " your `.streamlit/secrets.toml` file."
  )
  st.stop()

st.title("📄 PDF to Excel Converter (Mistral Powered)")
st.write(
    "Upload a PDF service form. The app will extract the text, structure the"
    ' table data (auto-filling ditto marks `"`), and generate an Excel'
    " spreadsheet."
)

uploaded_file = st.file_uploader("Upload your PDF document", type=["pdf"])

if uploaded_file is not None:
  if st.button("Convert to Excel", type="primary"):
    with st.spinner("Extracting text and processing with Mistral AI..."):
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

        # 3. Call Mistral API using the official SDK
        client = Mistral(api_key=api_key)
        response = client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        content = response.choices[0].message.content.strip()

        # Clean markdown wrappers if returned by the model
        if content.startswith("```"):
          content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        if content.lower().startswith("json"):
          content = content[4:].strip()

        # Parse into Pandas DataFrame
        data = json.loads(content)
        df = pd.DataFrame(data)

        st.success("Successfully converted PDF to Excel!")
        st.dataframe(df)

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

      except Exception as e:
        st.error(f"An error occurred during conversion: {str(e)}")