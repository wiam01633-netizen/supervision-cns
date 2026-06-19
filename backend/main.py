# main.py — Version 3 : sécurité .env + CORS restreint
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from models import Base, Alarme, Operateur, Etat, SystemeCNS
from auth import (
    hasher_password, verifier_password,
    creer_token, get_operateur_connecte
)
from config import CORS_ORIGINS, ADMIN_USERNAME, ADMIN_PASSWORD
import asyncio, json
from websocket1 import collecter_tous_systemes
from datetime import datetime
from typing import Optional

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Supervision CNS - ESA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,      # ← liste depuis .env
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/")
async def accueil():
    return {"message": "Serveur Supervision CNS actif"}

# ── INITIALISATION ──
@app.on_event("startup")
def creer_admin():
    """Crée l'admin par défaut — credentials depuis .env"""
    db = next(get_db())
    existant = db.query(Operateur).filter(
        Operateur.username == ADMIN_USERNAME
    ).first()
    if not existant:
        admin = Operateur(
            nom      = "Admin ESA",
            username = ADMIN_USERNAME,
            password = hasher_password(ADMIN_PASSWORD),
            role     = "admin"
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin créé : {ADMIN_USERNAME}")
    db.close()

# ── AUTHENTIFICATION ──
@app.post("/api/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    operateur = db.query(Operateur).filter(
        Operateur.username == form.username
    ).first()
    if not operateur or not verifier_password(form.password, operateur.password):
        raise HTTPException(
            status_code=401,
            detail="Nom d'utilisateur ou mot de passe incorrect"
        )
    token = creer_token({"sub": operateur.username, "role": operateur.role})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "nom":          operateur.nom,
        "role":         operateur.role
    }

@app.get("/api/moi")
def get_moi(operateur = Depends(get_operateur_connecte)):
    return {
        "id":       operateur.id,
        "nom":      operateur.nom,
        "username": operateur.username,
        "role":     operateur.role
    }

# ── ÉTATS ──
@app.get("/api/etats")
async def get_etats(operateur = Depends(get_operateur_connecte)):
    return await collecter_tous_systemes()

# ── ALARMES ──
@app.get("/api/alarmes")
def get_alarmes(
    db: Session = Depends(get_db),
):
    alarmes = db.query(
        Alarme,
        SystemeCNS.nom.label("systeme_nom"),
        Operateur.nom.label("operateur_nom")
    ).outerjoin(
        SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).outerjoin(
        Operateur, Alarme.operateur_id == Operateur.id
    ).filter(
        Alarme.acquitte == False
    ).order_by(Alarme.debut.desc()).all()

    return [
        {
            "id":          a.Alarme.id,
            "systeme_nom": a.systeme_nom,
            "type_alarme": a.Alarme.type_alarme,
            "debut":       str(a.Alarme.debut),
            "acquitte":    a.Alarme.acquitte,
            "operateur":   a.operateur_nom
        }
        for a in alarmes
    ]

@app.put("/api/alarmes/{alarme_id}/acquitter")
def acquitter_alarme(
    alarme_id: int,
    db: Session = Depends(get_db),
    operateur = Depends(get_operateur_connecte)
):
    alarme = db.query(Alarme).filter(Alarme.id == alarme_id).first()
    if not alarme:
        raise HTTPException(status_code=404, detail="Alarme introuvable")
    if alarme.acquitte:
        raise HTTPException(status_code=400, detail="Alarme déjà acquittée")

    alarme.acquitte     = True
    alarme.fin          = datetime.now()
    alarme.operateur_id = operateur.id
    db.commit()
    db.refresh(alarme)

    return {
        "message":   f"Alarme {alarme_id} acquittée par {operateur.nom}",
        "alarme_id": alarme_id,
        "operateur": operateur.nom,
        "fin":       str(alarme.fin)
    }
