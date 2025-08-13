import jwt
import requests
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from flask import current_app, jsonify
import logging
import base64

logger = logging.getLogger("hie-integration")

def generate_encrypted_pin():
    """Generate JWT encrypted PIN using RS256 algorithm"""
    try:
        private_key = serialization.load_pem_private_key(
            current_app.config['PRIVATE_KEY'].encode(),
            password=None,
            backend=default_backend()
        )
        payload = {
            "key": f"6QP-{current_app.config['AGENT_ID']}",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as e:
        logger.error(f"PIN generation failed: {str(e)}")
        raise

def get_dha_token():
    """Obtain access token from DHA using the official authentication endpoint"""
    try:
        # Prepare Basic Authentication header
        auth_str = f"{current_app.config['BASIC_AUTH_USERNAME']}:{current_app.config['BASIC_AUTH_PASSWORD']}"
        basic_auth = base64.b64encode(auth_str.encode()).decode()
        
        # Prepare request parameters
        params = {
            "key": f"6QP-{current_app.config['AGENT_ID']}"
        }
        
        # Make request to authentication endpoint
        auth_url = f"{current_app.config['DHA_BASE_URL']}/v1/hie-auth"
        response = requests.get(
            auth_url,
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Accept": "text/plain"  # API returns plain text token
            },
            params=params,
            timeout=10
        )
        
        # Log the full auth response for debugging
        logger.debug(f"Token request status: {response.status_code}")
        logger.debug(f"Token response content: {response.text[:100]}...")
        
        if response.status_code != 200:
            logger.error(f"DHA token error: {response.status_code} - {response.text}")
            return None
            
        # The token is returned as plain text in the response body
        return response.text.strip()
    except requests.exceptions.RequestException as e:
        logger.error(f"Token request failed: {str(e)}")
        return None

def make_dha_request(endpoint, method='GET', params=None, json_data=None):
    """Make authenticated request to DHA API"""
    token = get_dha_token()
    if not token:
        return {'error': 'DHA authentication failed'}, 503
    
    headers = {
        "Authorization": f"Token {token}",  # Changed from Bearer to Token
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    url = f"{current_app.config['DHA_BASE_URL']}{endpoint}"
    
    try:
        if method == 'GET':
            response = requests.get(url, params=params, headers=headers, timeout=15)
        elif method == 'POST':
            response = requests.post(url, json=json_data, headers=headers, timeout=15)
        else:
            return {'error': 'Unsupported HTTP method'}, 400
        
        return handle_dha_response(response)
    except requests.exceptions.RequestException as e:
        logger.error(f"DHA API request failed: {str(e)}")
        return {'error': f"Connection to DHA failed: {str(e)}"}, 503
    
def handle_dha_response(response):
    """Handle responses from DHA API"""
    try:
        response_data = response.json()
    except ValueError:
        response_data = response.text
    
    if response.status_code == 200:
        return response_data
    elif response.status_code == 401:
        return {'error': 'Unauthorized access to DHA API'}, 401
    elif response.status_code == 404:
        return {'error': 'Resource not found in DHA system'}, 404
    else:
        logger.error(f"DHA API error {response.status_code}: {response_data}")
        return {'error': f"DHA API error: {response_data}"}, response.status_code

