import jwt
import requests
import base64
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("dha-test")

# Your credentials
CREDENTIALS = {
    "DHA_BASE_URL": "https://uat.dha.go.ke",
    "AGENT_ID": "DHABP02218",
    "BASIC_AUTH_USERNAME": "nYTWyHmJE3Hfw1r6jCA",
    "BASIC_AUTH_PASSWORD": "oMXHQFFwitNYuKFXhjq",
    "TOKEN_AUTH_KEY": "6QP-DHABP02218",
    "TOKEN_AUTH_SECRET": "3MULZGRxo7yTsrIG2YwfHFTZCWTMvhtnUXq6PJYI78PDdC89"
}

def generate_jwt_token():
    """Generate JWT token with 20-second expiration as per DHA requirements"""
    try:
        now = datetime.utcnow()
        payload = {
            "key": CREDENTIALS['TOKEN_AUTH_KEY'],
            "iat": now,  # Issued at timestamp (REQUIRED)
            "exp": now + timedelta(seconds=20)  # 20-second expiration
        }
        return jwt.encode(payload, CREDENTIALS['TOKEN_AUTH_SECRET'], algorithm="HS256")
    except Exception as e:
        logger.error(f"JWT generation failed: {str(e)}")
        return None

def test_api_connection(token):
    """Test API connection with the generated token"""
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        params = {
            "identification_type": "National ID",
            "identification_number": "TEST123456",
            "agent": CREDENTIALS['TOKEN_AUTH_KEY']
        }
        
        url = f"{CREDENTIALS['DHA_BASE_URL']}/v3/client-registry/fetch-client"
        logger.debug(f"Making API request to: {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Params: {params}")
        
        # Generate new token for each request (since they expire in 20s)
        token = generate_jwt_token()
        headers['Authorization'] = f"Bearer {token}"
        
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=10  # Shorter timeout since token expires quickly
        )
        
        logger.debug(f"API response status: {response.status_code}")
        logger.debug(f"API response headers: {response.headers}")
        logger.debug(f"API response content: {response.text[:500]}")
        
        if response.status_code == 200:
            return {"status": "success", "response": response.json()}
        elif response.status_code == 404:
            return {"status": "success", "message": "404 expected with test data"}
        else:
            return {"status": "failure", "message": f"HTTP {response.status_code}", "response": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("=== Starting DHA Credentials Test ===")
    
    # Generate JWT token directly from credentials
    print("\n[1] Generating JWT token from credentials...")
    token = generate_jwt_token()
    
    if token:
        print(f"✓ JWT token generated successfully: {token[:50]}...")
        print(f"   Token expires in 20 seconds")
        
        # Test API connection
        print("\n[2] Testing API connection with JWT token...")
        api_result = test_api_connection(token)
        
        if api_result['status'] == 'success':
            print("✓ API connection successful!")
        else:
            print(f"✗ API connection failed: {api_result.get('message')}")
            print(f"   Response: {api_result.get('response', '')}")
    else:
        print("✗ JWT token generation failed")
    
    print("\n=== Test Complete ===")