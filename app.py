from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, time, date
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import fitz  # PyMuPDF
import os
import re
from dotenv import load_dotenv
from flask_migrate import Migrate
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from typing import List, Dict
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load environment variables from .env file
load_dotenv()

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:newpassword@localhost:3306/lsw_firm_db1'
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your_default_secret_key_here")
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit

# Initialize DB and login manager
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load DeepSeek model
MODEL_PATH = os.path.expanduser("~/Documents/deepseek-ai/DeepSeek-R1-Distill-Llama-8B")
  # Update this if your model is saved elsewhere
device = "cuda" if torch.cuda.is_available() else "cpu"

try:
    print("Loading DeepSeek model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(MODEL_PATH).to(device)
    print("✓ DeepSeek model loaded successfully")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None
    tokenizer = None

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    nationality = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    appointments = db.relationship('Appointment', backref='user', lazy=True)
    chat_history = db.relationship('ChatHistory', backref='user', lazy=True, cascade="all, delete-orphan")

class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_reply = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    __table_args__ = (db.Index('idx_user_timestamp', 'user_id', 'timestamp'),)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))



# Chat formatting
def format_chat_history(history: List[Dict]) -> str:
    return "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history)

def generate_deepseek_response(prompt: str, history: List[Dict] = None, max_length: int = 1500) -> str:
    if not model or not tokenizer:
        return "Error: Model not loaded"
    try:
        system_msg = {
            "role": "system",
            "content": f"Legal Context:\n{law_text[:10000]}\n\nYou are a helpful legal assistant."
        }
        chat_history = history or []
        messages = [system_msg] + chat_history + [{"role": "user", "content": prompt}]
        formatted_input = format_chat_history(messages)
        inputs = tokenizer(formatted_input, return_tensors="pt", truncation=True, max_length=4096).to(device)
        outputs = model.generate(
            inputs.input_ids,
            max_new_tokens=max_length,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
        full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = full_response.split("Assistant:")[-1].strip()
        return response.split("User:")[0].strip()
    except Exception as e:
        print(f"Generation error: {e}")
        return "Sorry, an error occurred generating the response."

# Routes
@app.route('/')
def home():
    return render_template('home.html',
                           user=current_user if current_user.is_authenticated else None,
                           today=date.today().isoformat())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            first_name = request.form['name']
            last_name = request.form['surname']
            dob = datetime.strptime(request.form['dob'], '%Y-%m-%d').date()
            nationality = request.form['nationality']
            phone = request.form['phone']
            email = request.form['email']
            username = request.form['username']
            password = request.form['password']
            confirm_password = request.form['confirm_password']
            address = request.form.get('address', '')

            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                flash('You must be at least 18 years old to register.', 'danger')
                return redirect(url_for('register'))

            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'danger')
                return redirect(url_for('register'))
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'danger')
                return redirect(url_for('register'))
            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return redirect(url_for('register'))

            new_user = User(
                username=username,
                password=generate_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                dob=dob,
                nationality=nationality,
                phone=phone,
                email=email,
                address=address
            )

            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash('Registration successful!', 'success')
            return redirect(url_for('home'))

        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')
            app.logger.error(f"Registration error: {e}")
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))
@app.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    if request.method == 'POST':
        try:
            phone_number = request.form['phone_number']
            date_str = request.form['date']
            time_str = request.form['time']
            message = request.form.get('message', '')

            # Validate phone number
            if not re.match(r'^\+?[0-9]{1,4}?[0-9]{6,12}$', phone_number):
                flash('Invalid phone number format', 'danger')
                return redirect(url_for('book'))

            # Parse date/time
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time_str, '%H:%M').time()

            # Validate business rules
            if appointment_date.weekday() >= 5:
                flash('Weekend appointments not available', 'danger')
                return redirect(url_for('book'))

            if not (time(9, 0) <= appointment_time <= time(17, 0)):
                flash('Appointments available 9AM-5PM only', 'danger')
                return redirect(url_for('book'))

            # Check for existing appointment
            existing = Appointment.query.filter(
                Appointment.user_id == current_user.id,
                Appointment.date == appointment_date,
                Appointment.time == appointment_time
            ).first()
            
            if existing:
                flash('You already have an appointment at this time', 'warning')
                return redirect(url_for('book'))

            # Create appointment
            new_appointment = Appointment(
                name=f"{current_user.first_name} {current_user.last_name}",
                email=current_user.email,
                phone_number=phone_number,
                date=appointment_date,
                time=appointment_time,
                message=message,
                user_id=current_user.id
            )

            db.session.add(new_appointment)
            db.session.commit()
            flash('Appointment booked successfully!', 'success')
            return redirect(url_for('confirmation'))

        except ValueError as e:
            flash(f'Invalid date/time format: {str(e)}', 'danger')
            return redirect(url_for('book'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to book appointment', 'danger')
            app.logger.error(f"Booking error: {str(e)}")
            return redirect(url_for('book'))

    return render_template('book.html', today=date.today().isoformat(), user=current_user)

@app.route('/confirmation')
def confirmation():
    return render_template('confirmation.html')

@app.route('/appointments')
@login_required
def appointments():
    user_appointments = Appointment.query.filter_by(user_id=current_user.id)\
                                      .order_by(Appointment.date, Appointment.time)\
                                      .all()
    return render_template('appointments.html', appointments=user_appointments)

@app.route("/chatbot")
@login_required
def chat_interface():
    return render_template("chatbot.html")

@app.route("/chatbot", methods=["POST"])
@login_required
def chatbot():
    data = request.json
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a message.", "timestamp": datetime.utcnow().isoformat()}), 400

    try:
        previous_chats = ChatHistory.query.filter_by(
            user_id=current_user.id
        ).order_by(ChatHistory.timestamp.desc()).limit(4).all()

        history = []
        for chat in reversed(previous_chats):
            history.extend([
                {"role": "user", "content": chat.user_message},
                {"role": "assistant", "content": chat.bot_reply}
            ])

        bot_reply = generate_deepseek_response(user_message, history)
        timestamp = datetime.utcnow()

        new_chat = ChatHistory(
            user_id=current_user.id,
            user_message=user_message,
            bot_reply=bot_reply,
            timestamp=timestamp
        )
        db.session.add(new_chat)

        chat_count = ChatHistory.query.filter_by(user_id=current_user.id).count()
        if chat_count > 20:
            oldest = ChatHistory.query.filter_by(user_id=current_user.id)\
                .order_by(ChatHistory.timestamp.asc()).limit(chat_count - 20).all()
            for chat in oldest:
                db.session.delete(chat)

        db.session.commit()

        return jsonify({
            "reply": bot_reply,
            "timestamp": timestamp.isoformat()
        })

    except Exception as e:
        app.logger.error(f"Chatbot error: {str(e)}")
        return jsonify({
            "reply": "Sorry, I encountered an error. Please try again.",
            "timestamp": datetime.utcnow().isoformat()
        }), 500

@app.route('/chat-history')
@login_required
def view_chat_history():
    chats = ChatHistory.query.filter_by(user_id=current_user.id)\
        .order_by(ChatHistory.timestamp.desc()).limit(5).all()
    return render_template('chat_history.html', chat_history=reversed(chats))

@app.route("/clear-chat-history", methods=["POST"])
@login_required
def clear_chat_history():
    try:
        deleted = ChatHistory.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Deleted {deleted} messages",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
