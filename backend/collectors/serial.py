# collectors/serial.py
import serial

def collecter_serie(port, baudrate=9600, commande='STATUS\r\n'):
    """
    Interroge un équipement via RS-232 ou RS-485
    """
    try:
        ser = serial.Serial(
            port=port,          # ex: 'COM3' sur Windows ou '/dev/ttyUSB0' sur Linux
            baudrate=baudrate,
            timeout=2
        )
        # Envoie la commande à l'équipement
        ser.write(commande.encode('utf-8'))

        # Lit la réponse
        reponse = ser.readline().decode('utf-8').strip()
        ser.close()

        return {
            "etat": normaliser_serie(reponse),
            "valeur": reponse
        }

    except serial.SerialException as e:
        return {"etat": "FAULT", "valeur": str(e)}


def normaliser_serie(reponse):
    reponse = reponse.upper()
    if "OK" in reponse or "NORMAL" in reponse:
        return "OK"
    elif "ALARM" in reponse or "FAIL" in reponse:
        return "ALARM"
    else:
        return "UNKNOWN"