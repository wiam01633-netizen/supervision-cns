# models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

# Table des systèmes CNS
class SystemeCNS(Base):
    __tablename__ = "systemes_cns"

    id          = Column(Integer, primary_key=True, index=True)
    nom         = Column(String(100), nullable=False)   # ex: VOR, ILS, DME
    type_sys    = Column(String(50))                    # Navigation, Com, Surveillance
    interface   = Column(String(20))                    # SNMP, SERIAL, IO
    adresse     = Column(String(100))                   # IP ou port série
    actif       = Column(Boolean, default=True)

# Table des états en temps réel
class Etat(Base):
    __tablename__ = "etats"

    id          = Column(Integer, primary_key=True, index=True)
    systeme_id  = Column(Integer)
    etat        = Column(String(20))    # OK, ALARM, FAULT, UNKNOWN
    valeur_brute= Column(String(200))
    timestamp   = Column(DateTime, default=func.now())

# Table des alarmes
class Alarme(Base):
    __tablename__ = "alarmes"

    id          = Column(Integer, primary_key=True, index=True)
    systeme_id  = Column(Integer, ForeignKey("systemes_cns.id"))  # ✅ clé étrangère
    type_alarme = Column(String(100))
    debut       = Column(DateTime, default=func.now())
    fin         = Column(DateTime, nullable=True)
    acquitte    = Column(Boolean, default=False)
    operateur_id = Column(Integer, ForeignKey("operateurs.id"), nullable=True)  # ✅ clé étrangère

# Table des opérateurs
class Operateur(Base):
    __tablename__ = "operateurs"

    id          = Column(Integer, primary_key=True, index=True)
    nom         = Column(String(100))
    username    = Column(String(50), unique=True)
    password    = Column(String(200))   # mot de passe chiffré
    role        = Column(String(20), default="operateur")