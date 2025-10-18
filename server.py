from flask import Flask, request, jsonify, send_from_directory, render_template_string, session, redirect, url_for, flash
import os
import json
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import shutil
import sqlite3
from functools import wraps
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration - Updated for production
UPLOAD_FOLDER = 'downloads'
DATA_FOLDER = 'data'
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')  # Use environment variable
ALLOWED_EXTENSIONS = {'zip'}
DB_FILE = os.path.join(DATA_FOLDER, 'users.db')

# Flask app configuration - Updated for production
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024 * 1024))  # 5GB default
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')  # Use environment variable

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

def init_database():
    """Initialize the user database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_admin BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Create default admin user if no users exist
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        default_password = generate_password_hash('admin123')
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                      ('admin', default_password))
        print("🔑 Default admin user created: admin/admin123")
    
    conn.commit()
    conn.close()

def login_required(f):
    """Decorator to require login for admin routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def authenticate_user(username, password):
    """Authenticate user credentials"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user[1], password):
        return user[0]  # Return user ID
    return None

def get_all_users():
    """Get all users from database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, username, created_at FROM users ORDER BY username')
    users = cursor.fetchall()
    conn.close()
    
    return users

def create_user(username, password):
    """Create a new user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        password_hash = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                      (username, password_hash))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False  # Username already exists

def delete_user(user_id):
    """Delete a user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Don't allow deleting the last admin user
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0]
    
    if user_count <= 1:
        conn.close()
        return False  # Can't delete last user
    
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_versions():
    """Load all versions from the JSON file"""
    versions_file = os.path.join(DATA_FOLDER, 'versions.json')
    if not os.path.exists(versions_file):
        return []
    
    try:
        with open(versions_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_versions(versions):
    """Save all versions to the JSON file"""
    versions_file = os.path.join(DATA_FOLDER, 'versions.json')
    with open(versions_file, 'w') as f:
        json.dump(versions, f, indent=2)

def get_active_version():
    """Get the currently active version"""
    versions = load_versions()
    for version in versions:
        if version.get('is_active', False):
            return version
    return None

def get_active_launcher_version():
    """Get the currently active launcher version"""
    launcher_versions = load_launcher_versions()
    for version in launcher_versions:
        if version.get('is_active', False):
            return version
    return None

def load_launcher_versions():
    """Load all launcher versions from the JSON file"""
    launcher_file = os.path.join(DATA_FOLDER, 'launcher_versions.json')
    if not os.path.exists(launcher_file):
        return []
    
    try:
        with open(launcher_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_launcher_versions(versions):
    """Save all launcher versions to the JSON file"""
    launcher_file = os.path.join(DATA_FOLDER, 'launcher_versions.json')
    with open(launcher_file, 'w') as f:
        json.dump(versions, f, indent=2)

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} bytes"

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_id = authenticate_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('admin_interface'))
        else:
            flash('Invalid username or password', 'error')
    
    login_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 300px; }
        .login-container h1 { text-align: center; margin-bottom: 30px; color: #333; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; color: #555; }
        .form-group input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px; box-sizing: border-box; }
        .btn { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; margin-top: 10px; }
        .btn:hover { background: #0056b3; }
        .alert { padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .alert-success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .alert-error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>🔐 Admin Login</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST">
            <div class="form-group">
                <label>Username:</label>
                <input type="text" name="username" required>
            </div>
            
            <div class="form-group">
                <label>Password:</label>
                <input type="password" name="password" required>
            </div>
            
            <button type="submit" class="btn">Login</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
            NerdsCorp 2025
        </div>
    </div>
</body>
</html>
    '''
    
    return render_template_string(login_html)

@app.route('/logout')
@login_required
def logout():
    """Logout route"""
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/admin/users')
@login_required
def manage_users():
    """User management page"""
    users = get_all_users()
    
    user_management_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>User Management</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 800px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn:hover { opacity: 0.8; }
        .user-form { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        .users-table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .users-table th, .users-table td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .users-table th { background: #f8f9fa; font-weight: bold; }
        .alert { padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .alert-success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .alert-error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👥 User Management</h1>
            <div>
                <a href="{{ url_for('admin_interface') }}" class="btn btn-primary">← Back to Admin</a>
                <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="user-form">
            <h3>➕ Add New User</h3>
            <form method="POST" action="{{ url_for('create_user_route') }}">
                <div class="form-group">
                    <label>Username:</label>
                    <input type="text" name="username" required>
                </div>
                
                <div class="form-group">
                    <label>Password:</label>
                    <input type="password" name="password" required minlength="6">
                </div>
                
                <button type="submit" class="btn btn-success">Add User</button>
            </form>
        </div>
        
        <h3>👤 Existing Users</h3>
        <table class="users-table">
            <thead>
                <tr>
                    <th>Username</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ user[1] }}</td>
                    <td>{{ user[2] }}</td>
                    <td>
                        {% if users|length > 1 %}
                            <a href="{{ url_for('delete_user_route', user_id=user[0]) }}" 
                               class="btn btn-danger" 
                               onclick="return confirm('Delete user {{ user[1] }}?')">🗑️ Delete</a>
                        {% else %}
                            <span style="color: #666;">Cannot delete last user</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
    '''
    
    return render_template_string(user_management_html, users=users)

@app.route('/admin/users/create', methods=['POST'])
@login_required
def create_user_route():
    """Create user route"""
    username = request.form['username'].strip()
    password = request.form['password']
    
    if len(username) < 3:
        flash('Username must be at least 3 characters long', 'error')
    elif len(password) < 6:
        flash('Password must be at least 6 characters long', 'error')
    elif create_user(username, password):
        flash(f'User "{username}" created successfully!', 'success')
    else:
        flash('Username already exists', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/admin/users/delete/<int:user_id>')
@login_required
def delete_user_route(user_id):
    """Delete user route"""
    if delete_user(user_id):
        flash('User deleted successfully!', 'success')
    else:
        flash('Cannot delete user', 'error')
    
    return redirect(url_for('manage_users'))

# Public launcher download page
@app.route('/')
def launcher_download():
    """Public launcher download page"""
    try:
        launcher_version = get_active_launcher_version()
    except:
        launcher_version = None
    
    download_page_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download Game Launcher - EpicQuest</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0c0c0c 0%, #1a1a2e 50%, #16213e 100%);
            color: #ffffff;
            overflow-x: hidden;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }

        /* Header */
        header {
            position: fixed;
            top: 0;
            width: 100%;
            background: rgba(0, 0, 0, 0.9);
            backdrop-filter: blur(10px);
            z-index: 1000;
            padding: 15px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(45deg, #ff6b6b, #4ecdc4, #45b7d1);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: glow 2s ease-in-out infinite alternate;
        }

        .admin-link {
            color: rgba(255, 255, 255, 0.7);
            text-decoration: none;
            font-size: 14px;
            transition: color 0.3s ease;
        }

        .admin-link:hover {
            color: #4ecdc4;
        }

        /* Hero Section */
        .hero {
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            position: relative;
            background: radial-gradient(ellipse at center, rgba(78, 205, 196, 0.1) 0%, transparent 50%);
        }

        .hero-content h1 {
            font-size: 4rem;
            margin-bottom: 20px;
            background: linear-gradient(45deg, #ff6b6b, #4ecdc4, #45b7d1, #96ceb4);
            background-size: 400% 400%;
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradientShift 3s ease-in-out infinite;
        }

        .hero-content p {
            font-size: 1.2rem;
            margin-bottom: 40px;
            opacity: 0.9;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }

        .download-section {
            background: rgba(255, 255, 255, 0.05);
            padding: 40px;
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            margin-top: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }

        .download-section h2 {
            color: #4ecdc4;
            margin-bottom: 20px;
            font-size: 2rem;
        }

        .version-info {
            background: rgba(78, 205, 196, 0.1);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid rgba(78, 205, 196, 0.3);
            margin: 20px 0;
            text-align: left;
        }

        .version-info strong {
            color: #4ecdc4;
        }

        .release-notes {
            margin: 20px 0;
            padding: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: left;
        }

        .release-notes h4 {
            color: #ff6b6b;
            margin-bottom: 10px;
        }

        .download-btn {
            background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
            color: white;
            padding: 15px 40px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            margin: 20px 10px;
            text-decoration: none;
            display: inline-block;
            position: relative;
            overflow: hidden;
        }

        .download-btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
            transition: left 0.5s;
        }

        .download-btn:hover::before {
            left: 100%;
        }

        .download-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(78, 205, 196, 0.4);
        }

        .download-btn:disabled {
            background: linear-gradient(45deg, #6c757d, #5a6268);
            cursor: not-allowed;
            opacity: 0.6;
        }

        .download-btn:disabled:hover {
            transform: none;
            box-shadow: none;
        }

        .download-btn:disabled::before {
            display: none;
        }

        /* Features Section */
        .features {
            padding: 80px 0;
            background: rgba(0, 0, 0, 0.2);
        }

        .features h2 {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 50px;
            color: #4ecdc4;
        }

        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 30px;
        }

        .feature-card {
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.05));
            padding: 30px;
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .feature-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 20px 40px rgba(78, 205, 196, 0.2);
        }

        .feature-icon {
            font-size: 3rem;
            margin-bottom: 20px;
            color: #4ecdc4;
        }

        .feature-card h3 {
            font-size: 1.5rem;
            margin-bottom: 15px;
            color: #ffffff;
        }

        .feature-card p {
            opacity: 0.8;
            line-height: 1.6;
        }

        /* Floating particles */
        .particle {
            position: absolute;
            background: rgba(78, 205, 196, 0.3);
            border-radius: 50%;
            pointer-events: none;
            animation: float 6s ease-in-out infinite;
        }

        /* Animations */
        @keyframes glow {
            from { text-shadow: 0 0 10px rgba(78, 205, 196, 0.5); }
            to { text-shadow: 0 0 20px rgba(78, 205, 196, 0.8), 0 0 30px rgba(78, 205, 196, 0.4); }
        }

        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-20px); }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .hero-content h1 {
                font-size: 2.5rem;
            }
            
            .download-btn {
                padding: 12px 30px;
                font-size: 1rem;
            }

            .download-section {
                padding: 30px 20px;
            }
        }
    </style>
