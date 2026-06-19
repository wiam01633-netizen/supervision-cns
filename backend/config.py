from dotenv import load_dotenv
import os
 
load_dotenv()  # Charge le fichier .env automatiquement
 
# ── Base de données ──
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_NAME     = os.getenv("DB_NAME",     "supervision_cns")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin123")
DB_PORT     = os.getenv("DB_PORT",     "5432")
 
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
 
# ── Sécurité JWT ──
SECRET_KEY     = os.getenv("SECRET_KEY",     "change_moi_en_production")
ALGORITHM      = os.getenv("ALGORITHM",      "HS256")
EXPIRE_MINUTES = int(os.getenv("EXPIRE_MINUTES", "60"))
 
# ── Admin ──
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
 
# ── CORS ──
_origins_str = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5500,http://127.0.0.1:5500"
)
CORS_ORIGINS = [o.strip() for o in _origins_str.split(",")]