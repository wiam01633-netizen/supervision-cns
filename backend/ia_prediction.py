# ia_prediction.py — Version améliorée PFE
import psycopg2
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import os
import time
from datetime import datetime, timedelta

# ── Chemins des fichiers sauvegardés ──
MODEL_PATH   = "modele_ia.pkl"
SCALER_PATH  = "scaler_ia.pkl"
RETRAIN_INTERVAL = 3600   # ré-entraîner toutes les 1h (pas 30s !)
MIN_DATA_ROWS    = 200    # minimum pour entraîner

# ── Connexion PostgreSQL ──
def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="supervision_cns",
        user="postgres",
        password="admin123"
    )

# ════════════════════════════════════════════════════════
# CHARGEMENT HISTORIQUE — features enrichies
# ════════════════════════════════════════════════════════
def charger_historique():
    conn = get_conn()
    query = """
        SELECT
            e.systeme_id,
            e.etat,
            e.timestamp,
            EXTRACT(HOUR   FROM e.timestamp) AS heure,
            EXTRACT(DOW    FROM e.timestamp) AS jour_semaine,
            EXTRACT(MINUTE FROM e.timestamp) AS minute,
            -- Nombre d'alarmes actives sur le même système dans les 30 dernières minutes
            (
                SELECT COUNT(*) FROM alarmes a
                WHERE a.systeme_id = e.systeme_id
                  AND a.debut >= e.timestamp - INTERVAL '30 minutes'
                  AND a.debut <= e.timestamp
            ) AS nb_alarmes_recentes,
            -- Durée moyenne des pannes passées sur ce système (en secondes)
            (
                SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (fin - debut))), 0)
                FROM alarmes a
                WHERE a.systeme_id = e.systeme_id
                  AND a.fin IS NOT NULL
                  AND a.debut >= NOW() - INTERVAL '24 hours'
            ) AS duree_moy_panne
        FROM etats e
        ORDER BY e.timestamp DESC
        LIMIT 20000
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# ════════════════════════════════════════════════════════
# PRÉPARATION FEATURES — fenêtre glissante enrichie
# ════════════════════════════════════════════════════════
def preparer_features(df):
    features = []
    labels   = []
    FENETRE  = 10   # 10 derniers états

    systemes = df['systeme_id'].unique()

    for sys_id in systemes:
        df_sys = df[df['systeme_id'] == sys_id].copy()
        df_sys = df_sys.sort_values('timestamp').reset_index(drop=True)

        if len(df_sys) < FENETRE + 1:
            continue

        for i in range(FENETRE, len(df_sys)):
            fenetre = df_sys.iloc[i - FENETRE:i]
            courant = df_sys.iloc[i]

            # ── Features de base ──
            nb_alarm = (fenetre['etat'] == 'ALARM').sum()
            nb_fault = (fenetre['etat'] == 'FAULT').sum()
            nb_ok    = (fenetre['etat'] == 'OK').sum()
            taux_alarme = (nb_alarm + nb_fault) / FENETRE

            # ── Features temporelles ──
            heure        = float(courant['heure'])
            jour_semaine = float(courant['jour_semaine'])
            minute       = float(courant['minute'])

            # ── Heure creuse / heure de pointe (nuit vs jour) ──
            heure_creuse = 1 if (heure >= 22 or heure <= 5) else 0

            # ── Tendance : est-ce que ça empire ? ──
            # Comparer première moitié vs deuxième moitié de la fenêtre
            premiere_moitie = fenetre.iloc[:FENETRE//2]
            deuxieme_moitie = fenetre.iloc[FENETRE//2:]
            alarmes_1ere = ((premiere_moitie['etat'] == 'ALARM') | (premiere_moitie['etat'] == 'FAULT')).sum()
            alarmes_2eme = ((deuxieme_moitie['etat'] == 'ALARM') | (deuxieme_moitie['etat'] == 'FAULT')).sum()
            tendance_degradation = 1 if alarmes_2eme > alarmes_1ere else 0

            # ── Features enrichies (BDD) ──
            nb_alarmes_recentes = float(courant.get('nb_alarmes_recentes', 0) or 0)
            duree_moy_panne     = float(courant.get('duree_moy_panne', 0) or 0)

            # ── Consécutivité : nb de pannes d'affilée ──
            consecutif = 0
            for _, row in fenetre.iloc[::-1].iterrows():
                if row['etat'] in ['ALARM', 'FAULT']:
                    consecutif += 1
                else:
                    break

            features.append([
                float(sys_id),
                nb_alarm,
                nb_fault,
                nb_ok,
                taux_alarme,
                heure,
                jour_semaine,
                minute,
                heure_creuse,
                tendance_degradation,
                consecutif,
                nb_alarmes_recentes,
                duree_moy_panne
            ])

            # Label : le prochain état est-il une panne ?
            prochain_etat = df_sys.iloc[i]['etat']
            labels.append(1 if prochain_etat in ['ALARM', 'FAULT'] else 0)

    return np.array(features), np.array(labels)

FEATURE_NAMES = [
    "systeme_id", "nb_alarm", "nb_fault", "nb_ok", "taux_alarme",
    "heure", "jour_semaine", "minute", "heure_creuse",
    "tendance_degradation", "consecutif",
    "nb_alarmes_recentes", "duree_moy_panne"
]

# ════════════════════════════════════════════════════════
# ENTRAÎNEMENT — avec persistance joblib
# ════════════════════════════════════════════════════════
def entrainer_et_sauvegarder(features, labels):
    if len(features) < MIN_DATA_ROWS:
        print(f"⚠️  Seulement {len(features)} échantillons — minimum {MIN_DATA_ROWS} requis")
        return None, None

    # Normalisation
    scaler = StandardScaler()
    features_norm = scaler.fit_transform(features)

    # Split train/test
    X_train, X_test, y_train, y_test = train_test_split(
        features_norm, labels, test_size=0.2, random_state=42, stratify=labels
    )

    modele = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_leaf=3,
        class_weight='balanced',   # important si peu de pannes
        random_state=42,
        n_jobs=-1
    )
    modele.fit(X_train, y_train)

    # Évaluation
    y_pred = modele.predict(X_test)
    print("\n📈 Rapport de classification :")
    print(classification_report(y_test, y_pred, target_names=['OK', 'PANNE']))

    # Importance des features
    importances = modele.feature_importances_
    print("\n🔍 Importance des features :")
    for nom, imp in sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1]):
        barre = "█" * int(imp * 40)
        print(f"  {nom:<25} {barre} {imp:.3f}")

    # ✅ Sauvegarder modèle + scaler
    joblib.dump(modele, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\n✅ Modèle sauvegardé → {MODEL_PATH}")
    print(f"✅ Scaler sauvegardé  → {SCALER_PATH}")

    return modele, scaler

# ════════════════════════════════════════════════════════
# CHARGEMENT — réutiliser le modèle existant
# ════════════════════════════════════════════════════════
def charger_modele():
    if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
        modele = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
        age    = time.time() - os.path.getmtime(MODEL_PATH)
        print(f"📂 Modèle chargé (âge : {int(age/60)} min)")
        return modele, scaler, age
    return None, None, float('inf')

# ════════════════════════════════════════════════════════
# PRÉDICTION — pour chaque système
# ════════════════════════════════════════════════════════
def predire(modele, scaler, df):
    predictions = []
    FENETRE = 10
    systemes = df['systeme_id'].unique()

    for sys_id in systemes:
        df_sys = df[df['systeme_id'] == sys_id].copy()
        df_sys = df_sys.sort_values('timestamp').reset_index(drop=True)

        if len(df_sys) < FENETRE:
            continue

        fenetre = df_sys.tail(FENETRE)
        now     = datetime.now()

        nb_alarm = (fenetre['etat'] == 'ALARM').sum()
        nb_fault = (fenetre['etat'] == 'FAULT').sum()
        nb_ok    = (fenetre['etat'] == 'OK').sum()
        taux_alarme = (nb_alarm + nb_fault) / FENETRE

        heure_creuse = 1 if (now.hour >= 22 or now.hour <= 5) else 0

        alarmes_1ere = ((fenetre.iloc[:5]['etat'] == 'ALARM') | (fenetre.iloc[:5]['etat'] == 'FAULT')).sum()
        alarmes_2eme = ((fenetre.iloc[5:]['etat'] == 'ALARM') | (fenetre.iloc[5:]['etat'] == 'FAULT')).sum()
        tendance = 1 if alarmes_2eme > alarmes_1ere else 0

        consecutif = 0
        for _, row in fenetre.iloc[::-1].iterrows():
            if row['etat'] in ['ALARM', 'FAULT']:
                consecutif += 1
            else:
                break

        nb_alarmes_recentes = float(fenetre.iloc[-1].get('nb_alarmes_recentes', 0) or 0)
        duree_moy_panne     = float(fenetre.iloc[-1].get('duree_moy_panne', 0) or 0)

        feature = np.array([[
            float(sys_id), nb_alarm, nb_fault, nb_ok, taux_alarme,
            float(now.hour), float(now.weekday()), float(now.minute),
            heure_creuse, tendance, consecutif,
            nb_alarmes_recentes, duree_moy_panne
        ]])

        feature_norm = scaler.transform(feature)
        proba = modele.predict_proba(feature_norm)[0][1]

        # Niveau de risque
        if proba >= 0.75:
            niveau  = 'CRITIQUE'
            message = f"⚠️ Risque très élevé ({round(proba*100)}%) — Intervention immédiate"
        elif proba >= 0.50:
            niveau  = 'ÉLEVÉ'
            message = f"🔶 Risque élevé ({round(proba*100)}%) — Surveillance renforcée"
        elif proba >= 0.25:
            niveau  = 'MOYEN'
            message = f"🔷 Risque modéré ({round(proba*100)}%) — Maintenance préventive"
        else:
            niveau  = 'FAIBLE'
            message = f"✅ Risque faible ({round(proba*100)}%) — Système stable"

        predictions.append({
            'systeme_id':  int(sys_id),
            'probabilite': round(float(proba), 3),
            'niveau':      niveau,
            'message':     message
        })

        print(f"  🔮 Sys {sys_id:>2} — {niveau:<8} {round(proba*100):>3}% — {message[:45]}")

    return predictions

# ════════════════════════════════════════════════════════
# SAUVEGARDE EN BASE
# ════════════════════════════════════════════════════════
def sauvegarder_predictions(predictions):
    conn   = get_conn()
    cursor = conn.cursor()
    for pred in predictions:
        cursor.execute(
            """INSERT INTO predictions (systeme_id, probabilite, niveau, message)
               VALUES (%s, %s, %s, %s)""",
            (pred['systeme_id'], pred['probabilite'], pred['niveau'], pred['message'])
        )
    conn.commit()
    conn.close()
    print(f"  ✅ {len(predictions)} prédictions sauvegardées")

# ════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ════════════════════════════════════════════════════════
def boucle_ia():
    print("🤖 IA Prédiction démarrée (version améliorée)")
    print(f"   Ré-entraînement toutes les {RETRAIN_INTERVAL//60} min")
    print(f"   Prédiction toutes les 30s\n")

    modele = None
    scaler = None

    while True:
        try:
            print(f"\n🔄 Cycle — {datetime.now().strftime('%H:%M:%S')}")

            # 1. Charger historique
            df = charger_historique()
            print(f"   📊 {len(df)} états chargés")

            if len(df) < MIN_DATA_ROWS:
                print(f"   ⏳ Pas assez de données ({len(df)}/{MIN_DATA_ROWS}) — attente 30s")
                time.sleep(30)
                continue

            # 2. Charger ou ré-entraîner le modèle
            modele_chargé, scaler_chargé, age = charger_modele()

            if modele_chargé is None or age > RETRAIN_INTERVAL:
                print("   🏋️  Entraînement du modèle...")
                features, labels = preparer_features(df)
                if len(features) == 0:
                    print("   ⚠️  Aucune feature extraite")
                    time.sleep(30)
                    continue
                modele, scaler = entrainer_et_sauvegarder(features, labels)
            else:
                modele = modele_chargé
                scaler = scaler_chargé

            # 3. Prédire
            if modele and scaler:
                predictions = predire(modele, scaler, df)
                sauvegarder_predictions(predictions)

            time.sleep(30)

        except Exception as e:
            print(f"❌ Erreur : {e}")
            import traceback; traceback.print_exc()
            time.sleep(30)

if __name__ == "__main__":
    boucle_ia()