from supabase import create_client, Client
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Client = None
supabase_admin: Client = None

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    logger.info("Supabase connected successfully")
except Exception as e:
    logger.error(f"Supabase init failed: {e}")

def init_db():
    """Tables are already created via SQL in Supabase dashboard - this is a no-op"""
    logger.info("Database tables should exist in Supabase")
    pass

def _ensure_connected():
    """Lazy init - only connect on first DB call"""
    global supabase, supabase_admin
    if supabase_admin is None:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("Supabase connected")
        except Exception as e:
            logger.error(f"Supabase init failed: {e}")
            raise
            

class DB:
    """Database helper class using Supabase client"""
    
    @staticmethod
    def insert(table: str, data: Dict) -> Optional[Dict]:
        """Insert and return row"""
        _ensure_connected()
        try:
            result = supabase_admin.table(table).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            return None
    
    @staticmethod
    def find_one(table: str, where: Dict) -> Optional[Dict]:
        """Find one row"""
        _ensure_connected()
        try:
            query = supabase_admin.table(table).select('*')
            for key, value in where.items():
                query = query.eq(key, value)
            result = query.single().execute()
            return result.data if result.data else None
        except Exception as e:
            logger.error(f"Find one failed: {e}")
            return None
    
    @staticmethod
    def find_many(table: str, where: Dict = None, order_by: str = None, limit: int = None) -> List[Dict]:
        """Find many rows"""
        _ensure_connected()
        try:
            query = supabase_admin.table(table).select('*')
            
            if where:
                for key, value in where.items():
                    query = query.eq(key, value)
            
            if order_by:
                # Parse order_by string like "created_at DESC"
                parts = order_by.split()
                column = parts[0]
                ascending = len(parts) == 1 or parts[1].upper() == 'ASC'
                query = query.order(column, desc=not ascending)
            
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Find many failed: {e}")
            return []
    
    @staticmethod
    def update(table: str, where: Dict, data: Dict) -> bool:
        """Update rows"""
        _ensure_connected()
        try:
            query = supabase_admin.table(table).update(data)
            for key, value in where.items():
                query = query.eq(key, value)
            query.execute()
            return True
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False
    
    @staticmethod
    def query(sql: str, params: List = None) -> List[Dict]:
        """
        _ensure_connected()
        Execute raw SQL via RPC function
        Note: For complex queries, you may need to create custom RPC functions in Supabase
        """
        logger.warning("Raw SQL queries not directly supported with Supabase client. Use RPC functions instead.")
        return []
db_instance = DB()
# Initialize on import (but it's a no-op now)
init_db()
