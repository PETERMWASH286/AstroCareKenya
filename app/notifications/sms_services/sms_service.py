import africastalking
from flask import current_app

def initialize_sms_service():
    """Initialize Africa's Talking service with app config"""
    africastalking.initialize(
        username=current_app.config['AFRICASTALKING_USERNAME'],
        api_key=current_app.config['AFRICASTALKING_API_KEY']
    )
    return africastalking.SMS

def format_kenyan_phone(phone):
    """Format phone number to E.164 format for Africa's Talking"""
    # Remove any non-digit characters
    cleaned = ''.join(filter(str.isdigit, phone))
    
    # Handle Kenyan numbers
    if cleaned.startswith('0'):
        return '+254' + cleaned[1:]
    elif cleaned.startswith('254'):
        return '+' + cleaned
    elif cleaned.startswith('7'):
        return '+254' + cleaned
    else:
        return '+' + cleaned  # Assume it's already in E.164 format

def send_sms(phone_numbers, message):
    try:
        # Validate input
        if not phone_numbers:
            current_app.logger.warning("No phone numbers provided for SMS")
            return {
                'success': False,
                'error': 'No phone numbers provided'
            }
            
        # Initialize service
        sms = initialize_sms_service()
        
        # Format all numbers with validation
        formatted_numbers = []
        invalid_numbers = []
        
        for num in phone_numbers:
            if not num:
                continue
            try:
                formatted = format_kenyan_phone(num)
                if formatted.startswith('+254') and len(formatted) == 13:
                    formatted_numbers.append(formatted)
                else:
                    invalid_numbers.append(num)
            except Exception as e:
                invalid_numbers.append(num)
                current_app.logger.warning(f"Invalid number {num}: {str(e)}")
        
        if invalid_numbers:
            current_app.logger.warning(
                f"Skipping {len(invalid_numbers)} invalid numbers: {invalid_numbers[:5]}"
            )
        
        if not formatted_numbers:
            current_app.logger.error("No valid phone numbers after formatting")
            return {
                'success': False,
                'error': 'No valid phone numbers'
            }
        
        # Log first 3 numbers
        log_nums = formatted_numbers[:3]
        current_app.logger.info(
            f"Sending SMS to {len(formatted_numbers)} numbers: "
            f"{log_nums}{'...' if len(formatted_numbers) > 3 else ''}"
        )
        
        # Send SMS
        response = sms.send(
            message, 
            formatted_numbers, 
            sender_id=current_app.config['SMS_SENDER_ID']
        )
        
        current_app.logger.info(f"Africa's Talking response: {response}")
        return {
            'success': True,
            'response': response
        }
    except Exception as e:
        current_app.logger.exception(f"Africa's Talking API error: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
        
        