# inserter.py — Version finale : SNMP (navigation) + RS-232 (VHF COM 1)
import psycopg2
import random
import time
from datetime import datetime
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

conn = psycopg2.connect(
    host=DB_HOST, database=DB_NAME,
    user=DB_USER, password=DB_PASSWORD
)
cursor = conn.cursor()

# ════════════════════════════════════════════════════════
# SYSTÈMES CNS — 2 protocoles différents
# ════════════════════════════════════════════════════════
SYSTEMES_SNMP = [
    # Systèmes de navigation → protocole SNMP
    {"id": 1, "nom": "VOR",       "protocole": "SNMP", "frequence": 113.6, "signal_nominal": -65, "fiabilite": 0.97, "duree_panne": (3, 8),  "type_panne": ["ALARM"]},
    {"id": 2, "nom": "Localiser", "protocole": "SNMP", "frequence": 108.9, "signal_nominal": -70, "fiabilite": 0.97, "duree_panne": (3, 8),  "type_panne": ["ALARM", "FAULT"]},
    {"id": 3, "nom": "DME VOR",   "protocole": "SNMP", "frequence": 50.0,  "signal_nominal": -60, "fiabilite": 0.98, "duree_panne": (2, 5),  "type_panne": ["ALARM"]},
    {"id": 4, "nom": "DME Glide", "protocole": "SNMP", "frequence": 50.0,  "signal_nominal": -60, "fiabilite": 0.98, "duree_panne": (2, 5),  "type_panne": ["ALARM"]},
    {"id": 6, "nom": "ADS-B",     "protocole": "SNMP", "frequence": 1090.0, "signal_nominal": -68, "fiabilite": 0.96, "duree_panne": (2, 6), "type_panne": ["ALARM", "FAULT"]},
    {"id": 7, "nom": "Glide",     "protocole": "SNMP", "frequence": 329.9, "signal_nominal": -72, "fiabilite": 0.97, "duree_panne": (3, 8),  "type_panne": ["ALARM", "FAULT"]},
]

SYSTEME_RS232 = {
    # VHF COM 1 → protocole RS-232
    "id": 5, "nom": "VHF COM 1", "protocole": "RS-232",
    "fiabilite": 0.92, "duree_panne": (3, 8),
    "type_panne": ["ALARM", "FAULT"]
}

# États actuels de tous les systèmes
tous_systemes = SYSTEMES_SNMP + [SYSTEME_RS232]
etats_actuels = {
    sys["id"]: {"etat": "OK", "cycles_restants": 0}
    for sys in tous_systemes
}

# ════════════════════════════════════════════════════════
# SIMULATION SNMP — équipements de navigation
# Simule ce qu'un vrai agent SNMP retournerait
# ════════════════════════════════════════════════════════
def collecter_snmp(sys, etat):
    """
    Simule la collecte SNMP d'un équipement de navigation
    Retourne état + niveau signal + fréquence
    """
    # Signal varie selon l'état
    if etat == "OK":
        signal = sys["signal_nominal"] + random.uniform(-3, 3)
    elif etat == "ALARM":
        signal = sys["signal_nominal"] + random.uniform(-20, -10)
    else:  # FAULT
        signal = sys["signal_nominal"] + random.uniform(-40, -25)

    valeur_brute = f"SNMP|OID:1.3.6.1.4.1.99999|signal:{signal:.1f}dBm|freq:{sys['frequence']}MHz"

    return {
        "etat":        etat,
        "signal":      round(signal, 1),
        "frequence":   sys["frequence"],
        "valeur_brute": valeur_brute,
        "protocole":   "SNMP"
    }

# ════════════════════════════════════════════════════════
# SIMULATION RS-232 — VHF COM 1
# Simule ce qu'un vrai port série retournerait
# ════════════════════════════════════════════════════════
def collecter_rs232(etat):
    """
    Simule la collecte RS-232 du VHF COM 1
    Reproduit la réponse à la commande STATUS
    """
    # Réponses typiques d'un équipement VHF COM réel
    reponses = {
        "OK":    "OK|PWR:+48V|TX:ON|RX:ON|VSWR:1.2",
        "ALARM": "ALARM|PWR:+45V|TX:DEGRADED|RX:ON|VSWR:2.1",
        "FAULT": "FAULT|PWR:+40V|TX:OFF|RX:OFF|VSWR:3.5"
    }

    reponse_brute = reponses.get(etat, "UNKNOWN")
    valeur_brute  = f"RS232|CMD:STATUS|REP:{reponse_brute}"

    return {
        "etat":        etat,
        "reponse":     reponse_brute,
        "valeur_brute": valeur_brute,
        "protocole":   "RS-232"
    }

# ════════════════════════════════════════════════════════
# LIRE PRÉDICTIONS IA
# ════════════════════════════════════════════════════════
def lire_predictions():
    try:
        cursor.execute("""
            SELECT DISTINCT ON (systeme_id)
                systeme_id, probabilite, niveau
            FROM predictions
            ORDER BY systeme_id, timestamp DESC
        """)
        return {
            row[0]: {"proba": float(row[1]), "niveau": row[2]}
            for row in cursor.fetchall()
        }
    except:
        return {}