</head>
<body>
    <header>
        <nav class="container">
            <div class="logo">EpicQuest</div>
            <a href="{{ url_for('login') }}" class="admin-link">🔐 Admin</a>
        </nav>
    </header>

    <main>
        <section class="hero">
            <div class="container">
                <div class="hero-content">
                    <h1>🎮 Game Launcher</h1>
                    <p>Download and install our official game launcher to get started with automatic updates and seamless gameplay experience!</p>
                    
                    <div class="download-section">
                        <h2>🔥 Download Launcher</h2>
                        
                        {% if launcher_version %}
                        <div class="version-info">
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; text-align: center;">
                                <div>
                                    <strong>Version:</strong><br>
                                    v{{ launcher_version['version'] }}
                                </div>
                                <div>
                                    <strong>Size:</strong><br>
                                    {{ (launcher_version['file_size'] / (1024*1024)) | round(1) }} MB
                                </div>
                                <div>
                                    <strong>Released:</strong><br>
                                    {{ launcher_version['release_date'][:10] }}
                                </div>
                            </div>
                        </div>
                        
                        {% if launcher_version['release_notes'] %}
                        <div class="release-notes">
                            <h4>📝 What's New:</h4>
                            <p style="margin: 0; white-space: pre-line;">{{ launcher_version['release_notes'] }}</p>
                        </div>
                        {% endif %}
                        
                        <a href="{{ url_for('download_file', filename=launcher_version['download_url']) }}" 
                           class="download-btn">⬇️ Download Launcher</a>
                        {% else %}
                        <div style="background: rgba(255, 107, 107, 0.1); padding: 30px; border-radius: 15px; border: 1px solid rgba(255, 107, 107, 0.3); margin: 20px 0;">
                            <div style="font-size: 3rem; margin-bottom: 15px;">🚧</div>
                            <h3 style="color: #ff6b6b; margin-bottom: 15px;">No launcher version available yet</h3>
                            <p style="opacity: 0.8;">Please check back later or contact support for more information.</p>
                            <button class="download-btn" disabled>⬇️ Download Not Available</button>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </section>

        <section class="features">
            <div class="container">
                <h2>Launcher Features</h2>
                <div class="features-grid">
                    <div class="feature-card">
                        <div class="feature-icon">🔄</div>
                        <h3>Auto-Updates</h3>
                        <p>The launcher automatically checks for and installs game updates, so you're always playing the latest version with all the newest features and improvements.</p>
                    </div>
                    
                    <div class="feature-card">
                        <div class="feature-icon">📊</div>
                        <h3>Progress Tracking</h3>
                        <p>See detailed download progress and installation status with real-time updates, so you always know exactly what's happening.</p>
                    </div>
                    
                    <div class="feature-card">
                        <div class="feature-icon">🛡️</div>
                        <h3>Safe & Secure</h3>
                        <p>Automatic backups before updates and secure file verification ensure your game files are safe and your progress is never lost.</p>
                    </div>
                    
                    <div class="feature-card">
                        <div class="feature-icon">⚡</div>
                        <h3>Fast & Reliable</h3>
                        <p>Optimized download speeds and robust error handling provide a smooth, uninterrupted gaming experience every time.</p>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <script>
        // Create floating particles
        function createParticles() {
            const hero = document.querySelector('.hero');
            for (let i = 0; i < 15; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                particle.style.left = Math.random() * 100 + '%';
                particle.style.top = Math.random() * 100 + '%';
                particle.style.width = Math.random() * 4 + 2 + 'px';
                particle.style.height = particle.style.width;
                particle.style.animationDelay = Math.random() * 6 + 's';
                particle.style.animationDuration = (Math.random() * 4 + 4) + 's';
                hero.appendChild(particle);
            }
        }

        // Initialize particles when page loads
        window.addEventListener('load', createParticles);

        // Add scroll effect to header
        window.addEventListener('scroll', () => {
            const header = document.querySelector('header');
            if (window.scrollY > 100) {
                header.style.background = 'rgba(0, 0, 0, 0.95)';
            } else {
                header.style.background = 'rgba(0, 0, 0, 0.9)';
            }
        });
    </script>
