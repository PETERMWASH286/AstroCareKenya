# app/shared_models.py
"""
A simple aggregator to re‑export models that are used across modules,
so that no module needs to import directly from another module.
"""

# Import the models from their original modules:
from app.auth.models import Role, User      # auth models live in app/auth/models.py
from app.user_management.models import Privilege  # privilege lives in app/user_management/models.py

# (Optionally re-export them under __all__)
__all__ = ['Role', 'User', 'Privilege']
