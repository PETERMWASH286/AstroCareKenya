# app/utils/notifications.py
import os
import logging
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import smtplib
import africastalking

# Configure logging
logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, app=None):
        self.smtp_server = None
        self.smtp_port = None
        self.smtp_username = None
        self.smtp_password = None
        self.smtp_sender = None
        self.africastalking_username = None
        self.africastalking_api_key = None
        self.africastalking_sender = None
        
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize with Flask app configuration"""
        # Email configuration - Updated to match your Config class
        self.smtp_server = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        self.smtp_port = app.config.get('MAIL_PORT', 587)
        self.smtp_username = app.config.get('MAIL_USERNAME')
        self.smtp_password = app.config.get('MAIL_PASSWORD')
        self.smtp_sender = app.config.get('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME'))
        
        # SMS Configuration - Updated to match your Config class
        self.africastalking_username = app.config.get('AFRICASTALKING_USERNAME')
        self.africastalking_api_key = app.config.get('AFRICASTALKING_API_KEY')
        self.africastalking_sender = app.config.get('SMS_SENDER_ID', 'ASTROCARE')

        # Debug logging to verify configuration
        logger.info(f"NotificationManager initialized with:")
        logger.info(f"SMTP Server: {self.smtp_server}:{self.smtp_port}")
        logger.info(f"SMTP Username: {self.smtp_username}")
        logger.info(f"SMTP Sender: {self.smtp_sender}")
        logger.info(f"Africa's Talking Username: {self.africastalking_username}")
        logger.info(f"Africa's Talking Sender: {self.africastalking_sender}")

    def send_email(self, subject, recipients, body, html_body=None, attachments=None, cc=None, bcc=None, sender=None):
        """
        Send email using SMTP configuration from app config
        
        :param subject: Email subject
        :param recipients: List of recipient email addresses
        :param body: Plain text email body
        :param html_body: HTML email body (optional)
        :param attachments: List of file paths to attach (optional)
        :param cc: List of CC email addresses (optional)
        :param bcc: List of BCC email addresses (optional)
        :param sender: Override sender email address (optional)
        :return: Boolean indicating success
        """
        try:
            # Print email details for debugging
            print("=== Email Details ===")
            print("SMTP Server:", self.smtp_server)
            print("SMTP Port:", self.smtp_port)
            print("SMTP Username:", self.smtp_username)
            print("Subject:", subject)
            print("From:", sender or self.smtp_sender)
            print("To:", recipients)
            if cc:
                print("Cc:", cc)
            if bcc:
                print("Bcc:", bcc)
            print("Body length:", len(body))
            if html_body:
                print("HTML Body length:", len(html_body))
            if attachments:
                print("Attachments:", attachments)
            print("=====================")
            sys.stdout.flush()
            
            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = sender or self.smtp_sender
            msg['To'] = ', '.join(recipients)
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)

            # Attach plain text body
            # If both plain text and HTML provided, use multipart/alternative
            if body and html_body:
                alt_part = MIMEMultipart('alternative')
                alt_part.attach(MIMEText(body, 'plain'))
                alt_part.attach(MIMEText(html_body, 'html'))
                msg.attach(alt_part)
            elif html_body:
                msg.attach(MIMEText(html_body, 'html'))
            elif body:
                msg.attach(MIMEText(body, 'plain'))


            # Attach any files provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                        msg.attach(part)
                    else:
                        logger.warning(f"Attachment file not found: {file_path}")

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                print("SMTP login successful, sending email...")
                sys.stdout.flush()
                
                # Combine all recipients
                all_recipients = recipients.copy()
                if cc:
                    all_recipients.extend(cc)
                if bcc:
                    all_recipients.extend(bcc)
                
                server.send_message(msg)
                print(f"Email sent successfully to: {recipients}")
                sys.stdout.flush()

            logger.info(f"Email sent successfully to {recipients}")
            return True

        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            print(error_msg)
            sys.stdout.flush()
            logger.error(error_msg)
            return False

    def send_sms(self, message, recipients, sender_id=None):
        """
        Send SMS via Africa's Talking with detailed logging.
        """
        try:
            # Log credentials (without exposing full key)
            logger.info(f"=== SMS Attempt ===")
            logger.info(f"AT Username: {self.africastalking_username}")
            logger.info(f"AT Sender ID: {self.africastalking_sender}")
            logger.info(f"Recipients (raw): {recipients}")
            logger.info(f"Message (first 50 chars): {message[:50]}...")

            if not self.africastalking_username or not self.africastalking_api_key:
                logger.error("Africa's Talking credentials not configured")
                return False

            # Initialize Africa's Talking
            africastalking.initialize(
                self.africastalking_username,
                self.africastalking_api_key
            )
            sms = africastalking.SMS

            # Format recipients
            formatted_recipients = []
            for phone in recipients:
                phone = phone.strip()
                if not phone.startswith('+'):
                    if phone.startswith('0'):
                        phone = '+254' + phone[1:]
                    else:
                        phone = '+254' + phone
                formatted_recipients.append(phone)

            logger.info(f"Formatted recipients: {formatted_recipients}")

            # Send SMS
            response = sms.send(
                message=message,
                recipients=formatted_recipients
            )

            # Log the full response for debugging
            logger.info(f"Full API response: {response}")

            # Check response
            if response.get('SMSMessageData', {}).get('Recipients'):
                successful = [r for r in response['SMSMessageData']['Recipients'] if r.get('status') == 'Success']
                logger.info(f"Successful recipients: {successful}")
                if successful:
                    return True
                else:
                    logger.error("No successful recipients. Response: %s", response)
                    return False
            else:
                logger.error("No recipients processed. Response: %s", response)
                return False

        except Exception as e:
            logger.exception("Exception in send_sms")
            return False

    def send_notification(self, subject, message, email_recipients=None, sms_recipients=None, html_message=None):
        """
        Send both email and SMS notifications
        
        :param subject: Notification subject
        :param message: Notification message
        :param email_recipients: List of email addresses
        :param sms_recipients: List of phone numbers
        :param html_message: HTML version of email (optional)
        :return: Dictionary with results for email and SMS
        """
        results = {
            'email_sent': False,
            'sms_sent': False
        }
        
        # Send email if recipients provided
        if email_recipients:
            results['email_sent'] = self.send_email(
                subject=subject,
                recipients=email_recipients,
                body=message,
                html_body=html_message
            )
        
        # Send SMS if recipients provided
        if sms_recipients:
            results['sms_sent'] = self.send_sms(
                message=message,
                recipients=sms_recipients
            )
        
        return results

# Initialize extension
notification_manager = NotificationManager()








