# motorsmonitorapp.py
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from flask import Flask, request, jsonify, render_template, send_file, make_response, session, redirect, url_for
from functools import wraps
import logging
import datetime
import os

# --- Configuration ---
from config import SECRET_KEY, DATABASE_FILE, ADMIN_USERNAME, ADMIN_PASSWORD

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Configure logging
logging.basicConfig(filename=\'/tmp/app.log\', level=logging.INFO, format=\'%(asctime)s - %(levelname)s - %(message)s\')

# Motor Descriptions (Add your specific names here)
MOTOR_DESCRIPTIONS = {
    1: "Motor 1 Description...",
    2: "Motor 2 Description...",
    3: "Motor 3 Description...",
    4: "Motor 4 Description...",
    5: "Nano Pump 1 (Wet A.)",
    6: "Nano Pump 2 (Wet A.)",
    7: "Nano Pump 3 (Wet A.)",
    8: "Nano Stuffer Pump (Wet A.)",
    9: "Motor 9 Description...",
    10: "Motor 10 Description...",
    11: "Motor 11 Description...",
    12: "Motor 12 Description...",
    13: "Motor 13 Description...",
    14: "Motor 14 Description...",
    15: "Motor 15 Description...",
    16: "Motor 16 Description...",
    17: "Motor 17 Description...",
    18: "Motor 18 Description...",
    19: "Motor 19 Description...",
    20: "Motor 20 Description..."
}

# --- Database Functions ---
def get_db_connection():
    # Use isolation_level=None for autocommit on writes, simplifying transaction management
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Updated \'readings\' table
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motor_id INTEGER,
            read_timestamp DATETIME,  
            dominant_freq REAL,
            amplitude REAL,
            temp REAL
        )
    \'\'\')
    
    # \'motor_status\' table
    c.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS motor_status (
            motor_id INTEGER PRIMARY KEY,
            last_ping DATETIME,
            is_running BOOLEAN
        )
    \'\'\')
    
    # Check and add \'is_running\' column if it doesn\'t exist
    try:
        c.execute("SELECT is_running FROM motor_status LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE motor_status ADD COLUMN is_running BOOLEAN")
        
    logging.info("Initializing or updating status for all defined motors...")
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    
    for motor_id in MOTOR_DESCRIPTIONS.keys():
        c.execute(\'\'\'
            INSERT OR IGNORE INTO motor_status (motor_id, last_ping, is_running)
            VALUES (?, ?, ?)
        \'\'\', (motor_id, current_time, 0)) # 0 = Stopped/Unknown state initially
        
    conn.commit()
    conn.close()
    
# Ensure the database and its tables are created on startup
setup_database()


# --- Authentication ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if \'logged_in\' not in session:
            return redirect(url_for(\'login\', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route(\'/login\', methods=[\'GET\', \'POST\'])
def login():
    if request.method == \'POST\':
        if request.form[\'username\'] == ADMIN_USERNAME and request.form[\'password\'] == ADMIN_PASSWORD:
            session[\'logged_in\'] = True
            next_url = request.args.get(\'next\')
            return redirect(next_url or url_for(\'users\'))
        else:
            return \'Invalid Credentials. Please try again.\'
    return \'\'\'
        <form method="post">
            <p><input type=text name=username>
            <p><input type=password name=password>
            <p><input type=submit value=Login>
        </form>
    \'\'\'

@app.route(\'/logout\')
def logout():
    session.pop(\'logged_in\', None)
    return redirect(url_for(\'login\'))


# --- Compute Motor Health and Sensor Status ---
def compute_status(motor_id):
    if motor_id not in MOTOR_DESCRIPTIONS.keys():
        logging.warning(f"Invalid motor_id: {motor_id}")
        return "Invalid", "Invalid", "N/A"

    conn = get_db_connection()

    # Get the latest motor status from the new table
    status_row = pd.read_sql_query(
        "SELECT last_ping, is_running FROM motor_status WHERE motor_id = ?",
        conn, params=(motor_id,)
    )
    
    is_running_flag = "Unknown"
    sensor_status = "Offline"
    
    if not status_row.empty:
        last_ping_str = status_row[\'last_ping\'].iloc[0]
        is_running_flag = "Running" if status_row[\'is_running\'].iloc[0] == 1 else "Stopped"
        
        try:
            try:
                last_ping_time = datetime.datetime.strptime(last_ping_str, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                last_ping_time = datetime.datetime.strptime(last_ping_str, "%Y-%m-%d %H:%M:%S")
                
            time_diff = (datetime.datetime.now() - last_ping_time).total_seconds()
            if time_diff < 60: # 1 minute timeout for \'online\' status
                sensor_status = "Online"
        except ValueError:
            logging.error(f"Error parsing last_ping timestamp for motor_id {motor_id}")
            sensor_status = "Unknown"

    # Now get the latest readings for motor health check
    latest_readings = pd.read_sql_query(
        "SELECT temp, dominant_freq, amplitude FROM readings WHERE motor_id = ? ORDER BY read_timestamp DESC LIMIT 1",
        conn, params=(motor_id,)
    )
    conn.close()

    motor_health = "No Data"
    
    if sensor_status == "Offline":
        motor_health = "Offline" 
    elif not status_row.empty and not status_row[\'is_running\'].iloc[0] == 1:
        motor_health = "Off / Healthy" # Healthy when stopped
    elif latest_readings.empty:
        motor_health = "No Sensor Data"
    else:
        temp = latest_readings[\'temp\'].iloc[0]
        amplitude = latest_readings[\'amplitude\'].iloc[0]
        
        if amplitude > 35 or temp > 50:
            motor_health = "Critical 🔴"
        elif amplitude > 28 or temp > 45:
            motor_health = "Warning 🟠"
        elif amplitude > 24 or temp > 38:
            motor_health = "Concern 🟡"
        else:
            motor_health = "Healthy 🟢"
    
    return motor_health, sensor_status, is_running_flag

# --- Receive Data from ESP32 ---
@app.route(\'/data\', methods=[\'POST\'])
def receive_data():
    if not request.is_json:
        logging.error("Request is not JSON")
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    
    required_fields = [\'motor_id\', \'timestamp\', \'dominant_freq\', \'amplitude\', \'temp\', \'is_running\']
    if any(field not in data for field in required_fields):
        logging.error(f"Invalid data received, missing fields: {data}")
        return jsonify({"error": "Missing required data fields (motor_id, timestamp, dominant_freq, amplitude, temp, is_running)"}), 400
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute(\'\'\'
            INSERT INTO readings (motor_id, read_timestamp, dominant_freq, amplitude, temp)
            VALUES (?, ?, ?, ?, ?)\
        \'\'\', (data[\'motor_id\'], data[\'timestamp\'], data[\'dominant_freq\'], data[\'amplitude\'], data[\'temp\']))
        
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        c.execute(\'\'\'
            INSERT INTO motor_status (motor_id, last_ping, is_running)
            VALUES (?, ?, ?)\
            ON CONFLICT(motor_id) DO UPDATE SET last_ping=excluded.last_ping, is_running=excluded.is_running
        \'\'\', (data[\'motor_id\'], current_time, data[\'is_running\']))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Received data for Motor {data[\'motor_id\']}: Freq={data[\'dominant_freq\']:.2f}Hz, Amp={data[\'amplitude\']:.2f}g, Temp={data[\'temp\']:.1f}°C, Running={data[\'is_running\']}")
        return jsonify({"message": "Data received successfully!"}), 200
    except Exception as e:
        logging.error(f"Error logging data: {e}")
        return jsonify({"error": "Failed to log data"}), 500

# ----------------------------------------------------
# --- API ROUTES FOR AJAX REFRESH ---
# ----------------------------------------------------

def get_motor_data(motor_id, limit=10):
    conn = get_db_connection()
    df = pd.read_sql_query(
        f"SELECT read_timestamp, dominant_freq, amplitude, temp FROM readings WHERE motor_id = ? ORDER BY read_timestamp DESC LIMIT {limit}",
        conn, params=(motor_id,)
    )
    conn.close()
    return df

def generate_graph(df, y_col, title, y_axis_title):
    fig = go.Figure()
    if not df.empty and y_col in df.columns and df[y_col].notna().any():
        df_graph = df.iloc[::-1]
        df_graph[\'read_timestamp\'] = pd.to_datetime(df_graph[\'read_timestamp\']).dt.strftime(\'%Y-%m-%dT%H:%M:%S\')
        fig.add_trace(go.Scatter(x=df_graph[\'read_timestamp\'], y=df_graph[y_col].fillna(0), mode=\'lines\'))
    
    fig.update_layout(
        title=title,
        xaxis_title=\'Time\',
        yaxis_title=y_axis_title,
        xaxis=dict(type=\'date\', tickformat=\'%m-%d<br>%H:%M:%S\')
    )
    return fig

@app.route(\'/api/motors\')
@login_required
def api_motors():
    motors = []
    for motor_id in range(1, 21): 
        latest = get_motor_data(motor_id, limit=1)
        motor_health, sensor_status, is_running_flag = compute_status(motor_id)
        
        temp = None if latest.empty else latest[\'temp\'].iloc[0]
        last_timestamp = None if latest.empty else latest[\'read_timestamp\'].iloc[0]
        dominant_freq = None if latest.empty else latest[\'dominant_freq\'].iloc[0]
        amplitude = None if latest.empty else latest[\'amplitude\'].iloc[0]
        
        motors.append({
            \'id\': motor_id,
            \'description\': MOTOR_DESCRIPTIONS.get(motor_id, f"Motor ID {motor_id}"),
            \'temp\': f"{temp:.1f}°C" if temp is not None else \'N/A\',
            \'dominant_freq\': f"{dominant_freq:.2f}Hz" if dominant_freq is not None else \'N/A\',
            \'amplitude\': f"{amplitude:.2f}g" if amplitude is not None else \'N/A\',
            \'motor_health\': motor_health,
            \'sensor_status\': sensor_status,
            \'is_running\': is_running_flag,
            \'last_timestamp\': last_timestamp
        })
    
    response = jsonify(motors)
    
    response.headers[\'Cache-Control\'] = \'no-store, no-cache, must-revalidate, max-age=0\'
    response.headers[\'Pragma\'] = \'no-cache\'
    response.headers[\'Expires\'] = \'0\'
    return response

@app.route(\'/api/motor/<int:motor_id>\')
@login_required
def api_motor_dashboard(motor_id):
    if motor_id not in MOTOR_DESCRIPTIONS.keys():
        return jsonify({"error": "Invalid motor_id"}), 400
    
    df_table = get_motor_data(motor_id, limit=10)
    df_graph = get_motor_data(motor_id, limit=500)
    latest = get_motor_data(motor_id, limit=1)

    motor_health, sensor_status, is_running_flag = compute_status(motor_id)
    
    last_timestamp = None if latest.empty else latest[\'read_timestamp\'].iloc[0]
    temp = None if latest.empty else latest[\'temp\'].iloc[0]
    dominant_freq = None if latest.empty else latest[\'dominant_freq\'].iloc[0]
    amplitude = None if latest.empty else latest[\'amplitude\'].iloc[0]

    fig_vib = generate_graph(df_graph, \'amplitude\', \'Vibration Amplitude (g) Trend\', \'Amplitude (g)\')
    fig_temp = generate_graph(df_graph, \'temp\', \'Temperature (°C) Trend\', \'Temperature (°C)\')
    
    response_data = {
        \'motor\': {
            \'id\': motor_id,
            \'description\': MOTOR_DESCRIPTIONS.get(motor_id, f"Unknown Motor ID {motor_id}"),
            \'motor_health\': motor_health,
            \'sensor_status\': sensor_status,
            \'is_running_flag\': is_running_flag,
            \'last_timestamp\': last_timestamp,
            \'temp\': f"{temp:.1f}°C" if temp is not None else \'N/A\',
            \'dominant_freq\': f"{dominant_freq:.2f}Hz" if dominant_freq is not None else \'N/A\',
            \'amplitude\': f"{amplitude:.2f}g" if amplitude is not None else \'N/A\', 
        },
        \'data\': df_table.to_dict(\'records\'),
        \'graph_vib_json\': fig_vib.to_json(),
        \'graph_temp_json\': fig_temp.to_json()
    }
    
    response = jsonify(response_data)
    
    response.headers[\'Cache-Control\'] = \'no-store, no-cache, must-revalidate, max-age=0\'
    response.headers[\'Pragma\'] = \'no-cache\'
    response.headers[\'Expires\'] = \'0\'
    return response

# ----------------------------------------------------
# --- WEB ROUTES ---
# ----------------------------------------------------
@app.route(\'/\')
@login_required
def users():
    users = [\'MMaUser1\', \'MMaUser2\', \'MMaUser3\']
    return render_template(\'users.html\', users=users)

@app.route(\'/motors\')
@login_required
def index():
    response = render_template(\'motor_overview.html\')
    response = app.make_response(response)
    response.headers[\'Cache-Control\'] = \'no-store, no-cache, must-revalidate, max-age=0\'
    response.headers[\'Pragma\'] = \'no-cache\'
    response.headers[\'Expires\'] = \'0\'
    return response

@app.route(\'/motor/<int:motor_id>\')
@login_required
def dashboard(motor_id):
    if motor_id not in MOTOR_DESCRIPTIONS.keys():
        return jsonify({"error": "Invalid motor_id"}), 400
    
    df_table = get_motor_data(motor_id, limit=10)
    df_graph = get_motor_data(motor_id, limit=500)
    latest = get_motor_data(motor_id, limit=1)
    
    motor_health, sensor_status, is_running_flag = compute_status(motor_id)
    
    last_timestamp = None if latest.empty else latest[\'read_timestamp\'].iloc[0]

    fig_vib = generate_graph(df_graph, \'amplitude\', \'Vibration Amplitude (g) Trend\', \'Amplitude (g)\')
    fig_temp = generate_graph(df_graph, \'temp\', \'Temperature (°C) Trend\', \'Temperature (°C)\')

    response = render_template(
        \'dashboard.html\',
        graph_vib_json=fig_vib.to_json(),
        graph_temp_json=fig_temp.to_json(),
        data=df_table.to_dict(\'records\'),
        motor_id=motor_id,
        motor_description=MOTOR_DESCRIPTIONS.get(motor_id, f"Unknown Motor ID {motor_id}"),
        motor_health=motor_health,
        sensor_status=sensor_status,
        is_running_flag=is_running_flag,
        last_timestamp=last_timestamp
    )
    response = app.make_response(response)
    response.headers[\'Cache-control\'] = \'no-store, no-cache, must-revalidate, max-age=0\'
    response.headers[\'Pragma\'] = \'no-cache\'
    response.headers[\'Expires\'] = \'0\'
    return response

# --- Other API Routes ---
@app.route(\'/download\')
@login_required
def download_data():
    motor_id = request.args.get(\'motor_id\', type=int)
    if not motor_id or motor_id not in MOTOR_DESCRIPTIONS.keys():
        return jsonify({"error": "Invalid motor_id"}), 400
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM readings WHERE motor_id = ?", conn, params=(motor_id,))
    conn.close()

    csv_filename = f"/tmp/motor_{motor_id}_log.csv"
    df.to_csv(csv_filename, index=False)
    
    return send_file(csv_filename, as_attachment=True, download_name=f\'motor_{motor_id}_log.csv\')

@app.route(\'/reset\', methods=[\'POST\', \'GET\'])
@login_required
def reset_data():
    motor_id = request.args.get(\'motor_id\', type=int)
    if not motor_id or motor_id not in MOTOR_DESCRIPTIONS.keys():
        return jsonify({"error": "Invalid motor_id"}), 400
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("DELETE FROM readings WHERE motor_id = ?", (motor_id,))
        c.execute("DELETE FROM motor_status WHERE motor_id = ?", (motor_id,))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Database readings and status for Motor {motor_id} reset successfully.")
        return jsonify({"message": f"Data for Motor {motor_id} has been reset."}), 200
    except Exception as e:
        logging.error(f"Error resetting data for Motor {motor_id}: {e}")
        return jsonify({"error": "Failed to reset data."}), 500

if __name__ == \'__main__\':
    port = int(os.environ.get(\'PORT\', 8080))
    app.run(host=\'0.0.0.0\', port=port)
