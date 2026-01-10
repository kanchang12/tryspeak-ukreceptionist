import psycopg2
from psycopg2.extras import RealDictCursor
import os

# CockroachDB connection string
DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """Create tables if they don't exist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Signups table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255),
            email VARCHAR(255),
            phone_number VARCHAR(20),
            business_name VARCHAR(255),
            business_type VARCHAR(50),
            message TEXT,
            referral_code_used VARCHAR(50),
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Onboarding calls table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            signup_email VARCHAR(255),
            signup_phone VARCHAR(20),
            signup_name VARCHAR(255),
            business_type VARCHAR(50),
            vapi_call_id VARCHAR(255),
            call_started_at TIMESTAMP,
            call_ended_at TIMESTAMP,
            call_duration INT,
            full_transcript TEXT,
            recording_url TEXT,
            status VARCHAR(20),
            reviewed_at TIMESTAMP,
            reviewed_by VARCHAR(255),
            business_owner_id UUID,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Business owners table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS business_owners (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE,
            phone_number VARCHAR(20),
            business_name VARCHAR(255),
            business_type VARCHAR(50),
            vapi_assistant_id VARCHAR(255),
            vapi_phone_number VARCHAR(20),
            onboarding_transcript TEXT,
            referral_code VARCHAR(50),
            status VARCHAR(20),
            ai_enabled BOOLEAN DEFAULT TRUE,
            plan VARCHAR(20) DEFAULT 'starter',
            monthly_price DECIMAL(10,2) DEFAULT 75.00,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Their customers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS their_customers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            business_owner_id UUID,
            phone_number VARCHAR(20),
            name VARCHAR(255),
            email VARCHAR(255),
            total_calls INT DEFAULT 0,
            customer_type VARCHAR(20) DEFAULT 'new',
            last_contact TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(business_owner_id, phone_number)
        )
    """)
    
    # Interactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            business_owner_id UUID,
            customer_id UUID,
            type VARCHAR(50),
            channel VARCHAR(20),
            caller_phone VARCHAR(20),
            call_duration INT,
            recording_url TEXT,
            transcript TEXT,
            summary TEXT,
            is_emergency BOOLEAN DEFAULT FALSE,
            priority VARCHAR(20) DEFAULT 'normal',
            status VARCHAR(20),
            scheduled_datetime TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Referrals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            referrer_id UUID,
            referee_email VARCHAR(255),
            referee_id UUID,
            referral_code VARCHAR(50),
            status VARCHAR(20) DEFAULT 'pending',
            referrer_credit_amount DECIMAL(10,2) DEFAULT 25.00,
            referee_discount_amount DECIMAL(10,2) DEFAULT 25.00,
            referrer_credit_applied BOOLEAN DEFAULT FALSE,
            referee_discount_applied BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            UNIQUE(referrer_id, referee_email)
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

class DB:
    """Database helper class"""
    
    @staticmethod
    def insert(table, data):
        """Insert and return row"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = list(data.values())
        
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, values)
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return dict(result) if result else None
    
    @staticmethod
    def find_one(table, where):
        """Find one row"""
        conditions = ' AND '.join([f"{k} = %s" for k in where.keys()])
        values = list(where.values())
        
        sql = f"SELECT * FROM {table} WHERE {conditions} LIMIT 1"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, values)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return dict(result) if result else None
    
    @staticmethod
    def find_many(table, where=None, order_by=None, limit=None):
        """Find many rows"""
        sql = f"SELECT * FROM {table}"
        values = []
        
        if where:
            conditions = ' AND '.join([f"{k} = %s" for k in where.keys()])
            sql += f" WHERE {conditions}"
            values = list(where.values())
        
        if order_by:
            sql += f" ORDER BY {order_by}"
        
        if limit:
            sql += f" LIMIT {limit}"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, values)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return [dict(r) for r in results]
    
    @staticmethod
    def update(table, where, data):
        """Update rows"""
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        where_clause = ' AND '.join([f"{k} = %s" for k in where.keys()])
        values = list(data.values()) + list(where.values())
        
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
    
    @staticmethod
    def query(sql, params=None):
        """Execute raw SQL"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        
        if sql.strip().upper().startswith('SELECT'):
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return [dict(r) for r in results]
        else:
            conn.commit()
            cursor.close()
            conn.close()

# Initialize on import
init_db()
