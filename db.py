import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_NAME = os.getenv("DB_NAME", "job_finder")

def get_admin_connection():
    """Connect to default 'postgres' database to check/create target database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database="postgres"
    )

def get_connection():
    """Connect to the target database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def create_database_if_not_exists():
    """Ensure the target database exists in PostgreSQL."""
    conn = get_admin_connection()
    conn.autocommit = True
    cursor = conn.cursor()
    
    try:
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;", (DB_NAME,))
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Database '{DB_NAME}' does not exist. Creating...")
            # Execute CREATE DATABASE using safe SQL formatting
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
            print(f"Database '{DB_NAME}' created successfully.")
        else:
            print(f"Database '{DB_NAME}' already exists.")
            
    except Exception as e:
        print(f"Error checking/creating database: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

def run_migrations():
    """Read schema.sql and apply it to the target database."""
    create_database_if_not_exists()
    
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")
        
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    conn = get_connection()
    conn.autocommit = True
    cursor = conn.cursor()
    
    try:
        print("Executing schema migrations...")
        cursor.execute(schema_sql)
        print("Schema migrations applied successfully.")
    except Exception as e:
        print(f"Error running migrations: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # If run directly, verify connection and execute migrations
    print("Testing connection and initializing database...")
    try:
        run_migrations()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Initialization failed: {e}")
