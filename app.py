response = client.models.generate_content(
    model='gemini-3.6-flash',
    contents=[
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        prompt
    ]
)