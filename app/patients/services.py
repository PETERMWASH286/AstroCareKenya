import base64
import datetime
import requests
from flask import current_app
from app import db
from .models import Transaction

class MpesaClient:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None

    def get_access_token(self):
        """Get M-Pesa API access token"""
        if self.access_token and self.token_expiry and datetime.datetime.now() < self.token_expiry:
            return self.access_token
            
        consumer_key    = current_app.config['MPESA_CONSUMER_KEY']
        consumer_secret = current_app.config['MPESA_CONSUMER_SECRET']
        auth_url        = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        
        try:
            current_app.logger.debug(f"Attempting M-Pesa auth with consumer key: {consumer_key[:3]}...{consumer_key[-3:]}")
            response = requests.get(
                auth_url,
                auth=(consumer_key, consumer_secret),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            
            current_app.logger.debug(f"Auth response: {response.text}")
            data = response.json()
            self.access_token = data['access_token']
            
            # Cast expires_in to int before doing math
            expires = int(data.get('expires_in', 0))
            self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=expires - 300)
            
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            error_msg = f"M-Pesa auth failed: {str(e)}"
            if hasattr(e, 'response') and e.response:
                error_msg += f" | Response: {e.response.text}"
            current_app.logger.error(error_msg)
            raise Exception("Could not authenticate with M-Pesa API")


    def initiate_stk_push(self, phone, amount, account_ref, description, patient_id):
        try:
            current_app.logger.info(f"STK push init - Phone: 254{phone}, Amount: {amount}, Ref: {account_ref}")
            access_token = self.get_access_token()
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            passkey = current_app.config['MPESA_PASSKEY']
            business_shortcode = current_app.config['MPESA_BUSINESS_SHORTCODE']

            password = base64.b64encode(f"{business_shortcode}{passkey}{timestamp}".encode()).decode()
            headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

            payload = {
                "BusinessShortCode": business_shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": amount,
                "PartyA": f"254{phone}",
                "PartyB": business_shortcode,
                "PhoneNumber": f"254{phone}",
                "CallBackURL": current_app.config['MPESA_CALLBACK_URL'],
                "AccountReference": account_ref,
                "TransactionDesc": description,
            }

            response = requests.post(
                'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest',
                json=payload,
                headers=headers,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()

            # Store transaction
            tx = Transaction(
                patient_id=patient_id,
                amount=amount,
                payment_method='stk',
                phone=f"254{phone}",
                account_ref=account_ref,
                checkout_request_id=data.get('CheckoutRequestID'),
                status='requested'
            )
            db.session.add(tx)
            db.session.commit()

            current_app.logger.info(f"STK push successful – CheckoutID: {tx.checkout_request_id}")
            return {
                "success": True,
                "checkout_request_id": data['CheckoutRequestID'],
                "customer_message": data['CustomerMessage'],
                "transaction": tx
            }


        except Exception as e:
            current_app.logger.error(f"STK push failed: {e}", exc_info=True)
            tx = Transaction(
                patient_id=patient_id,
                amount=amount,
                payment_method='stk',
                phone=f"254{phone}",
                account_ref=account_ref,
                status='failed',
                error_message=str(e)[:255]
            )
            db.session.add(tx)
            db.session.commit()
            return {"success": False, "error": str(e)}

mpesa_client = MpesaClient()