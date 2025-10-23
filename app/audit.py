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

# -------------------------------------------------------------------
# Custom JSON encoder for special Python/SQLAlchemy types
# -------------------------------------------------------------------
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
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

# -------------------------------------------------------------------
# Utility functions
# -------------------------------------------------------------------
def is_model_instance(obj):
    """Check if obj is a SQLAlchemy model instance."""
    return isinstance(obj.__class__, DeclarativeMeta)


def model_to_string(obj):
    """Represent SQLAlchemy model instance as ModelName(PK)."""
    insp = inspect(obj)
    pk = insp.identity
    if pk is None:
        return f"{obj.__class__.__name__}(unsaved)"
    if isinstance(pk, tuple):
        pk_str = ",".join(map(str, pk))
    else:
        pk_str = str(pk)
    return f"{obj.__class__.__name__}({pk_str})"


def serialize_for_json(data):
    """Recursively convert data into JSON-safe types."""
    if isinstance(data, dict):
        return {k: serialize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [serialize_for_json(v) for v in data]
    if isinstance(data, tuple):
        return tuple(serialize_for_json(v) for v in data)
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    if isinstance(data, (datetime, date, Decimal, uuid.UUID)):
        return CustomJSONEncoder().default(data)
    if is_model_instance(data):
        return model_to_string(data)
    return str(data)


def get_audit_info():
    """
    Get user, IP, method, and endpoint info from the current request context.
    """
    if has_request_context():
        ip = request.remote_addr or 'unknown'
        method = request.method
        endpoint = request.endpoint
        if current_user.is_authenticated:
            return current_user.id, current_user.username, ip, method, endpoint
        return None, 'anonymous', ip, method, endpoint
    return None, 'system', None, None, None



def should_audit(target):
    """Skip auditing if model explicitly disables it."""
    return getattr(target.__class__, '__audit_trail__', True)


def get_record_id(target):
    """Get stringified PK of target object."""
    insp = inspect(target)
    pk = insp.identity
    if isinstance(pk, tuple):
        return ",".join(map(str, pk))
    return str(pk)

# -------------------------------------------------------------------
# Core logger
# -------------------------------------------------------------------
# in audit.py (replace or extend your existing function)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

MAX_MESSAGE_CHARS = 1024

def short_str(v, limit=140):
    s = str(v)
    return s if len(s) <= limit else s[:limit-1] + "…"

def build_natural_message(action, model_name, record_id, username=None, ip=None, changes=None, details=None, success=None):
    """
    Build a short human-readable sentence describing the audit event.
    - Keep it concise and avoid dumping huge JSON blobs into the message.
    """
    if action == 'CREATE':
        base = f"Created {model_name} ({record_id})."
        if details and isinstance(details, dict) and 'new' in details:
            # show up to 4 fields
            fields = list(details['new'].items())[:4]
            if fields:
                fs = ", ".join(f"{k}={short_str(v, 40)}" for k, v in fields)
                base += f" Set {fs}."
        return base

    if action == 'UPDATE':
        base = f"Updated {model_name} ({record_id})."
        if changes:
            parts = []
            for key, val in list(changes.items())[:6]:
                old = short_str(val.get('old'))
                new = short_str(val.get('new'))
                parts.append(f"{key}: {old} → {new}")
            if parts:
                base += " " + "; ".join(parts)
        return base

    if action == 'DELETE':
        return f"Deleted {model_name} ({record_id})."

    if action == 'LOGIN':
        if success:
            return f"User '{username}' logged in successfully from {ip or 'unknown IP'}."
        else:
            reason = None
            if isinstance(details, dict):
                reason = details.get('reason') or details.get('error')
            if reason:
                return f"Failed login attempt for '{username or record_id}' from {ip or 'unknown IP'} — reason: {short_str(reason,80)}."
            return f"Failed login attempt for '{username or record_id}' from {ip or 'unknown IP'}."

    if action == 'LOGOUT':
        return f"User '{username}' logged out."

    # fallback
    parts = []
    if username:
        parts.append(f"user='{username}'")
    if ip:
        parts.append(f"ip={ip}")
    if record_id:
        parts.append(f"id={record_id}")
    return f"{action} on {model_name} ({', '.join(parts)})"

def log_audit_event(action, target=None, connection=None, changes=None, *,
                    model_name_override=None, record_id_override=None,
                    success=None, message=None, details_extra=None):
    """
    Flexible audit logger.
    - `target`: SQLAlchemy model instance (optional).
    - `connection`: DB connection (from event listeners). If None, a new connection is used.
    - `model_name_override` / `record_id_override`: used when target is None.
    - `details_extra`: dict, merged into details for machine-use.
    - `message`: optional human sentence; if None one will be generated.
    """
    # Determine model_name and record_id
    if target is not None:
        model_name = target.__class__.__name__
        try:
            record_id = get_record_id(target)
        except Exception:
            record_id = record_id_override
    else:
        model_name = model_name_override or 'N/A'
        record_id = record_id_override or None

    # get request/user info
    user_id, username, ip, method, endpoint = get_audit_info()

    # assemble details from changes or new/deleted columns if target
    details = {}
    if changes:
        details['changes'] = changes
    else:
        if target is not None:
            insp = inspect(target)
            # for create/delete you may want snapshot of attributes - but careful about size
            try:
                details['snapshot'] = {col.key: getattr(target, col.key) for col in insp.mapper.column_attrs}
            except Exception:
                pass

    # merge extras (view-level details)
    if details_extra:
        details.update(details_extra)

    # redact common sensitive keys
    for field in ('password', 'password_hash', 'token', 'secret'):
        if 'snapshot' in details and field in details['snapshot']:
            details['snapshot'][field] = '***REDACTED***'
        if 'changes' in details:
            if field in details['changes']:
                details['changes'][field]['new'] = '***REDACTED***'
                details['changes'][field]['old'] = '***REDACTED***'

    # use a generated message if not provided
    if not message:
        message = build_natural_message(action, model_name, record_id, username=username, ip=ip, changes=changes, details=details, success=success)
    if message and len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS-1] + "…"

    # final serialize details for JSON
    details = serialize_for_json(details)

    audit_log_table = AuditLog.__table__
    payload = dict(
        user_id=user_id,
        username=username,
        ip_address=ip,
        method=method,
        endpoint=endpoint,
        action=action,
        model_name=model_name,
        record_id=record_id,
        timestamp=datetime.utcnow(),
        details=details,
        success=bool(success) if success is not None else None,
        message=message
    )

    close_conn = False
    if connection is None:
        # create short-lived connection for manual calls (views)
        connection = db.engine.connect()
        close_conn = True

    try:
        connection.execute(audit_log_table.insert().values(**payload))
    finally:
        if close_conn:
            try:
                connection.close()
            except Exception:
                pass


