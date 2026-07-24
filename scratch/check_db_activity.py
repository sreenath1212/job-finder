from db import get_connection

def check_activity():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT pid, query, state, age(clock_timestamp(), query_start) FROM pg_stat_activity WHERE state != 'idle';")
    rows = cur.fetchall()
    print("--- Active PG Sessions ---")
    for r in rows:
        print(r)
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_activity()
