
import pytest
from app import app as flask_app

@pytest.fixture
def app():
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

def test_home_page(client):
    """Test the home page loads correctly."""
    with client.session_transaction() as session:
        session['logged_in'] = True
    response = client.get('/')
    assert response.status_code == 200

def test_motors_route(client):
    """Test the /motors route loads correctly."""
    with client.session_transaction() as session:
        session['logged_in'] = True
    response = client.get('/motors')
    assert response.status_code == 200

def test_api_motors_route(client):
    """Test the /api/motors route loads correctly."""
    with client.session_transaction() as session:
        session['logged_in'] = True
    response = client.get('/api/motors')
    assert response.status_code == 200

def test_api_motor_1_route(client):
    """Test the /api/motor/1 route loads correctly."""
    with client.session_transaction() as session:
        session['logged_in'] = True
    response = client.get('/api/motor/1')
    assert response.status_code == 200

def test_api_motor_1_route_is_json(client):
    """Test the /api/motor/1 route returns a JSON response."""
    with client.session_transaction() as session:
        session['logged_in'] = True
    response = client.get('/api/motor/1')
    assert response.is_json

def test_post_data_route(client):
    """Test the post data route returns a 200 status code."""
    response = client.post('/data', json={
        "motor_id": 1,
        "timestamp": "2022-01-01 00:00:00",
        "dominant_freq": 1.0,
        "amplitude": 1.0,
        "temp": 1.0,
        "is_running": 1
    })
    assert response.status_code == 200

def test_post_data_route_is_json(client):
    """Test the post data route returns a JSON response."""
    response = client.post('/data', json={
        "motor_id": 1,
        "timestamp": "2022-01-01 00:00:00",
        "dominant_freq": 1.0,
        "amplitude": 1.0,
        "temp": 1.0,
        "is_running": 1
    })
    assert response.is_json
