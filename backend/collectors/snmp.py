# collectors/snmp.py
# Version simulation - sans équipement réel
import random

def collecter_snmp(adresse_ip, oid='', communaute='public'):
    """
    Simule une collecte SNMP
    À remplacer par la vraie collecte quand vous aurez les équipements
    """
    etats = ["OK", "OK", "OK", "ALARM", "FAULT"]
    return {
        "etat": random.choice(etats),
        "valeur": "simulation"
    }