# -------------------------------------------------------------------
# Event listeners - FIXED VERSION
# -------------------------------------------------------------------
def after_insert_listener(mapper, connection, target):
    # FIXED: Use inspect to check if identity is set instead of assuming 'id' attribute
    insp = inspect(target)
    if insp.identity is None:  # Check if primary key is not set yet
        # Try to force flush to get the primary key
        try:
            # Use the session from the connection if available
            session = object_session(target)
            if session:
                session.flush()
        except Exception:
            # If flush fails, continue without the primary key
            pass
    
    if should_audit(target):
        log_audit_event('CREATE', target, connection)


def before_update_listener(mapper, connection, target):
    if not should_audit(target):
        return
        
    changes = {}
    insp = inspect(target)

    for attr in insp.attrs:
        hist = attr.history
        if hist.has_changes():
            if attr.key in ('roles', 'privileges'):
                added = [model_to_string(item) for item in hist.added]
                deleted = [model_to_string(item) for item in hist.deleted]
                if added or deleted:
                    changes[attr.key] = {'old': deleted, 'new': added}
            else:
                old_val = hist.deleted[0] if hist.deleted else None
                new_val = hist.added[0] if hist.added else None

                if is_model_instance(old_val):
                    old_val = model_to_string(old_val)
                if is_model_instance(new_val):
                    new_val = model_to_string(new_val)

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

# -------------------------------------------------------------------
# Register listeners
# -------------------------------------------------------------------
event.listen(db.Model, 'after_insert', after_insert_listener)
event.listen(db.Model, 'before_update', before_update_listener)
event.listen(db.Session, 'before_flush', before_flush_listener)