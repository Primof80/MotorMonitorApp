import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'a_default_secret_key')
DATABASE_FILE = os.environ.get('DATABASE_FILE', '/tmp/motor_readings.db')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password')
