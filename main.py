from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from fastapi import HTTPException

app = FastAPI()

# DATABASE SETUP
DB_URL = "postgresql://postgres:postgres@localhost:5432/wallet_db"

engine = create_engine(DB_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String)
    currency = Column(String)
    balance = Column(BigInteger, default=0)

@app.get("/")
def home():
    return {"message": "API is online"}

# @app.get("/check-db")
# def check_db():
#     try:
#         connection = engine.connect()
#         connection.close()
#         return {"status": "Success", "message": "Connected to PostgreSQL!"}
#     except Exception as e:
#         return {"status": "Error", "message": str(e)}

@app.post("/deposit")
def deposit_money(user_id: str, amount: int, currency: str):
    db = SessionLocal()
    try:
        wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id, 
            Wallet.currency == currency
        ).first()

        if not wallet:
            # Storing the amount as a whole number (cents/paise)
            wallet = Wallet(user_id=user_id, currency=currency, balance=amount)
            db.add(wallet)
        else:
            wallet.balance += amount

        db.commit()
        return {
            "message": "Deposit successful", 
            "new_balance_in_minor_units": wallet.balance,
            "display_balance": wallet.balance / 100  
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/withdraw")
def withdraw_money(user_id: str, amount: int, currency: str):
    db = SessionLocal()
    try:
        wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id, 
            Wallet.currency == currency
        ).first()

        # Safety check
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        if wallet.balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")

        # Remember: amount is in cents/minor units
        wallet.balance -= amount
        
        db.commit()
        return {
            "message": "Withdrawal successful", 
            "new_balance": wallet.balance,
            "display_amount": amount / 100
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()