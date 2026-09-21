import io
import json
import time
from google import genai
from google.genai import types
import pandas as pd
import pdfplumber
import streamlit as st

st.set_page_config(
    page_title="PDF to Excel Converter", page_icon="📊", layout="centered"
)

st.title("📄 PDF to Editable Excel Converter")
st.write(
    "Upload a PDF tracking form or record. The app will extract table data,"
    ' auto-fill ditto marks (`"`), and generate an Excel spreadsheet with'
    " built-in local fallback."
)

# Retrieve API Key from Streamlit Secrets or sidebar input
gemini_api_key = (
    st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None
)

if not gemini_api_key:
  with st.sidebar:
    st.header("Settings")
    gemini_api_key = st.text_input("Enter Gemini API Key:", type="password")
    st.caption("Get a free key from [Google AI Studio](https://aistudio.google.com).")

uploaded_file = st.file_uploader("Upload your PDF document", type=["pdf"])


def clean_and_fill_df(df: pd.DataFrame) -> pd.DataFrame:
  """Replaces ditto marks and fills down missing values from above rows."""
  df = df.replace(
      to_replace=r'^\s*["\u201c\u201d\u201e\u201f\u2033\u2036]\s*$',
      value=None,
      regex=True,
  )
  df = df.ffill()
  return df


def df_to_excel(df: pd.DataFrame) -> bytes:
  """Converts DataFrame into formatted Excel file in memory."""
  output = io.BytesIO()
  with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Extracted Records")

    worksheet = writer.sheets["Extracted Records"]
    for col in worksheet.columns:
      max_len = max(len(str(cell.value or "")) for cell in col)
      col_letter = col[0].column_letter
      worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

  return output.getvalue()


def extract_pdf_locally(pdf_bytes: bytes) -> pd.DataFrame:
  """Extracts tables locally using pdfplumber without any external API calls."""
  all_rows = []
  with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    for page in pdf.pages:
      table = page.extract_table()
      if table:
        all_rows.extend(table)

  if all_rows and len(all_rows) > 1:
    df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
    return df
  return None


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

        # Step 2: Try Gemini AI with stable production models & retry backoff
        st.write("🤖 Extracting table data using Gemini AI...")
        progress_bar.progress(35)

        max_attempts = 3
        raw_text = None
        success = False

        for attempt in range(max_attempts):
          for model_name in ["gemini-2.5-flash", "gemini-2.5-pro"]:
            try:
              response = client.models.generate_content(
                  model=model_name,
                  contents=[
                      types.Part.from_bytes(
                          data=pdf_bytes, mime_type="application/pdf"
                      ),
                      prompt,
                  ],
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
            wait_time = 4 * (2**attempt)
            st.write(
                f"⏳ Gemini servers busy. Waiting {wait_time}s before retry"
                f" {attempt + 2}/{max_attempts}..."
            )
            time.sleep(wait_time)

        # Step 2.5: Local Fallback if Gemini is overloaded
        df = None
        if success and raw_text:
          st.write("🧹 Cleaning extracted data & resolving ditto marks...")
          progress_bar.progress(70)

          raw_text = raw_text.strip()
          if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
          if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:].strip()

          data = json.loads(raw_text)
          df = pd.DataFrame(data)
        else:
          st.write(
              "⚠️ Gemini servers busy. Switching to local structural"
              " extraction..."
          )
          progress_bar.progress(70)
          df = extract_pdf_locally(pdf_bytes)
          if df is None:
            raise Exception(
                "Gemini servers are overloaded and local table extraction could"
                " not parse this PDF format."
            )

        # Post-processing
        df = clean_and_fill_df(df)

        # Step 3: Formatting Excel document
        st.write("📊 Generating formatted Excel file...")
        progress_bar.progress(90)

        excel_bytes = df_to_excel(df)
        file_name = uploaded_file.name.replace(".pdf", ".xlsx")

        # Step 4: Finish
        progress_bar.progress(100)
        status.update(
            label="✅ Conversion Complete!", state="complete", expanded=False
        )

        st.success("Successfully converted PDF to Excel!")

        st.subheader("Data Preview")
        st.dataframe(df)

        st.download_button(
            label="📥 Download Excel File",
            data=excel_bytes,
            file_name=file_name,
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

      except Exception as e:
        status.update(label="❌ Conversion Failed", state="error", expanded=True)
        st.error(f"An error occurred during conversion: {str(e)}")

elif uploaded_file and not gemini_api_key:
  st.warning("Please enter your Gemini API Key in the sidebar to proceed.")