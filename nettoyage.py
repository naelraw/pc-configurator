import libsql_client as libsql
import os
from dotenv import load_dotenv

load_dotenv()

client = libsql.create_client_sync(
    url=os.getenv("TURSO_DATABASE_URL"),
    auth_token=os.getenv("TURSO_AUTH_TOKEN"),
)

client.execute("DELETE FROM components WHERE categorie = 'TEST'")
print("✅ Lignes TEST supprimées")

result = client.execute("SELECT * FROM components")
for row in result.rows:
    print(row)

client.close()