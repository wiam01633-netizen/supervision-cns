# collectors/serial.py — Collecteur RS-232 VHF COM 1
# Mode simulation si pas de port série disponible
import os

PORT_SERIE = os.getenv("SERIAL_PORT", None)   # None = simulation
BAUDRATE   = 9600
COMMANDE   = 'STATUS\r\n'

def collecter_serie(port=None, baudrate=9600, commande='STATUS\r\n'):
    """
    Interroge VHF COM 1 via RS-232
    Si PORT_SERIE non configuré → simulation automatique
    """
    port = port or PORT_SERIE

    # ── Mode simulation ──
    if not port:
        from collectors.serial_simulator import collecter_serie_simule
        return collecter_serie_simule()

    # ── Mode réel ──
    try:
        import serial
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=2)
        ser.write(commande.encode('utf-8'))
        reponse = ser.readline().decode('utf-8').strip()
        ser.close()
        return {
            "etat":   normaliser_serie(reponse),
            "valeur": reponse,
            "source": "serial"
        }
    except Exception as e:
        return {"etat": "FAULT", "valeur": str(e), "source": "serial_error"}

def normaliser_serie(reponse):
    reponse = reponse.upper()
    if "OK" in reponse or "NORMAL" in reponse:   return "OK"
    elif "ALARM" in reponse or "FAIL" in reponse: return "ALARM"
    elif "FAULT" in reponse:                       return "FAULT"
    else:                                          return "UNKNOWN"