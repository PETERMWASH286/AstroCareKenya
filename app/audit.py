# /home/pincho/Desktop/astrocare/app/audit.py

from sqlalchemy import inspect, event
from flask import request, has_request_context
from flask_login import current_user
import json
from datetime import datetime, date
import uuid
from decimal import Decimal

from app.models import AuditLog, db
from sqlalchemy.orm import DeclarativeMeta

# Custom JSON encoder to handle special types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        # Fallback for other date/time-like objects
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

def is_model_instance(obj):
    """
    Detect whether obj is a SQLAlchemy model instance.
    We check for the DeclarativeMeta metaclass.
    """
    return isinstance(obj.__class__, DeclarativeMeta)

def model_to_string(obj):
    """
    Convert a SQLAlchemy model instance into a string representation,
    e.g. "Privilege(42)" or "Role(5)". Adjust as needed.
    """
    insp = inspect(obj)
    pk = insp.identity
    if pk is None:
        # Object not yet persisted
        return f"{obj.__class__.__name__}(unsaved)"
    # If composite primary key, join by comma; else single value:
    if isinstance(pk, tuple):
        pk_str = ",".join(map(str, pk))
    else:
        pk_str = str(pk)
    return f"{obj.__class__.__name__}({pk_str})"

def serialize_for_json(data):
    """
    Recursively serialize data so that it contains only JSON-friendly types:
    - dict, list, tuple, primitives, date/time, Decimal, UUID, and simple strings
    - If we encounter a SQLAlchemy model instance, replace it with model_to_string()
    """
    if isinstance(data, dict):
        return {k: serialize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [serialize_for_json(v) for v in data]
    if isinstance(data, tuple):
        return tuple(serialize_for_json(v) for v in data)
    # Handle basic scalar types
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    # Handle special types
    if isinstance(data, (datetime, date, Decimal, uuid.UUID)):
        return CustomJSONEncoder().default(data)
    # Handle SQLAlchemy model instances
    if is_model_instance(data):
        return model_to_string(data)
    # Fallback: leave as-is (e.g. enum)
    return str(data)

def get_audit_info():
    """
    Get user and IP information from the current request context.
    """
    if has_request_context():
        ip = request.remote_addr or 'unknown'
        if current_user.is_authenticated:
            return current_user.id, current_user.username, ip
        return None, 'anonymous', ip
    return None, 'system', None

def should_audit(target):
    """
    Only audit if the model’s __audit_trail__ attribute is True (or missing).
    """
    return getattr(target.__class__, '__audit_trail__', True)

def get_record_id(target):
    """
    Return a string representation of the target’s primary key(s).
    """
    insp = inspect(target)
    pk = insp.identity
    if isinstance(pk, tuple):
        return ",".join(map(str, pk))
    return str(pk)

def log_audit_event(action, target, connection, changes=None):
    """
    Insert a row into audit_logs.  
    - action: 'CREATE', 'UPDATE', or 'DELETE'  
    - target: the SQLAlchemy object being audited  
    - changes: dict of {'col': {'old': old_val, 'new': new_val}} for UPDATE
    """
    if not should_audit(target):
        return

    user_id, username, ip = get_audit_info()
    model_name = target.__class__.__name__
    record_id = get_record_id(target)

    # Build details dict
    details = {}
    insp = inspect(target)

    if action == 'CREATE':
        details = {
            'new': {
                col.key: getattr(target, col.key)
                for col in insp.mapper.column_attrs
            }
        }
    elif action == 'UPDATE' and changes:
        details = {'changes': changes}
    elif action == 'DELETE':
        details = {
            'deleted': {
                col.key: getattr(target, col.key)
                for col in insp.mapper.column_attrs
            }
        }

    # Redact sensitive fields
    for field in ('password', 'password_hash', 'token'):
        if 'new' in details and field in details['new']:
            details['new'][field] = '***REDACTED***'
        if 'deleted' in details and field in details['deleted']:
            details['deleted'][field] = '***REDACTED***'

    # Serialize details recursively
    details = serialize_for_json(details)

    # Insert audit row
    audit_log_table = AuditLog.__table__
    connection.execute(
        audit_log_table.insert().values(
            user_id    = user_id,
            username   = username,
            ip_address = ip,
            action     = action,
            model_name = model_name,
            record_id  = record_id,
            timestamp  = datetime.utcnow(),
            details    = details
        )
    )

# Hook into insert/update/delete events
def after_insert_listener(mapper, connection, target):
    log_audit_event('CREATE', target, connection)

def before_update_listener(mapper, connection, target):
    changes = {}
    insp = inspect(target)

    for attr in insp.attrs:
        hist = attr.history
        if hist.has_changes():
            # Special handling for many-to-many (e.g. roles or privileges)
            if attr.key in ('roles', 'privileges'):
                # Represent added/deleted lists of model instances
                added = [model_to_string(item) for item in hist.added]
                deleted = [model_to_string(item) for item in hist.deleted]
                if added or deleted:
                    changes[attr.key] = {'old': deleted, 'new': added}
            else:
                old_val = hist.deleted[0] if hist.deleted else None
                new_val = hist.added[0] if hist.added else None

                # If they are model instances, convert to string
                if is_model_instance(old_val):
                    old_val = model_to_string(old_val)
                if is_model_instance(new_val):
                    new_val = model_to_string(new_val)

                # If they are special types (datetime/date/Decimal/UUID), serialize
                if isinstance(old_val, (datetime, date, Decimal, uuid.UUID)):
                    old_val = CustomJSONEncoder().default(old_val)
                if isinstance(new_val, (datetime, date, Decimal, uuid.UUID)):
                    new_val = CustomJSONEncoder().default(new_val)

                changes[attr.key] = {'old': old_val, 'new': new_val}

    if changes:
        log_audit_event('UPDATE', target, connection, changes)

def before_flush_listener(session, flush_context, instances):
    for obj in session.deleted:
        if isinstance(obj, db.Model) and should_audit(obj):
            log_audit_event('DELETE', obj, session.connection())

# Register the listeners
event.listen(db.Model, 'after_insert', after_insert_listener)
event.listen(db.Model, 'before_update', before_update_listener)
event.listen(db.Session, 'before_flush', before_flush_listener)
