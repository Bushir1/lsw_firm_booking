from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, time
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import fitz  # PyMuPDF
import openai

app = Flask(__name__)
CORS(app)  # Allow frontend to access this backend

app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///appointments.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Define the User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # Storing hashed password
    appointments = db.relationship('Appointment', backref='user', lazy=True)

class Query(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Define the Appointment model
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    message = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Load a user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Home route with user greeting
@app.route('/')
def home():
    return render_template('home.html', user=current_user if current_user.is_authenticated else None)

# Registration route with password hashing
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('register'))

        # Hash password before storing
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
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
        date_str = request.form['date']
        time_str = request.form['time']
        message = request.form['message']

        # Convert date and time strings to appropriate types
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            flash('Invalid date or time format. Please use the correct format.', 'danger')
            return redirect(url_for('book'))

        # Validate day of the week (Monday to Friday)
        if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            flash('Appointments are only available from Monday to Friday.', 'danger')
            return redirect(url_for('book'))

        # Validate time (9:00 AM to 5:00 PM)
        start_time = time(9, 0)  # 9:00 AM
        end_time = time(17, 0)   # 5:00 PM
        if appointment_time < start_time or appointment_time > end_time:
            flash('Appointments are only available between 9:00 AM and 5:00 PM.', 'danger')
            return redirect(url_for('book'))

        # Save to database
        new_appointment = Appointment(
            name=name,
            email=email,
            date=date,
            time=appointment_time,
            message=message,
            user_id=current_user.id  # Associate appointment with the current user
        )
        db.session.add(new_appointment)
        db.session.commit()
        flash('Appointment booked successfully!', 'success')
        return redirect(url_for('confirmation'))

    return render_template('book.html')

# Confirmation route
@app.route('/confirmation')
def confirmation():
    return render_template('confirmation.html')

# Appointments route
@app.route('/appointments')
@login_required
def appointments():
    user_appointments = Appointment.query.filter_by(user_id=current_user.id).order_by(Appointment.date, Appointment.time).all()
    return render_template('appointments.html', appointments=user_appointments)

# Chatbot route
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if request.method == 'POST':
        user_message = request.json.get('message', '')

        # Query OpenAI with PDF content as context
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a chatbot that only answers questions based on the provided legal document."},
                {"role": "user", "content": f"Here is the legal document excerpt: {pdf_text[:3000]}..."},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response['choices'][0]['message']['content']
        return jsonify({"reply": reply})

    return render_template('chatbot.html')

# Load PDF and extract text
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text("text") + "\n"
    return text

# Load extracted PDF content from "LAW.pdf"
pdf_text = extract_text_from_pdf("LAW.pdf")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Ensure database is created
    app.run(debug=True)