@app.get("/api/historique")
def get_historique(
    db: Session = Depends(get_db),
    operateur = Depends(get_operateur_connecte),
    systeme:  Optional[str]  = Query(None),   # filtre par nom système
    acquitte: Optional[bool] = Query(None),   # filtre acquitté/non acquitté
    debut:    Optional[str]  = Query(None),   # filtre date début (YYYY-MM-DD)
    fin:      Optional[str]  = Query(None),   # filtre date fin   (YYYY-MM-DD)
    limite:   int            = Query(500)     # max 500 par défaut
):
    from sqlalchemy import and_

    # Base de la requête
    query = db.query(
        Alarme,
        SystemeCNS.nom.label("systeme_nom"),
        Operateur.nom.label("operateur_nom")
    ).outerjoin(
        SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).outerjoin(
        Operateur, Alarme.operateur_id == Operateur.id
    )

    # ── Filtres dynamiques ──
    if systeme:
        query = query.filter(SystemeCNS.nom == systeme)

    if acquitte is not None:
        query = query.filter(Alarme.acquitte == acquitte)

    if debut:
        query = query.filter(Alarme.debut >= debut)

    if fin:
        # Inclure toute la journée de fin
        query = query.filter(Alarme.debut <= fin + " 23:59:59")

    # Tri + limite
    alarmes = query.order_by(Alarme.debut.desc()).limit(limite).all()

    return [
        {
            "id":           a.Alarme.id,
            "systeme_nom":  a.systeme_nom  or "—",
            "type_alarme":  a.Alarme.type_alarme,
            "debut":        str(a.Alarme.debut),
            "fin":          str(a.Alarme.fin) if a.Alarme.fin else None,
            "acquitte":     a.Alarme.acquitte,
            "operateur_nom": a.operateur_nom or "—"
        }
        for a in alarmes
    ]


from fastapi.responses import StreamingResponse
import csv, io

@app.get("/api/historique/export/csv")
def exporter_csv(
    db: Session = Depends(get_db),
    operateur = Depends(get_operateur_connecte)
):
    alarmes = db.query(
        Alarme,
        SystemeCNS.nom.label("systeme_nom"),
        Operateur.nom.label("operateur_nom")
    ).outerjoin(
        SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).outerjoin(
        Operateur, Alarme.operateur_id == Operateur.id
    ).order_by(Alarme.debut.desc()).all()

    # Construire le CSV en mémoire
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    # En-tête
    writer.writerow(['ID', 'Système', 'Type', 'Début', 'Fin', 'Acquittée', 'Opérateur'])

    # Lignes
    for a in alarmes:
        writer.writerow([
            a.Alarme.id,
            a.systeme_nom  or '—',
            a.Alarme.type_alarme,
            str(a.Alarme.debut),
            str(a.Alarme.fin) if a.Alarme.fin else '—',
            'Oui' if a.Alarme.acquitte else 'Non',
            a.operateur_nom or '—'
        ])

    output.seek(0)

    # Retourner comme fichier téléchargeable
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=historique_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )

# ── KPIs ──
# ── REMPLACER toute la fonction get_kpi_alarmes dans main.py ──

# ── REMPLACER get_kpi_alarmes dans main.py ──

