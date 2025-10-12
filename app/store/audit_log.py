from flask_login import current_user
from flask import request
from datetime import datetime
import json
from app.extensions import db
from app.store.models import InventoryAuditLog

def get_client_ip():
    """Get client IP address"""
    if not request:
        return None
    return request.environ.get('HTTP_X_REAL_IP', request.remote_addr)

def log_inventory_action(action, resource_type, resource_id, description, 
                        old_values=None, new_values=None, changed_fields=None,
                        module=None):
    """
    SIMPLE REUSABLE FUNCTION TO LOG ANY INVENTORY ACTION
    
    Usage Examples:
        # Log creation
        log_inventory_action(
            action='create',
            resource_type='external_order',
            resource_id=order.id,
            description=f"Created external order for {order.item_name}",
            new_values={'item_name': order.item_name, 'quantity': order.quantity},
            module='procurement'
        )
    """
    # Get current user info
    user_id = getattr(current_user, 'id', 0) if current_user else 0
    username = getattr(current_user, 'username', 'system') if current_user else 'system'
    branch_id = getattr(current_user, 'branch_id', None) if current_user else None
    
    # Convert resource_id to string to support both integers and UUIDs
    resource_id_str = str(resource_id)
    
    # Convert dict values to JSON strings
    if old_values and isinstance(old_values, dict):
        old_values = json.dumps(old_values, default=str)
    if new_values and isinstance(new_values, dict):
        new_values = json.dumps(new_values, default=str)
    
    # Convert changed_fields list to string
    if changed_fields and isinstance(changed_fields, list):
        changed_fields = ','.join(changed_fields)
    
    # Create the log entry
    log_entry = InventoryAuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id_str,  # Use string version
        description=description,
        old_values=old_values,
        new_values=new_values,
        changed_fields=changed_fields,
        module=module or 'inventory',
        ip_address=get_client_ip(),
        branch_id=branch_id
    )
    
    db.session.add(log_entry)
    return log_entry