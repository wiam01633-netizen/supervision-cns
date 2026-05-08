from flask import Flask, send_from_directory
from flask_socketio import SocketIO
import random, time, threading
import psycopg2

app = Flask(__name__, static_folder="frontend")
conn = psycopg2.connect(
    host="localhost",
    database="supervision_cns",
    user="postgres",
    password="admin123"
)

cursor = conn.cursor()
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("frontend", path)

systems = [
    "VOR FES",
    "ILS RWY 18",
    "DME FES",
    "RADAR APPROACH"
]

def generate_data():
    while True:
        try:
            time.sleep(3)
            system = random.choice(systems)
            status = random.choices(
                ["OK", "ALARM", "FAULT"],       # ✅ Majuscules comme dans models.py
                weights=[0.7, 0.2, 0.1]
            )[0]

            # ✅ Insérer dans etats (pas alarmes)
            cursor.execute(
                """INSERT INTO etats (systeme_id, etat, valeur_brute, timestamp)
                   VALUES (%s, %s, %s, NOW())""",
                (systems.index(system) + 1, status, system)
            )

            # ✅ Insérer alarme seulement si nécessaire, avec les bonnes colonnes
            if status in ["ALARM", "FAULT"]:
                cursor.execute(
                    """INSERT INTO alarmes (systeme_id, systeme_nom, type_alarme, acquitte)
                       VALUES (%s, %s, %s, FALSE)""",
                    (systems.index(system) + 1, system, "Détection automatique")
                )
            conn.commit()

        except Exception as e:
            print("ERROR:", e)
            conn.rollback()   # ✅ Important : rollback en cas d'erreur

# Ajouter à la fin de app.py
if __name__ == "__main__": 
    thread = threading.Thread(target=generate_data, daemon=True)
thread.start() 
socketio.run(app, port=5001) # ✅ Changer 5000 → 5001