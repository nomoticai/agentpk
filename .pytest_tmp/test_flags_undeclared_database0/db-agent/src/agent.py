import psycopg2

def main():
    conn = psycopg2.connect("dbname=test")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    return cur.fetchall()

if __name__ == "__main__":
    main()