</body>
</html>
    '''
    
    return render_template_string(download_page_html, launcher_version=launcher_version)

# API Routes
@app.route('/api/version', methods=['GET'])
def get_current_version():
    """Get the current active version info"""
    try:
        active_version = get_active_version()
        
        if not active_version:
            return jsonify({'error': 'No active version available'}), 404
        
        # Ensure download URL is complete
        download_url = active_version['download_url']
        if not download_url.startswith('http'):
            download_url = f"{BASE_URL}/downloads/{download_url}"
        
        version_info = {
            'Version': active_version['version'],
            'DownloadUrl': download_url,
            'ReleaseNotes': active_version.get('release_notes', ''),
            'FileSize': active_version.get('file_size', 0)
        }
        
        return jsonify(version_info)
    
    except Exception as e:
        return jsonify({'error': f'Error retrieving version info: {str(e)}'}), 500

@app.route('/api/launcher/version', methods=['GET'])
def get_launcher_version():
    """Get the current launcher version info"""
    try:
        launcher_version = get_active_launcher_version()
        
        if not launcher_version:
            return jsonify({'error': 'No launcher version available'}), 404
        
        # Ensure download URL is complete
        download_url = launcher_version['download_url']
        if not download_url.startswith('http'):
            download_url = f"{BASE_URL}/downloads/{download_url}"
        
        version_info = {
            'Version': launcher_version['version'],
            'DownloadUrl': download_url,
            'ReleaseNotes': launcher_version.get('release_notes', ''),
            'FileSize': launcher_version.get('file_size', 0)
        }
        
        return jsonify(version_info)
    
    except Exception as e:
        return jsonify({'error': f'Error retrieving launcher version info: {str(e)}'}), 500

@app.route('/api/version/history', methods=['GET'])
def get_version_history():
    """Get all versions history"""
    try:
        versions = load_versions()
        # Sort by release date, newest first
        versions.sort(key=lambda x: x.get('release_date', ''), reverse=True)
        return jsonify(versions)
    except Exception as e:
        return jsonify({'error': f'Error retrieving version history: {str(e)}'}), 500

@app.route('/api/launcher/history', methods=['GET'])
def get_launcher_history():
    """Get all launcher versions history"""
    try:
        launcher_versions = load_launcher_versions()
        # Sort by release date, newest first
        launcher_versions.sort(key=lambda x: x.get('release_date', ''), reverse=True)
        return jsonify(launcher_versions)
    except Exception as e:
        return jsonify({'error': f'Error retrieving launcher history: {str(e)}'}), 500

@app.route('/api/upload', methods=['POST'])
def upload_game_version():
    """Upload a new game version"""
    try:
        # Check if file was uploaded
        if 'game_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['game_file']
        version = request.form.get('version', '').strip()
        release_notes = request.form.get('release_notes', '')
        upload_type = request.form.get('upload_type', 'game')  # 'game' or 'launcher'
        
        if not version:
            return jsonify({'error': 'Version is required'}), 400
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only ZIP files are allowed'}), 400
        
        # Create secure filename
        if upload_type == 'launcher':
            filename = f"launcher-v{version}.zip"
        else:
            filename = f"game-v{version}.zip"
            
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save uploaded file
        file.save(filepath)
        
        # Get file size
        file_size = os.path.getsize(filepath)
        
        # Create version info
        version_info = {
            'version': version,
            'download_url': filename,
            'release_notes': release_notes,
            'file_size': file_size,
            'release_date': datetime.utcnow().isoformat(),
            'is_active': True  # New uploads are active by default
        }
        
        if upload_type == 'launcher':
            # Handle launcher versions
            launcher_versions = load_launcher_versions()
            
            # Remove existing version if it exists
            launcher_versions = [v for v in launcher_versions if v['version'] != version]
            
            # Deactivate all other versions
            for v in launcher_versions:
                v['is_active'] = False
            
            # Add new version
            launcher_versions.append(version_info)
            
            # Save launcher versions
            save_launcher_versions(launcher_versions)
            
            return jsonify({
                'message': 'Launcher version uploaded successfully',
                'version': version,
                'file_size': file_size,
                'file_size_formatted': format_file_size(file_size)
            })
        else:
            # Handle game versions (existing logic)
            versions = load_versions()
            
            # Remove existing version if it exists
            versions = [v for v in versions if v['version'] != version]
            
            # Deactivate all other versions
            for v in versions:
                v['is_active'] = False
            
            # Add new version
            versions.append(version_info)
            
            # Save versions
            save_versions(versions)
            
            return jsonify({
                'message': 'Game version uploaded successfully',
                'version': version,
                'file_size': file_size,
                'file_size_formatted': format_file_size(file_size)
            })
    
    except Exception as e:
        return jsonify({'error': f'Error uploading version: {str(e)}'}), 500

@app.route('/api/version/<version>/activate', methods=['POST'])
def activate_version(version):
    """Activate a specific version"""
    try:
        versions = load_versions()
        target_version = None
        
        # Find the target version
        for v in versions:
            if v['version'] == version:
                target_version = v
                break
        
        if not target_version:
            return jsonify({'error': f'Version {version} not found'}), 404
        
        # Deactivate all versions
        for v in versions:
            v['is_active'] = False
        
        # Activate target version
        target_version['is_active'] = True
        
        save_versions(versions)
        
        return jsonify({'message': f'Version {version} activated successfully'})
    
    except Exception as e:
        return jsonify({'error': f'Error activating version: {str(e)}'}), 500

@app.route('/api/launcher/version/<version>/activate', methods=['POST'])
def activate_launcher_version(version):
    """Activate a specific launcher version"""
    try:
        launcher_versions = load_launcher_versions()
        target_version = None
        
        # Find the target version
        for v in launcher_versions:
            if v['version'] == version:
                target_version = v
                break
        
        if not target_version:
            return jsonify({'error': f'Launcher version {version} not found'}), 404
        
        # Deactivate all versions
        for v in launcher_versions:
            v['is_active'] = False
        
        # Activate target version
        target_version['is_active'] = True
        
        save_launcher_versions(launcher_versions)
        
        return jsonify({'message': f'Launcher version {version} activated successfully'})
    
    except Exception as e:
        return jsonify({'error': f'Error activating launcher version: {str(e)}'}), 500

@app.route('/api/version/<version>', methods=['DELETE'])
def delete_version(version):
    """Delete a specific version"""
    try:
        versions = load_versions()
        target_version = None
        
        # Find the target version
        for v in versions:
            if v['version'] == version:
                target_version = v
                break
        
        if not target_version:
            return jsonify({'error': f'Version {version} not found'}), 404
        
        # Don't allow deleting active version
        if target_version.get('is_active', False):
            return jsonify({'error': 'Cannot delete active version. Activate another version first.'}), 400
        
        # Remove file
        filename = target_version['download_url']
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Remove from versions list
        versions = [v for v in versions if v['version'] != version]
        save_versions(versions)
        
        return jsonify({'message': f'Version {version} deleted successfully'})
    
    except Exception as e:
        return jsonify({'error': f'Error deleting version: {str(e)}'}), 500

@app.route('/api/launcher/version/<version>', methods=['DELETE'])
def delete_launcher_version(version):
    """Delete a specific launcher version"""
    try:
        launcher_versions = load_launcher_versions()
        target_version = None
        
        # Find the target version
        for v in launcher_versions:
            if v['version'] == version:
                target_version = v
                break
        
        if not target_version:
            return jsonify({'error': f'Launcher version {version} not found'}), 404
        
        # Don't allow deleting active version
        if target_version.get('is_active', False):
            return jsonify({'error': 'Cannot delete active launcher version. Activate another version first.'}), 400
        
        # Remove file
        filename = target_version['download_url']
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Remove from versions list
        launcher_versions = [v for v in launcher_versions if v['version'] != version]
        save_launcher_versions(launcher_versions)
        
        return jsonify({'message': f'Launcher version {version} deleted successfully'})
    
    except Exception as e:
        return jsonify({'error': f'Error deleting launcher version: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'Healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

# Simple health endpoint for Docker
@app.route('/health')
def health():
    """Simple health check endpoint for Docker"""
    return {'status': 'healthy'}, 200

# Static file serving
@app.route('/downloads/<filename>')
def download_file(filename):
    """Serve download files"""
    return send_from_directory(UPLOAD_FOLDER, filename)

# Admin interface
@app.route('/admin')
@login_required
def admin_interface():
    """Admin web interface"""
    admin_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Game Update Server Admin</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid #e9ecef; padding-bottom: 15px; }
        .user-info { display: flex; align-items: center; gap: 10px; }
        .user-info span { color: #666; font-weight: bold; }
        .upload-form { background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .version-list { margin: 20px 0; }
        .version-item { 
            background: white; 
            padding: 15px; 
            margin: 10px 0; 
            border-radius: 5px; 
            border-left: 4px solid #007bff;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .active { border-left-color: #28a745; background: #f8fff9; }
        .btn { 
            padding: 8px 16px; 
            border: none; 
            border-radius: 4px; 
            cursor: pointer; 
            margin: 0 5px;
            text-decoration: none;
            display: inline-block;
            font-size: 12px;
        }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn:hover { opacity: 0.8; }
        input, textarea, select { width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        .file-input { width: auto; }
        .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .status.success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .status.error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .loading { display: none; text-align: center; padding: 20px; }
        .progress { width: 100%; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; margin: 10px 0; }
        .progress-bar { height: 100%; background: #007bff; width: 0%; transition: width 0.3s; }
        .tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid #e9ecef; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; margin-right: 10px; }
        .tab.active { border-bottom-color: #007bff; background: #f8f9fa; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .inline-form { display: flex; gap: 10px; align-items: end; }
        .inline-form > div { flex: 1; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎮 Game Update Server Admin</h1>
            <div class="user-info">
                <span>👤 {{ session.username }}</span>
                <a href="{{ url_for('manage_users') }}" class="btn btn-primary">👥 Users</a>
                <a href="{{ url_for('logout') }}" class="btn btn-danger">🚪 Logout</a>
            </div>
        </div>
        
        <div id="status"></div>
        
        <!-- Tabs -->
        <div class="tabs">
            <div class="tab active" onclick="showTab('game')">🎮 Game Versions</div>
            <div class="tab" onclick="showTab('launcher')">🚀 Launcher Versions</div>
        </div>
        
        <!-- Game Tab -->
        <div id="game-tab" class="tab-content active">
            <div class="upload-form">
                <h3>📦 Upload New Game Version</h3>
                <form id="uploadGameForm" enctype="multipart/form-data">
                    <div class="inline-form">
                        <div>
                            <label><strong>Version:</strong></label>
                            <input type="text" id="gameVersion" name="version" placeholder="e.g., 1.2.3" required>
                        </div>
                        <div>
                            <label><strong>Game File (ZIP):</strong></label>
                            <input type="file" id="gameFile" name="game_file" accept=".zip" class="file-input" required>
                        </div>
                        <div>
                            <label>&nbsp;</label>
                            <button type="submit" class="btn btn-primary" id="uploadGameBtn">Upload Game</button>
                        </div>
                    </div>
                    
                    <label><strong>Release Notes:</strong></label>
                    <textarea id="gameReleaseNotes" name="release_notes" placeholder="What's new in this version..." rows="3"></textarea>
                    
                    <input type="hidden" name="upload_type" value="game">
                    
                    <div class="progress" id="gameUploadProgress" style="display: none;">
                        <div class="progress-bar" id="gameProgressBar"></div>
                    </div>
                </form>
            </div>
            
            <div class="version-list">
                <h3>📋 Game Versions</h3>
                <div class="loading" id="gameLoading">Loading game versions...</div>
                <div id="gameVersions"></div>
            </div>
        </div>
        
        <!-- Launcher Tab -->
        <div id="launcher-tab" class="tab-content">
            <div class="upload-form">
                <h3>🚀 Upload New Launcher Version</h3>
                <form id="uploadLauncherForm" enctype="multipart/form-data">
                    <div class="inline-form">
                        <div>
                            <label><strong>Version:</strong></label>
                            <input type="text" id="launcherVersion" name="version" placeholder="e.g., 2.1.0" required>
                        </div>
                        <div>
                            <label><strong>Launcher File (ZIP):</strong></label>
                            <input type="file" id="launcherFile" name="game_file" accept=".zip" class="file-input" required>
                        </div>
                        <div>
                            <label>&nbsp;</label>
                            <button type="submit" class="btn btn-primary" id="uploadLauncherBtn">Upload Launcher</button>
                        </div>
                    </div>
                    
                    <label><strong>Release Notes:</strong></label>
                    <textarea id="launcherReleaseNotes" name="release_notes" placeholder="What's new in this launcher version..." rows="3"></textarea>
                    
                    <input type="hidden" name="upload_type" value="launcher">
                    
                    <div class="progress" id="launcherUploadProgress" style="display: none;">
                        <div class="progress-bar" id="launcherProgressBar"></div>
                    </div>
                </form>
            </div>
            
            <div class="version-list">
                <h3>🚀 Launcher Versions</h3>
                <div class="loading" id="launcherLoading">Loading launcher versions...</div>
                <div id="launcherVersions"></div>
            </div>
        </div>
    </div>

    <script>
        // Tab functionality
        function showTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName + '-tab').classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
            
            // Load versions for the selected tab
            if (tabName === 'game') {
                loadGameVersions();
            } else {
                loadLauncherVersions();
            }
        }

        // Load versions on page load
        loadGameVersions();
        loadLauncherVersions();

        // Game upload form handler
        document.getElementById('uploadGameForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            uploadVersion('game');
        });
        
        // Launcher upload form handler
        document.getElementById('uploadLauncherForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            uploadVersion('launcher');
        });

        async function uploadVersion(type) {
            const formId = type === 'game' ? 'uploadGameForm' : 'uploadLauncherForm';
            const btnId = type === 'game' ? 'uploadGameBtn' : 'uploadLauncherBtn';
            const progressId = type === 'game' ? 'gameUploadProgress' : 'launcherUploadProgress';
            const progressBarId = type === 'game' ? 'gameProgressBar' : 'launcherProgressBar';
            
            const form = document.getElementById(formId);
            const uploadBtn = document.getElementById(btnId);
            const progressDiv = document.getElementById(progressId);
            const progressBar = document.getElementById(progressBarId);
            
            const formData = new FormData(form);
            
            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            progressDiv.style.display = 'block';
            
            try {
                const xhr = new XMLHttpRequest();
                
                // Track upload progress
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = (e.loaded / e.total) * 100;
                        progressBar.style.width = percentComplete + '%';
                    }
                });
                
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        const response = JSON.parse(xhr.responseText);
                        showStatus(`✅ ${type === 'game' ? 'Game' : 'Launcher'} version uploaded successfully!`, 'success');
                        form.reset();
                        if (type === 'game') {
                            loadGameVersions();
                        } else {
                            loadLauncherVersions();
                        }
                    } else {
                        const error = JSON.parse(xhr.responseText);
                        showStatus('❌ Upload failed: ' + error.error, 'error');
                    }
                };
                
                xhr.onerror = function() {
                    showStatus('❌ Upload failed: Network error', 'error');
                };
                
                xhr.open('POST', '/api/upload');
                xhr.send(formData);
                
            } catch (error) {
                showStatus('❌ Upload failed: ' + error.message, 'error');
            } finally {
                uploadBtn.disabled = false;
                uploadBtn.textContent = type === 'game' ? 'Upload Game' : 'Upload Launcher';
                progressDiv.style.display = 'none';
                progressBar.style.width = '0%';
            }
        }

        async function loadGameVersions() {
            const loading = document.getElementById('gameLoading');
            const versionsDiv = document.getElementById('gameVersions');
            
            loading.style.display = 'block';
            versionsDiv.innerHTML = '';
            
            try {
                const response = await fetch('/api/version/history');
                const versions = await response.json();
                
                loading.style.display = 'none';
                
                if (versions.length === 0) {
                    versionsDiv.innerHTML = '<p>🔭 No game versions uploaded yet.</p>';
                    return;
                }
                
                renderVersions(versions, versionsDiv, 'game');
                
            } catch (error) {
                loading.style.display = 'none';
                showStatus('❌ Failed to load game versions: ' + error.message, 'error');
            }
        }
        
        async function loadLauncherVersions() {
            const loading = document.getElementById('launcherLoading');
            const versionsDiv = document.getElementById('launcherVersions');
            
            loading.style.display = 'block';
            versionsDiv.innerHTML = '';
            
            try {
                const response = await fetch('/api/launcher/history');
                let versions = [];
                
                if (response.ok) {
                    versions = await response.json();
                }
                
                loading.style.display = 'none';
                
                if (versions.length === 0) {
                    versionsDiv.innerHTML = '<p>🔭 No launcher versions uploaded yet.</p>';
                    return;
                }
                
                renderVersions(versions, versionsDiv, 'launcher');
                
            } catch (error) {
                loading.style.display = 'none';
                showStatus('❌ Failed to load launcher versions: ' + error.message, 'error');
            }
        }
        
        function renderVersions(versions, container, type) {
            versions.forEach(version => {
                const versionDiv = document.createElement('div');
                versionDiv.className = 'version-item' + (version.is_active ? ' active' : '');
                
                const fileSize = formatFileSize(version.file_size || 0);
                const releaseDate = new Date(version.release_date).toLocaleString();
                const icon = type === 'game' ? '🎮' : '🚀';
                
                versionDiv.innerHTML = `
                    <div>
                        <strong>${icon} v${version.version}</strong> ${version.is_active ? '<span style="color: #28a745;">●</span> Active' : '<span style="color: #6c757d;">○</span> Inactive'}
                        <br>
                        <small>📅 Released: ${releaseDate} | 💾 Size: ${fileSize}</small>
                        <br>
                        <small>📝 ${version.release_notes || 'No release notes provided'}</small>
                    </div>
                    <div>
                        ${!version.is_active ? `<button class="btn btn-success" onclick="activateVersion('${version.version}', '${type}')">✅ Activate</button>` : ''}
                        <button class="btn btn-danger" onclick="deleteVersion('${version.version}', '${type}')" ${version.is_active ? 'style="background: #6c757d;" title="Deactivate first to delete"' : ''}>🗑️ Delete</button>
                    </div>
                `;
                
                container.appendChild(versionDiv);
            });
        }

        async function activateVersion(version, type) {
            if (confirm(`Activate ${type} version ${version}? This will make it the current version for all clients.`)) {
                try {
                    const endpoint = type === 'game' ? `/api/version/${version}/activate` : `/api/launcher/version/${version}/activate`;
                    const response = await fetch(endpoint, { method: 'POST' });
                    const result = await response.json();
                    
                    if (response.ok) {
                        showStatus(`✅ ${type === 'game' ? 'Game' : 'Launcher'} version ${version} activated successfully!`, 'success');
                        if (type === 'game') {
                            loadGameVersions();
                        } else {
                            loadLauncherVersions();
                        }
                    } else {
                        showStatus('❌ Failed to activate version: ' + result.error, 'error');
                    }
                } catch (error) {
                    showStatus('❌ Error: ' + error.message, 'error');
                }
            }
        }

        async function deleteVersion(version, type) {
            if (confirm(`Delete ${type} version ${version}? This action cannot be undone.`)) {
                try {
                    const endpoint = type === 'game' ? `/api/version/${version}` : `/api/launcher/version/${version}`;
                    const response = await fetch(endpoint, { method: 'DELETE' });
                    const result = await response.json();
                    
                    if (response.ok) {
                        showStatus(`✅ ${type === 'game' ? 'Game' : 'Launcher'} version ${version} deleted successfully!`, 'success');
                        if (type === 'game') {
                            loadGameVersions();
                        } else {
                            loadLauncherVersions();
                        }
                    } else {
                        showStatus('❌ Failed to delete version: ' + result.error, 'error');
                    }
                } catch (error) {
                    showStatus('❌ Error: ' + error.message, 'error');
                }
            }
        }

        function formatFileSize(bytes) {
            if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
            if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
            if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return bytes + ' bytes';
        }

        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = `<div class="status ${type}">${message}</div>`;
            
            // Auto-hide success messages after 5 seconds
            if (type === 'success') {
                setTimeout(() => {
                    statusDiv.innerHTML = '';
                }, 5000);
            }
        }
    </script>
</body>
</html>
    '''
    
    return render_template_string(admin_html)

if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    
    # Get configuration from environment
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.getenv('PORT', 5000))
    
    if debug_mode:
        print("🚀 Starting Game Update Server...")
        print(f"🌐 Launcher Download: http://localhost:{port}/")
        print(f"📊 Admin Interface: http://localhost:{port}/admin")
        print(f"🔑 Default Login: admin/admin123")
        print(f"🔗 API Endpoint: http://localhost:{port}/api/version")
        print(f"🚀 Launcher API: http://localhost:{port}/api/launcher/version")
        print(f"💾 Downloads folder: {os.path.abspath(UPLOAD_FOLDER)}")
        print(f"📁 Data folder: {os.path.abspath(DATA_FOLDER)}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)


