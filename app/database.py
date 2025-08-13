# app/database.py
from flask import g, current_app
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

class DatabaseManager:
    _engine_cache = {}
    
    @classmethod
    def get_tenant_engine(cls, hospital):
        """Get or create engine for a hospital"""
        cache_key = f"engine_{hospital.id}"
        
        if cache_key not in cls._engine_cache:
            cls._engine_cache[cache_key] = create_engine(
                hospital.db_uri,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            current_app.logger.info(f"Created engine for {hospital.name}")
            
        return cls._engine_cache[cache_key]
    
    @classmethod
    def init_app(cls, app):
        """Initialize the database manager with the app"""
        pass

def get_db_session():
    """Get the current database session"""
    if 'db_session' not in g:
        if 'hospital' in g:
            engine = DatabaseManager.get_tenant_engine(g.hospital)
            g.db_session = scoped_session(sessionmaker(bind=engine))
        else:
            # Fallback to default session
            from app.extensions import db
            g.db_session = db.session
    
    return g.db_session

def close_db_session(e=None):
    """Close the database session at the end of the request"""
    session = g.pop('db_session', None)
    if session is not None:
        session.remove()