@app.get("/api/kpi/alarmes")
def get_kpi_alarmes(
    db: Session = Depends(get_db),
    periode: str = Query("24h")   # ✅ paramètre depuis le frontend
):
    from sqlalchemy import func
    from datetime import timedelta

    # ════════════════════════════════════════════════════════
    # ✅ Calculer la date de début selon la période choisie
    # ════════════════════════════════════════════════════════
    if periode == "24h":
        depuis = datetime.now() - timedelta(hours=24)
    elif periode == "7j":
        depuis = datetime.now() - timedelta(days=7)
    elif periode == "30j":
        depuis = datetime.now() - timedelta(days=30)
    else:  # "tout"
        depuis = datetime(2000, 1, 1)

    # ── Alarmes actives (toujours sans filtre date) ──
    actives = db.query(Alarme).filter(
        Alarme.acquitte == False,
        Alarme.debut    != None
    ).count()

    # ── Total sur la période ──
    total = db.query(Alarme).filter(
        Alarme.debut >= depuis,
        Alarme.debut != None
    ).count()

    # ── MTTR corrigé ──
    mttr = db.execute(text("""
        SELECT AVG(duree) FROM (
            SELECT EXTRACT(EPOCH FROM (fin - debut)) as duree
            FROM alarmes
            WHERE fin IS NOT NULL AND debut IS NOT NULL
              AND fin > debut
              AND EXTRACT(EPOCH FROM (fin - debut)) BETWEEN 10 AND 86400
              AND debut >= :depuis
        ) sub
    """), {"depuis": depuis}).scalar()

    # ── Alarmes par système ──
    par_systeme = db.query(
        SystemeCNS.nom, func.count(Alarme.id).label('total')
    ).join(
        SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).filter(
        Alarme.debut >= depuis,
        Alarme.debut != None
    ).group_by(SystemeCNS.nom).order_by(func.count(Alarme.id).desc()).all()

    # ── Évolution — granularité selon période ──
    if periode == "24h":
        format_date = "HH24:MI"
        interval    = "24 hours"
    elif periode == "7j":
        format_date = "DD/MM"
        interval    = "7 days"
    elif periode == "30j":
        format_date = "DD/MM"
        interval    = "30 days"
    else:
        format_date = "MM/YYYY"
        interval    = "3650 days"

    evolution = db.execute(text(f"""
        SELECT TO_CHAR(debut, '{format_date}') as heure, COUNT(*) as total
        FROM alarmes
        WHERE debut >= NOW() - INTERVAL '{interval}'
          AND debut IS NOT NULL
        GROUP BY TO_CHAR(debut, '{format_date}')
        ORDER BY MIN(debut)
    """)).fetchall()

    # ── MTTR par système ──
    mttr_sys = db.execute(text("""
        SELECT s.nom, AVG(duree) as mttr FROM (
            SELECT a.systeme_id,
                   EXTRACT(EPOCH FROM (a.fin - a.debut)) as duree
            FROM alarmes a
            WHERE a.fin IS NOT NULL AND a.debut IS NOT NULL
              AND a.fin > a.debut
              AND EXTRACT(EPOCH FROM (a.fin - a.debut)) BETWEEN 10 AND 86400
              AND a.debut >= :depuis
        ) sub
        JOIN systemes_cns s ON s.id = sub.systeme_id
        GROUP BY s.nom ORDER BY mttr DESC
    """), {"depuis": depuis}).fetchall()

    return {
        "total":         total,
        "actives":       actives,
        "periode":       periode,
        "mttr_secondes": round(float(mttr or 0), 1),
        "par_systeme":   [{"nom": r.nom, "total": r.total} for r in par_systeme],
        "evolution":     [{"heure": r.heure, "total": r.total} for r in evolution],
        "mttr_par_systeme": [
            {"nom": r.nom, "mttr": round(float(r.mttr or 0), 1)}
            for r in mttr_sys
        ]
    }

@app.get("/api/kpi/etats")
def get_kpi_etats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total = db.query(Etat).count()
    ok    = db.query(Etat).filter(Etat.etat == "OK").count()
    alarm = db.query(Etat).filter(Etat.etat == "ALARM").count()
    fault = db.query(Etat).filter(Etat.etat == "FAULT").count()
    taux  = round((ok / total * 100), 1) if total > 0 else 0
    return {
        "taux_disponibilite": taux,
        "repartition": {"ok": ok, "alarm": alarm, "fault": fault}
    }

