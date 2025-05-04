import fitz  # PyMuPDF
import json

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text") + "\n"
    return text.strip()

pdf_text = extract_text_from_pdf("LAW.pdf")
print(pdf_text)  # Check the extracted text


import json

data = [
    {
        "messages": [
            {"role": "system", "content": "You are a legal expert assistant."},
            {"role": "user", "content": "What is the procedure for filing a lawsuit?"},
            {"role": "assistant", "content": "To file a lawsuit, you need to submit a complaint to the appropriate court, pay the filing fees, and serve the defendant."}
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What is the statute of limitations for contract disputes?"},
            {"role": "assistant", "content": "The statute of limitations for contract disputes varies by jurisdiction. In many places, it ranges from 3 to 6 years."}
        ]
    }
]

# Save to a JSONL file
with open("training_data.jsonl", "w", encoding="utf-8") as f:
    for entry in data:
        f.write(json.dumps(entry) + "\n")
