# websocket.py
from datetime import datetime
import random

SYSTEMES = [
    {"id": 1, "nom": "VOR",       "type": "Navigation",    "interface": "SNMP"},
    {"id": 2, "nom": "ILS LOC",   "type": "Navigation",    "interface": "SNMP"},
    {"id": 3, "nom": "DME",       "type": "Navigation",    "interface": "TCP/IP"},
    {"id": 5, "nom": "VHF COM 1", "type": "Communication", "interface": "I/O"},
    {"id": 7, "nom": "ILS GLIDE", "type": "Navigation",    "interface": "SNMP"},
    
]

async def collecter_tous_systemes():
    etats_possibles = ["OK", "OK", "OK", "ALARM", "FAULT"]
    resultats = []
    for sys in SYSTEMES:
        resultats.append({
            "id":        sys["id"],
            "nom":       sys["nom"],
            "type":      sys["type"],
            "interface": sys["interface"],
            "etat":      random.choice(etats_possibles),
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
    return resultats