def fiabilite_ajustee(sys, predictions):
    fiabilite = sys["fiabilite"]
    pred = predictions.get(sys["id"])
    if not pred: return fiabilite
    proba = pred["proba"]
    if proba >= 0.75:   fiabilite -= 0.10
    elif proba >= 0.50: fiabilite -= 0.04
    elif proba < 0.25:  fiabilite = min(fiabilite + 0.002, 0.999)
    return max(0.5, min(0.999, fiabilite))

# ════════════════════════════════════════════════════════
# GESTION ALARMES
# ════════════════════════════════════════════════════════
def gerer_alarme(sys_id, nom, etat, type_alarme):
    cursor.execute(
        "SELECT id FROM alarmes WHERE systeme_id = %s AND acquitte = FALSE",
        (sys_id,)
    )
    alarme_existante = cursor.fetchone()

    if etat in ["ALARM", "FAULT"]:
        if not alarme_existante:
            cursor.execute(
                "INSERT INTO alarmes (systeme_id, type_alarme, acquitte, debut) VALUES (%s, %s, FALSE, NOW())",
                (sys_id, type_alarme)
            )
            print(f"   🆕 Alarme : {nom} → {etat}")
    else:
        if alarme_existante:
            cursor.execute(
                "UPDATE alarmes SET fin = NOW() WHERE systeme_id = %s AND acquitte = FALSE",
                (sys_id,)
            )
            print(f"   ✅ OK : {nom}")

# ════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ════════════════════════════════════════════════════════
print("✅ Simulation démarrée — Multi-protocoles")
print("   Navigation (VOR, Localiser, DME, Glide) → SNMP simulé")
print("   VHF COM 1                               → RS-232 simulé\n")

cycle       = 0
predictions = lire_predictions()

while True:
    try:
        cycle += 1

        # Recharger prédictions toutes les 5min
        if cycle % 30 == 0:
            predictions = lire_predictions()

        print(f"\n── Cycle {cycle} — {datetime.now().strftime('%H:%M:%S')} ──")

        # ── SYSTÈMES SNMP (navigation) ──
        for sys in SYSTEMES_SNMP:
            sys_id      = sys["id"]
            etat_actuel = etats_actuels[sys_id]
            fiabilite   = fiabilite_ajustee(sys, predictions)

            # Logique état
            if etat_actuel["cycles_restants"] > 0:
                etat = etat_actuel["etat"]
                etat_actuel["cycles_restants"] -= 1
                if etat_actuel["cycles_restants"] == 1 and etat == "FAULT":
                    etat = "ALARM"
            else:
                if random.random() > fiabilite:
                    etat  = random.choice(sys["type_panne"])
                    duree = random.randint(*sys["duree_panne"])
                    etat_actuel["cycles_restants"] = duree
                    etat_actuel["etat"]            = etat
                    print(f"   ⚠️  PANNE SNMP : {sys['nom']} → {etat}")
                else:
                    etat                = "OK"
                    etat_actuel["etat"] = "OK"

            # Collecter via SNMP simulé
            resultat = collecter_snmp(sys, etat)

            # INSERT état avec valeur SNMP
            cursor.execute(
                "INSERT INTO etats (systeme_id, etat, valeur_brute, timestamp) VALUES (%s, %s, %s, NOW())",
                (sys_id, etat, resultat["valeur_brute"])
            )

            # Gérer alarme
            gerer_alarme(
                sys_id, sys["nom"], etat,
                f"SNMP Trap - {etat} | signal:{resultat['signal']}dBm"
            )

            print(f"   📡 SNMP {sys['nom']:<12} → {etat:<6} | {resultat['signal']}dBm | {sys['frequence']}MHz")

        # ── VHF COM 1 → RS-232 ──
        sys        = SYSTEME_RS232
        sys_id     = sys["id"]
        etat_actuel = etats_actuels[sys_id]
        fiabilite  = fiabilite_ajustee(sys, predictions)

        if etat_actuel["cycles_restants"] > 0:
            etat = etat_actuel["etat"]
            etat_actuel["cycles_restants"] -= 1
            if etat_actuel["cycles_restants"] == 1 and etat == "FAULT":
                etat = "ALARM"
        else:
            if random.random() > fiabilite:
                etat  = random.choice(sys["type_panne"])
                duree = random.randint(*sys["duree_panne"])
                etat_actuel["cycles_restants"] = duree
                etat_actuel["etat"]            = etat
                print(f"   ⚠️  PANNE RS-232 : {sys['nom']} → {etat}")
            else:
                etat                = "OK"
                etat_actuel["etat"] = "OK"

        # Collecter via RS-232 simulé
        resultat = collecter_rs232(etat)

        # INSERT état avec valeur RS-232
        cursor.execute(
            "INSERT INTO etats (systeme_id, etat, valeur_brute, timestamp) VALUES (%s, %s, %s, NOW())",
            (sys_id, etat, resultat["valeur_brute"])
        )

        # Gérer alarme
        gerer_alarme(
            sys_id, sys["nom"], etat,
            f"RS-232 - {etat} | {resultat['reponse']}"
        )

        print(f"   🔌 RS232 {sys['nom']:<12} → {etat:<6} | {resultat['reponse']}")

        conn.commit()

        # Résumé toutes les 60s
        if cycle % 6 == 0:
            cursor.execute("SELECT COUNT(*) FROM alarmes WHERE acquitte = FALSE")
            nb = cursor.fetchone()[0]
            print(f"\n   📊 Alarmes actives : {nb}")

        time.sleep(10)

    except Exception as e:
        print(f"❌ Erreur : {e}")
        conn.rollback()
        time.sleep(10)