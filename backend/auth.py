# auth.py — Version 2 : utilise config.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import Operateur
from config import SECRET_KEY, ALGORITHM, EXPIRE_MINUTES
import warnings
warnings.filterwarnings("ignore")

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def hasher_password(password: str) -> str:
    return pwd_context.hash(password)

def verifier_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)

def creer_token(data: dict) -> str:
    to_encode = data.copy()
    expire    = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verifier_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré"
        )

def get_operateur_connecte(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    payload  = verifier_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token invalide")
    operateur = db.query(Operateur).filter(
        Operateur.username == username
    ).first()
    if not operateur:
        raise HTTPException(status_code=401, detail="Opérateur introuvable")
    return operateur