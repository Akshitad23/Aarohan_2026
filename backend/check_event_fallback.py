"""Check the Windows event fallback before opening it to the venue LAN."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
env_file = Path(os.getenv("AAROHAN_ENV_FILE", BACKEND / ".env.event"))
if not env_file.is_absolute():
    env_file = (Path.cwd() / env_file).resolve()
if not env_file.is_file():
    raise SystemExit(f"Fallback environment file not found: {env_file}")
load_dotenv(env_file, override=True)

required = ("DATABASE_URL", "ADMIN_PASSWORD", "GROQ_API_KEY")
missing = [name for name in required if not os.getenv(name, "").strip()]
if missing:
    raise SystemExit("Set the missing values in the fallback environment file: " + ", ".join(missing))
if os.getenv("REQUIRE_DATABASE_URL", "").lower() != "true":
    raise SystemExit("Set REQUIRE_DATABASE_URL=true to prevent accidental SQLite startup.")

from urllib.parse import urlparse

database_url = urlparse(os.environ["DATABASE_URL"])
if database_url.scheme not in ("postgres", "postgresql") or not database_url.hostname:
    raise SystemExit("DATABASE_URL must be the shared Neon PostgreSQL connection string.")
if not database_url.hostname.endswith("neon.tech"):
    raise SystemExit("DATABASE_URL is not a Neon host. Use the event's production Neon URL.")

catalog_path = os.getenv("CIPHER_CATALOG_PATH", "").strip()
catalog_json = os.getenv("CIPHER_CATALOG_JSON", "").strip()
if bool(catalog_path) == bool(catalog_json):
    raise SystemExit("Configure exactly one private cipher catalog source.")
if catalog_path and not Path(catalog_path).is_file():
    raise SystemExit("The private cipher catalog file is missing: " + catalog_path)

from ciphers import get_challenge
get_challenge("organizer-fallback-preflight")

from logger_db import connect, storage_kind
if storage_kind() != "postgres":
    raise SystemExit("The fallback is not configured for Postgres; refusing to start.")
try:
    with connect() as connection:
        connection.execute("SELECT 1").fetchone()
except Exception as error:
    raise SystemExit("Could not connect to the shared Neon database (" + type(error).__name__ + ").") from None

print("Fallback ready: private catalog valid; shared Neon database reachable; organizer and Groq credentials configured.")
if os.getenv("OLLAMA_BACKUP_URL", "").strip():
    print("Local Ollama backup is configured. Verify its model is running before relying on it.")
else:
    print("No local Ollama backup configured; Groq is the only model provider on this laptop.")
