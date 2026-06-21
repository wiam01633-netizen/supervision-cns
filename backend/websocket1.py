# websocket1.py
import psycopg2
from datetime import datetime

def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="supervision_cns",
        user="postgres",
        password="admin123"
    )

SYSTEMES = {
    1: {"nom": "VOR",       "type": "Navigation",    "interface": "SNMP"},
    2: {"nom": "Localiser", "type": "Navigation",    "interface": "SNMP"},
    3: {"nom": "DME VOR",   "type": "Navigation",    "interface": "SNMP"},
    4: {"nom": "DME Glide", "type": "Navigation",    "interface": "SNMP"},
    5: {"nom": "VHF COM 1", "type": "Communication", "interface": "RS-232"},
    6: {"nom": "ADS-B",     "type": "Surveillance",  "interface": "SNMP"},
    7: {"nom": "Glide",     "type": "Navigation",    "interface": "SNMP"},
}

async def collecter_tous_systemes():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
    SELECT DISTINCT ON (systeme_id)
        systeme_id, etat, timestamp
    FROM etats
    WHERE systeme_id IN (1, 2, 3, 4, 5, 6, 7)
    ORDER BY systeme_id, timestamp DESC
""")

        rows = cursor.fetchall()
        conn.close()

        resultats = []
        # ✅ row[0]=systeme_id, row[1]=etat, row[2]=timestamp
        for row in rows:
            sys_id    = row[0]
            etat      = row[1]
            timestamp = row[2]

            if sys_id in SYSTEMES:
                info = SYSTEMES[sys_id]
                resultats.append({
                    "id":        sys_id,
                    "nom":       info["nom"],
                    "type":      info["type"],
                    "interface": info["interface"],
                    "etat":      etat,
                    "timestamp": timestamp.strftime("%H:%M:%S")
                })

        return resultats

    except Exception as e:
        print(f"❌ Erreur websocket1: {e}")
        return [
            {
                "id":        sys_id,
                "nom":       info["nom"],
                "type":      info["type"],
                "interface": info["interface"],
                "etat":      "UNKNOWN",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            for sys_id, info in SYSTEMES.items()
        ]