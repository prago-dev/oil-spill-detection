import os
from dotenv import load_dotenv

load_dotenv()

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import os
from model.detect import OilSpillDetector


app = Flask(__name__)

# Email Configuration 
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")         # yaha admin ka email
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
#secret key
app.secret_key = os.getenv("SECRET_KEY")

#Mysql Connection
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'root'
app.config['MYSQL_DB'] = 'oil_spilling'

# File upload configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

mysql = MySQL(app)


# ------------------MODEL-----------------------------#
MODEL_PATH = "model/oil_spilling_model.pt"
app.config['PREDICT_FOLDER'] = "static/predictions"

oil_spill_detector = OilSpillDetector(
    model_path=MODEL_PATH,
    conf=0.3
)

def send_prediction_email(result, confidence, username):
    try:
        subject = "Oil Spill Detection Alert"

        body = f"""
Prediction Result

User: {username}

Result: {result}

Confidence: {round(confidence * 100, 2)}%
"""

        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = ADMIN_EMAIL
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, ADMIN_EMAIL, msg.as_string())
        server.quit()

    except Exception as e:
        print("Email send error:", e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Basic field validation
        if not username or not password:
            return render_template('login.html', error='Username and password are required.')

        # Authenticate user against the database
        try:
            cur = mysql.connection.cursor()
            cur.execute(
                "SELECT id, name, mobile, email, city, username, address FROM users WHERE username = %s AND password = %s",
                (username, password),
            )
            user = cur.fetchone()
            cur.close()
        except Exception:
            return render_template('login.html', error='Database error during login.')

        if not user:
            return render_template('login.html', error='Invalid username or password.')

        # Successful login
        session['role'] = 'user'
        session['user_id'] = user[0]
        session['username'] = user[5]
        return redirect(url_for('user_dashboard'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        email = request.form['email']
        city = request.form['city']
        username = request.form['username']
        address = request.form['address']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Basic validation
        if not name or not email or not password or not confirm_password:
            return render_template(
                'register.html',
                error='Name, email and password fields are required.'
            )

        if password != confirm_password:
            return render_template(
                'register.html',
                error='Passwords do not match.'
            )

        sql_query = """
            INSERT INTO users
            (name, mobile, email, city, username, address, password)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        sql_params = (name, mobile, email, city, username, address, password)

        try:
            cur = mysql.connection.cursor()
            cur.execute(sql_query, sql_params)
            mysql.connection.commit()
            cur.close()
        except Exception as e:
            print("Database error:", e)
            return render_template(
                'register.html',
                error='Database error occurred. Please try again.'
            )

        return redirect(url_for('login'))

    return render_template('register.html')



@app.route('/admin')
def admin():
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if username == 'admin' and password == 'super':
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))

        return render_template('admin/login.html', error='Invalid admin credentials')

    return render_template('admin/login.html')


@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    total_users = 0
    predictions_24h = 0
    recent_users = []
    try:
        cur = mysql.connection.cursor()

        # Total users count
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]

        # Predictions in last 24 hours (requires created_at column)
        cur.execute(
            "SELECT COUNT(*) FROM predictions WHERE created_at >= NOW() - INTERVAL 1 DAY"
        )
        predictions_24h = cur.fetchone()[0]

        # Recent users (last 5)
        cur.execute(
            "SELECT id, name, email, city, username FROM users ORDER BY id DESC LIMIT 5"
        )
        rows = cur.fetchall()
        cur.close()

        for row in rows:
            recent_users.append(
                {
                    'id': row[0],
                    'name': row[1],
                    'email': row[2],
                    'city': row[3],
                    'username': row[4],
                }
            )
    except Exception as e:
        print('Admin dashboard stats load error:', e)

    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        predictions_24h=predictions_24h,
        recent_users=recent_users,
    )


@app.route('/admin/history')
def admin_history():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    predictions = []
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, user_id, username, file_path, created_at FROM predictions ORDER BY id ASC"
        )
        rows = cur.fetchall()
        cur.close()

        for row in rows:
            predictions.append({
                'id': row[0],
                'user_id': row[1],
                'username': row[2],
                'file_path': row[3],
                'created_at': row[4],
            })
    except Exception as e:
        print('Admin history load error:', e)

    return render_template('admin/history.html', predictions=predictions)


@app.route('/admin/users')
def admin_user_list():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    users = []
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT id, name, mobile, email, city, username FROM users ORDER BY id ASC"
        )
        rows = cur.fetchall()
        cur.close()

        for row in rows:
            users.append({
                'id': row[0],
                'name': row[1],
                'mobile': row[2],
                'email': row[3],
                'city': row[4],
                'username': row[5],
            })
    except Exception as e:
        print("Admin user list error:", e)

    return render_template('admin/user_list.html', users=users)


@app.route('/user/dashboard')
def user_dashboard():
    if session.get('role') != 'user':
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    total_predictions = 0
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM predictions WHERE user_id = %s",
            (user_id,),
        )
        total_predictions = cur.fetchone()[0]
        cur.close()
    except Exception as e:
        print('User dashboard stats load error:', e)

    return render_template('user/dashboard.html', total_predictions=total_predictions)


@app.route('/user/history')
def user_history():
    if session.get('role') != 'user':
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    predictions = []

    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT 
                id,
                file_path,
                output_image,
                result,
                confidence,
                created_at
            FROM predictions
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        )

        rows = cur.fetchall()
        cur.close()

        for row in rows:
            predictions.append({
                'id': row[0],
                'file_path': row[1],
                'output_image': row[2],
                'result': row[3],
                'confidence': row[4],
                'created_at': row[5],
            })

    except Exception as e:
        print('User history load error:', e)

    return render_template('user/history.html', predictions=predictions)



@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    if session.get('role') != 'user':
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    username = session.get('username')
    if not user_id or not username:
        return redirect(url_for('login'))

    # Handle profile update
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        email = request.form['email']
        city = request.form['city']
        username = request.form['username']
        address = request.form['address']

        try:
            cur = mysql.connection.cursor()
            cur.execute(
                """
                UPDATE users
                SET name = %s,
                    mobile = %s,
                    email = %s,
                    city = %s,
                    username = %s,
                    address = %s
                WHERE id = %s
                """,
                (name, mobile, email, city, username, address, user_id)
            )
            mysql.connection.commit()
            cur.close()
            flash('Profile updated successfully.', 'success')
        except Exception as e:
            print("Profile update error:", e)
            flash('Failed to update profile.', 'danger')

        return redirect(url_for('user_profile'))

    # Load current user profile data
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT name, mobile, email, city, username, address FROM users WHERE id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        cur.close()
    except Exception as e:
        print("Profile fetch error:", e)
        row = None

    if not row:
        return render_template('user/profile.html', user=None)

    user = {
        'name': row[0],
        'mobile': row[1],
        'email': row[2],
        'city': row[3],
        'username': row[4],
        'address': row[5],
    }

    return render_template('user/profile.html', user=user)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/user/new_prediction')
def new_prediction():
    if session.get('role') != 'user':
        return redirect(url_for('login'))

    return render_template('user/new_prediction.html')



@app.route('/predict', methods=['POST'])
def predict():
    if session.get('role') != 'user':
        return redirect(url_for('login'))

    file = request.files.get('data_file')
    if not file or file.filename == '':
        flash('Please select a file.', 'danger')
        return redirect(url_for('new_prediction'))

    filename = secure_filename(file.filename)
    upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(upload_path)

    # 🔥 YOLO prediction
    detected, confidence, output_filename = oil_spill_detector.predict(
        upload_path,
        app.config['PREDICT_FOLDER']
    )
    result_text = "Oil Spill Detected" if detected else "No Oil Spill"
    cur = mysql.connection.cursor()
    cur.execute(
        """
        INSERT INTO predictions
        (user_id, username, file_path, result, confidence, output_image)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            session['user_id'],
            session['username'],
            filename,
            "Oil Spill Detected" if detected else "No Oil Spill",
            confidence,
            output_filename
        )
    )
    mysql.connection.commit()
    cur.close()
    # Send email to admin
    send_prediction_email(result_text, confidence, session['username'])

    flash('Prediction completed successfully!', 'success')
    
    return render_template('user/new_prediction.html',prediction_result=result_text,confidence=confidence,output_image=output_filename)



# @app.route('/predict', methods=['POST'])
# def predict():
#     # Ensure a user is logged in
#     if session.get('role') != 'user':
#         return redirect(url_for('login'))

#     user_id = session.get('user_id')
#     username = session.get('username')
#     if not user_id or not username:
#         return redirect(url_for('login'))

#     # Validate file presence
#     file = request.files.get('data_file')
#     if file is None or file.filename == '':
#         flash('Please select a file to upload.', 'danger')
#         return redirect(url_for('new_prediction'))

#     # Secure and save file
#     filename = secure_filename(file.filename)
#     save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#     try:
#         file.save(save_path)
#     except Exception as e:
#         print('File save error:', e)
#         flash('Failed to save uploaded file.', 'danger')
#         return redirect(url_for('new_prediction'))

#     # Insert prediction record into database
#     try:
#         cur = mysql.connection.cursor()
#         cur.execute(
#             """
#             INSERT INTO predictions (user_id, username, file_path)
#             VALUES (%s, %s, %s)
#             """,
#             (user_id, username, filename),
#         )
#         mysql.connection.commit()
#         cur.close()
#     except Exception as e:
#         print('Prediction DB insert error:', e)
#         flash('Failed to store prediction in database.', 'danger')
#         return redirect(url_for('new_prediction'))

#     flash('Prediction uploaded and stored successfully.', 'success')
#     return redirect(url_for('user_history'))


if __name__ == '__main__':
    app.run(debug=True)
