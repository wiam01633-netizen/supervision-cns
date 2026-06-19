# collectors/serial_simulator.py
# Simule un équipement VHF COM 1 via RS-232
import random

_etat_actuel = {"etat": "OK", "cycles": 0}

def collecter_serie_simule(fiabilite=0.92):
    """
    Simule la réponse RS-232 du VHF COM 1
    Retourne même structure que serial.py réel
    """
    global _etat_actuel

    if _etat_actuel["cycles"] > 0:
        _etat_actuel["cycles"] -= 1
        reponse = _etat_actuel["etat"]
    else:
        if random.random() > fiabilite:
            etat   = random.choice(["ALARM", "FAULT"])
            duree  = random.randint(3, 8)
            _etat_actuel["etat"]   = etat
            _etat_actuel["cycles"] = duree
            reponse = etat
        else:
            _etat_actuel["etat"]   = "OK"
            _etat_actuel["cycles"] = 0
            reponse = "OK"

    return {
        "etat":   reponse,
        "valeur": f"RS232|VHF_COM_1|{reponse}",
        "source": "simulation"
    }