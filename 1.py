import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Read content from LAW.txt with proper encoding handling
law_text = ""
if os.path.exists("LAW.txt"):
    try:
        with open("LAW.txt", "r", encoding="utf-8") as file:
            law_text = file.read()
    except UnicodeDecodeError:
        with open("LAW.txt", "r", encoding="latin-1") as file:
            law_text = file.read()
else:
    print("Warning: LAW.txt file not found.")

def find_relevant_section(question):
    """
    Searches for relevant sections in LAW.txt that match the user's question.
    Returns the most relevant part if found, otherwise returns None.
    """
    question_lower = question.lower()
    sentences = law_text.split(".")  # Splitting text into sentences
    
    relevant_sentences = [sentence.strip() for sentence in sentences if question_lower in sentence.lower()]
    
    if relevant_sentences:
        return " ".join(relevant_sentences) + "."
    else:
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.json
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400
    
    # Find relevant law section
    law_response = find_relevant_section(user_message)
    
    if not law_response:
        return jsonify({"reply": "Sorry, I can only answer questions based on the legal document. No matching section found."}), 400
    
    return jsonify({"reply": law_response})

if __name__ == "__main__":
    app.run(debug=True)

