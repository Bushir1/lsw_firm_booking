from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, time
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import fitz  # PyMuPDF
import requests
import os
from dotenv import load_dotenv
from openai import OpenAI
from flask_migrate import Migrate
from datetime import datetime, time, date




# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Allow frontend to access this backend

# Load environment variables from .env file
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:benjamin@localhost:3306/my_database'
#app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:newpassword@localhost:3306/lsw_firm_db'


# Set a secret key for session management (required for flash messages & Flask-Login)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your_default_secret_key_here")


# Initialize the database
db = SQLAlchemy(app)
migrate = Migrate(app, db)
# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Define the User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # Storing hashed password
    email = db.Column(db.String(120), unique=True, nullable=False)  # Add email field
    first_name = db.Column(db.String(100), nullable=False)  # Add first name
    last_name = db.Column(db.String(100), nullable=False)  # Add last name
    dob = db.Column(db.Date, nullable=False)  # Add date of birth
    nationality = db.Column(db.String(100), nullable=False)  # Add nationality
    phone = db.Column(db.String(15), nullable=False)  # Add phone number
    address = db.Column(db.String(255), nullable=True)  # Add address field (optional)
    appointments = db.relationship('Appointment', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'


class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Define the Appointment model
class Appointment(db.Model):
    __tablename__ = 'appointments'  # Explicitly set the table name
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)  # Add phone_number field
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Appointment {self.name} on {self.date}>'


# Add this model to your existing models
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_message = db.Column(db.String(500), nullable=False)
    bot_reply = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Load a user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # ✅ Correct for SQLAlchemy 2.0


# Home route with user greeting
@app.route('/')
def home():
    return render_template('home.html', user=current_user if current_user.is_authenticated else None)

# Registration route with password hashing
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Extract data from the form
        first_name = request.form['name']
        last_name = request.form['surname']
        dob = request.form['dob']
        nationality = request.form['nationality']
        phone = request.form['phone']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        address = request.form.get('address', '')  # Optional field

        # Check if the username or email already exists
        existing_user = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))
        if existing_email:
            flash('Email already exists. Please use a different one.', 'danger')
            return redirect(url_for('register'))

        # Check password confirmation
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        # Hash the password before storing
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Create a new user and store it in the database
        new_user = User(
            username=username,
            password=hashed_password,
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

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login route with password verification
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the user exists
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

# Book appointment route
@app.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone_number = request.form['phone_number']
        date_str = request.form['date']
        time_str = request.form['time']
        message = request.form['message']

        # Convert date and time strings to proper types
        try:
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time_str, '%H:%M').time()
        except ValueError as e:
            flash(f'Invalid date or time format: {e}. Please use the correct format.', 'danger')
            return redirect(url_for('book'))

        # Only allow Monday–Friday
        if appointment_date.weekday() >= 5:
            flash('Appointments are only available from Monday to Friday.', 'danger')
            return redirect(url_for('book'))

        # Only allow times from 9:00 AM to 5:00 PM
        if not (time(9, 0) <= appointment_time <= time(17, 0)):
            flash('Appointments are only available between 9:00 AM and 5:00 PM.', 'danger')
            return redirect(url_for('book'))

        # Save appointment
        new_appointment = Appointment(
            name=name,
            email=email,
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

    # GET request: send today’s date for min=date in form
    today = date.today().isoformat()
    return render_template('book.html', today=today)

# Confirmation route
@app.route('/confirmation')
def confirmation():
    return render_template('confirmation.html')

# Appointments route
@app.route('/appointments')
@login_required
def appointments():
    user_appointments = Appointments.query.filter_by(user_id=current_user.id).order_by(Appointments.date, Appointment.time).all()
    return render_template('appointments.html', appointments=user_appointments)

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



@app.route("/chatbot")
def chat():
    return render_template("chatbot.html")

# Chatbot API
@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.json
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI assistant trained to provide legal information based on the following text:"},
                {"role": "system", "content": law_text},
                {"role": "user", "content": user_message}
            ],
        )
        bot_reply = response.choices[0].message.content

        # Save the conversation to the database
        if current_user.is_authenticated:
            new_chat = ChatHistory(
                user_id=current_user.id,
                user_message=user_message,
                bot_reply=bot_reply
            )
            db.session.add(new_chat)
            db.session.commit()

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"}), 500

    return jsonify({"reply": bot_reply})

@app.route("/chatbot-history")
@login_required
def chat_history():
    user_chats = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp).all()
    chat_data = [{"user_message": chat.user_message, "bot_reply": chat.bot_reply} for chat in user_chats]
    return jsonify(chat_data)

@app.route("/clear-chat-history", methods=["POST"])
@login_required
def clear_chat_history():
    try:
        ChatHistory.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({"success": True, "message": "Chat history cleared successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists('instance/appointments.db'):  # Check if DB exists
            db.create_all()  # Create database if it doesn't exist
    app.run(debug=True)