import os
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.json
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use "gpt-4" if available
            messages=[
                {"role": "system", "content": "You are an AI assistant trained to provide legal information based on the following text:"},
                {"role": "system", "content": law_text},
                {"role": "user", "content": user_message}
            ],
        )
        bot_reply = response.choices[0].message.content
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"}), 500

    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    app.run(debug=True)

