# inserter.py
import psycopg2
import random
import time

conn = psycopg2.connect(
    host="localhost",
    database="supervision_cns",
    user="postgres",
    password="admin123"
)
cursor = conn.cursor()

systemes = [
    (1, "VOR"),
    (2, "ILS LOC"),
    (3, "DME"),
    (5, "VHF COM 1"),
    (7, "ILS GLIDE"),
    
]

print("✅ Synchronisation démarrée... (Ctrl+C pour arrêter)")

while True:
    try:
        for systeme_id, systeme_nom in systemes:
            etat = random.choices(
                ["OK", "OK", "OK", "ALARM", "FAULT"],
                weights=[0.6, 0.1, 0.1, 0.1, 0.1]
            )[0]

            # ✅ 1. Insérer l'état dans etats
            cursor.execute(
                """INSERT INTO etats (systeme_id, etat, valeur_brute, timestamp)
                   VALUES (%s, %s, %s, NOW())""",
                (systeme_id, etat, systeme_nom)
            )

            # ✅ 2. Vérifier si alarme active existe déjà pour ce système
            cursor.execute(
                """SELECT id FROM alarmes 
                   WHERE systeme_id = %s AND acquitte = FALSE""",
                (systeme_id,)
            )
            alarme_existante = cursor.fetchone()

            if etat in ["ALARM", "FAULT"]:
                if not alarme_existante:
                    # ✅ Créer alarme seulement si pas déjà active
                    cursor.execute(
                         """INSERT INTO alarmes (systeme_id, type_alarme, acquitte)
                         VALUES (%s, %s, FALSE)""",
                         (systeme_id, f"Détection automatique - {etat}")
                    )
                    print(f"🆕 Nouvelle alarme : {systeme_nom} → {etat}")
                else:
                    print(f"⚠️  Alarme déjà active : {systeme_nom} → {etat}")

            else:
                if alarme_existante:
                    # ✅ Système revenu OK → clôturer l'alarme automatiquement
                    cursor.execute(
                        """UPDATE alarmes 
                           SET acquitte = TRUE, fin = NOW()
                           WHERE systeme_id = %s AND acquitte = FALSE""",
                        (systeme_id,)
                    )
                    print(f"✅ Alarme clôturée : {systeme_nom} → revenu OK")
                else:
                    print(f"✅ {systeme_nom} → OK")

        conn.commit()

        # ✅ 3. Afficher le résumé synchronisé
        cursor.execute("SELECT COUNT(*) FROM alarmes WHERE acquitte = FALSE")
        total = cursor.fetchone()[0]
        print(f"\n📊 Alarmes actives en ce moment : {total}")
        print("--- Cycle terminé, attente 5s ---\n")
        time.sleep(5)

    except Exception as e:
        print(f"❌ Erreur : {e}")
        conn.rollback()
        time.sleep(10)