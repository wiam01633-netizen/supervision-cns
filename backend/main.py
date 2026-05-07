# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import get_db, engine
from models import Base, Alarme, Operateur, Etat, SystemeCNS
from auth import (
    hasher_password, verifier_password,
    creer_token, get_operateur_connecte
)
import asyncio, json
from websocket1 import collecter_tous_systemes
from datetime import datetime

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Supervision CNS - ESA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def accueil():
    return {"message": "Serveur Supervision CNS actif"}

# ── INITIALISATION ──
@app.on_event("startup")
def creer_admin():
    """Crée l'admin par défaut au démarrage"""
    db = next(get_db())
    existant = db.query(Operateur).filter(
        Operateur.username == "admin"
    ).first()
    if not existant:
        admin = Operateur(
            nom      = "Admin ESA",
            username = "admin",
            password = hasher_password("admin123"),
            role     = "admin"
        )
        db.add(admin)
        db.commit()
        print("Admin créé : admin / admin123")
    db.close()

# ── AUTHENTIFICATION ──
@app.post("/api/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Connexion opérateur — retourne un token JWT"""
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
    """Retourne les infos de l'opérateur connecté"""
    return {
        "id":       operateur.id,
        "nom":      operateur.nom,
        "username": operateur.username,
        "role":     operateur.role
    }

# ── ROUTES PROTÉGÉES ──
@app.get("/api/etats")
async def get_etats(operateur = Depends(get_operateur_connecte)):
    return await collecter_tous_systemes()

@app.get("/api/alarmes")
def get_alarmes(
    db: Session = Depends(get_db),
    operateur = Depends(get_operateur_connecte)
):
    # ✅ Jointure avec systemes_cns et operateurs
    from sqlalchemy import join
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
            "id":           a.Alarme.id,
            "systeme_nom":  a.systeme_nom,
            "type_alarme":  a.Alarme.type_alarme,
            "debut":        str(a.Alarme.debut),
            "acquitte":     a.Alarme.acquitte,
            "operateur":    a.operateur_nom
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
    if alarme:
        alarme.acquitte  = True
        alarme.fin       = datetime.now()
        alarme.operateur = operateur.nom
        db.commit()
        return {"message": f"Alarme acquittée par {operateur.nom}"}
    return {"message": "Alarme introuvable"}

@app.get("/api/test-alarme")
def creer_alarme_test(db: Session = Depends(get_db)):
    alarme = Alarme(
        systeme_id  = 1,
        systeme_nom = "VOR",
        type_alarme = "Test manuel",
        acquitte    = False
    )
    db.add(alarme)
    db.commit()
    db.refresh(alarme)
    return {"message": "Alarme créée", "id": alarme.id}
# ── KPIs ──
@app.get("/api/kpi/alarmes")
def get_kpi_alarmes(
    db: Session = Depends(get_db),
):
    from sqlalchemy import func, text

    # Total alarmes
    total = db.query(Alarme).count()

    # Alarmes actives
    actives = db.query(Alarme).filter(Alarme.acquitte == False).count()

    # MTTR moyen en secondes
    mttr = db.query(
        func.avg(
            func.extract('epoch', Alarme.fin - Alarme.debut)
        )
    ).filter(Alarme.fin != None).scalar()

    # Alarmes par système
    par_systeme = db.query(
        SystemeCNS.nom,
        func.count(Alarme.id).label('total')
    ).join(SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).group_by(SystemeCNS.nom).all()

    # Évolution par heure
    evolution = db.execute(text("""
        SELECT 
            TO_CHAR(debut, 'HH24:MI') as heure,
            COUNT(*) as total
        FROM alarmes
        WHERE debut >= NOW() - INTERVAL '2 hours'
        GROUP BY TO_CHAR(debut, 'HH24:MI')
        ORDER BY heure
    """)).fetchall()

    # MTTR par système
    mttr_sys = db.query(
        SystemeCNS.nom,
        func.avg(
            func.extract('epoch', Alarme.fin - Alarme.debut)
        ).label('mttr')
    ).join(SystemeCNS, Alarme.systeme_id == SystemeCNS.id
    ).filter(Alarme.fin != None
    ).group_by(SystemeCNS.nom).all()

    return {
        "total":   total,
        "actives": actives,
        "mttr_secondes": round(mttr or 0, 1),
        "par_systeme": [{"nom": r.nom, "total": r.total} for r in par_systeme],
        "evolution":   [{"heure": r.heure, "total": r.total} for r in evolution],
        "mttr_par_systeme": [{"nom": r.nom, "mttr": round(r.mttr or 0, 1)} for r in mttr_sys]
    }

@app.get("/api/kpi/etats")
def get_kpi_etats(
    db: Session = Depends(get_db),
    
):
    from sqlalchemy import func

    total = db.query(Etat).count()
    ok    = db.query(Etat).filter(Etat.etat == "OK").count()
    alarm = db.query(Etat).filter(Etat.etat == "ALARM").count()
    fault = db.query(Etat).filter(Etat.etat == "FAULT").count()

    taux = round((ok / total * 100), 1) if total > 0 else 0

    return {
        "taux_disponibilite": taux,
        "repartition": {
            "ok":    ok,
            "alarm": alarm,
            "fault": fault
        }
    }

@app.websocket("/ws/etats")
async def websocket_etats(websocket: WebSocket):
    await websocket.accept()
    db = next(get_db())
    try:
        while True:
            etats = await collecter_tous_systemes()
            for sys in etats:
                # ✅ Sauvegarder chaque état dans la table etats
                nouvel_etat = Etat(
                    systeme_id   = sys["id"],
                    etat         = sys["etat"],
                    valeur_brute = sys["interface"],
                    # timestamp est automatique grâce à func.now()
                )
                db.add(nouvel_etat)

                # ✅ Créer alarme seulement si ALARM ou FAULT
                if sys["etat"] in ["ALARM", "FAULT"]:
                    # Éviter les doublons : vérifier si alarme non acquittée existe déjà
                    existante = db.query(Alarme).filter(
                        Alarme.systeme_id == sys["id"],
                        Alarme.acquitte == False
                    ).first()
                    if not existante:
                        alarme = Alarme(
                            systeme_id  = sys["id"],
                            type_alarme = "Détection automatique",
                            acquitte    = False
                        )
                        db.add(alarme)

            db.commit()
            await websocket.send_text(json.dumps(etats))
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        print("Client déconnecté")
    finally:
        db.close()