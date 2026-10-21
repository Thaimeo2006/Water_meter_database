from urllib.parse import quote_plus
import sys

def update_database_url(new_password: str):
    with open("password/database_url.txt", "w") as f:
        f.write(f"mssql+pyodbc://sa:{quote_plus(new_password)}@127.0.0.1:1433/Meter"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            "&TrustServerCertificate=yes"
        )

with open("password/database_password.txt", "r") as f:
    password = f.read().strip()     

if len(sys.argv) >= 2:
    new_password = sys.argv[1]
    if len(new_password) > 0:
        password = new_password
        with open("password/database_password.txt", "w") as f:
            f.write(new_password)

update_database_url(password)