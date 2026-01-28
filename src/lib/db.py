"""Database connection utilities for Federal Court scraper.

This module provides database connection functionality using psycopg2.
"""

import psycopg2
from typing import Optional
from .config import Config


def get_connection():
    """Get a database connection using configuration.
    
    Returns:
        psycopg2 connection object
        
    Raises:
        psycopg2.Error: If connection fails
    """
    db_config = Config.get_db_config()
    
    conn = psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"]
    )
    
    return conn


def test_connection() -> tuple[bool, Optional[str]]:
    """Test database connection.
    
    Returns:
        Tuple of (success, error_message)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)