# ── PRÉDICTIONS ──
@app.get("/api/predictions")
def get_predictions(db: Session = Depends(get_db)):
    resultats = db.execute(text("""
        SELECT DISTINCT ON (p.systeme_id)
            p.systeme_id,
            s.nom        AS systeme_nom,
            p.probabilite,
            p.niveau,
            p.message,
            p.timestamp,
            (
                SELECT CASE
                    WHEN SUM(CASE WHEN etat IN ('ALARM','FAULT') THEN 1 ELSE 0 END)
                         FILTER (WHERE timestamp >= NOW() - INTERVAL '5 minutes') >
                         SUM(CASE WHEN etat IN ('ALARM','FAULT') THEN 1 ELSE 0 END)
                         FILTER (WHERE timestamp < NOW() - INTERVAL '5 minutes'
                               AND timestamp >= NOW() - INTERVAL '10 minutes')
                    THEN 1 ELSE 0 END
                FROM etats e2
                WHERE e2.systeme_id = p.systeme_id
                  AND e2.timestamp >= NOW() - INTERVAL '10 minutes'
            ) AS tendance,
            (
                SELECT COUNT(*) FROM etats e3
                WHERE e3.systeme_id = p.systeme_id
                  AND e3.etat IN ('ALARM','FAULT')
                  AND e3.timestamp >= NOW() - INTERVAL '5 minutes'
            ) AS consecutif,
            (
                SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (fin - debut))), 0)
                FROM alarmes a
                WHERE a.systeme_id = p.systeme_id
                  AND a.fin IS NOT NULL
                  AND a.debut >= NOW() - INTERVAL '24 hours'
            ) AS duree_moy,
            CASE
                WHEN EXTRACT(HOUR FROM NOW()) >= 22
                  OR EXTRACT(HOUR FROM NOW()) <= 5
                THEN true ELSE false
            END AS heure_creuse
        FROM predictions p
        JOIN systemes_cns s ON p.systeme_id = s.id
        ORDER BY p.systeme_id, p.timestamp DESC
    """)).fetchall()

    return [
        {
            "systeme_id":   r.systeme_id,
            "systeme_nom":  r.systeme_nom,
            "probabilite":  r.probabilite,
            "niveau":       r.niveau,
            "message":      r.message,
            "timestamp":    str(r.timestamp),
            "tendance":     r.tendance or 0,
            "consecutif":   r.consecutif or 0,
            "duree_moy":    round(float(r.duree_moy or 0), 0),
            "heure_creuse": r.heure_creuse or False
        }
        for r in resultats
    ]

# ── À AJOUTER dans main.py ──

# ════════════════════════════════════════════════════════
# SCÉNARIOS DÉMO — déclenchables depuis le dashboard
# ════════════════════════════════════════════════════════
SCENARIOS_DEMO = {
    "nominal": {
        "nom": "Nominal — Tous OK",
        "etats": {1: "OK", 2: "OK", 3: "OK", 4: "OK", 5: "OK", 7: "OK"}
    },
    "alarm": {
        "nom": "ALARM — Dégradation VHF COM 1",
        "etats": {1: "OK", 2: "OK", 3: "ALARM", 4: "OK", 5: "ALARM", 7: "OK"}
    },
    "fault": {
        "nom": "FAULT — Panne critique ILS",
        "etats": {1: "OK", 2: "FAULT", 3: "OK", 4: "OK", 5: "ALARM", 7: "FAULT"}
    }
}

@app.post("/api/scenario/{nom_scenario}")
def declencher_scenario(
    nom_scenario: str,
    db: Session = Depends(get_db),
    operateur = Depends(get_operateur_connecte)
):
    # Seul l'admin peut déclencher un scénario
    if operateur.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès refusé — admin uniquement"
        )

    scenario = SCENARIOS_DEMO.get(nom_scenario)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scénario '{nom_scenario}' introuvable"
        )

    resultats = []

    for sys_id, etat in scenario["etats"].items():
        # INSERT état
        nouvel_etat = Etat(
            systeme_id   = sys_id,
            etat         = etat,
            valeur_brute = f"Scénario:{nom_scenario}"
        )
        db.add(nouvel_etat)

        # Gestion alarmes
        alarme_existante = db.query(Alarme).filter(
            Alarme.systeme_id == sys_id,
            Alarme.acquitte   == False
        ).first()

        if etat in ["ALARM", "FAULT"]:
            if not alarme_existante:
                alarme = Alarme(
                    systeme_id  = sys_id,
                    type_alarme = f"Scénario démo - {etat}",
                    acquitte    = False
                )
                db.add(alarme)
                resultats.append(f"{sys_id} → {etat} (alarme créée)")
        else:
            if alarme_existante:
                alarme_existante.fin = datetime.now()
                resultats.append(f"{sys_id} → OK (alarme fermée)")

    db.commit()

    return {
        "message":   f"Scénario '{scenario['nom']}' appliqué",
        "operateur": operateur.nom,
        "resultats": resultats
    }

@app.get("/api/scenarios")
def get_scenarios(operateur = Depends(get_operateur_connecte)):
    """Liste les scénarios disponibles"""
    return [
        {"id": k, "nom": v["nom"]}
        for k, v in SCENARIOS_DEMO.items()
    ]
# ── WEBSOCKET ──
@app.websocket("/ws/etats")
async def websocket_etats(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            etats = await collecter_tous_systemes()
            await websocket.send_text(json.dumps(etats))
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        print("Client déconnecté")