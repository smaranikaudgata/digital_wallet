from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from datetime import datetime, timezone 
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

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String)
    type = Column(String)
    amount = Column(BigInteger)
    currency = Column(String)
    related_user = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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

        # Record transaction
        new_tx = Transaction(
            user_id = user_id,
            type = "DEPOSIT",
            amount = amount,
            currency = currency
        )
        db.add(new_tx)

        db.commit()
        return {
            "message": "Deposit successful", 
            "new_balance_in_minor_units": wallet.balance,
            "display_balance": f"{wallet.balance / 100:.2f}"
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

        # Record transaction
        new_tx = Transaction(
            user_id = user_id,
            type = "WITHDRAWAL",
            amount = amount,
            currency = currency
        )
        db.add(new_tx)
        
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

@app.post("/transfer")
def transfer_money(sender_id: str, receiver_id: str, amount: int, currency: str):
    db = SessionLocal()
    try:
        sender = db.query(Wallet).filter(Wallet.user_id == sender_id, Wallet.currency == currency).first()
        receiver = db.query(Wallet).filter(Wallet.user_id == receiver_id, Wallet.currency == currency).first()

        # Safety check
        if not sender or sender.balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient funds in sender account")
        if not receiver:
            raise HTTPException(status_code=404, detail="Receiver wallet not found")

        sender.balance -= amount
        receiver.balance += amount

        # Record transaction
        sender_tx = Transaction(
            user_id = sender_id,
            type = "TRANSFER_OUT",
            amount = amount,
            currency = currency,
            related_user = receiver_id
        )
        db.add(sender_tx)

        receiver_tx = Transaction(
            user_id = receiver_id,
            type = "TRANSFER_IN",
            amount = amount,
            currency = currency,
            related_user = sender_id
        )
        db.add(receiver_tx)

        db.commit()
        return {"message": "Transfer successful", "amount": amount}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/balance/{user_id}")
def get_balance(user_id: str, currency: str):
    db = SessionLocal()
    try:
        wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id, 
            Wallet.currency == currency
        ).first()

        # Safety check
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found or is empty")

        return {
            "user_id": user_id, 
            "balance": wallet.balance, 
            "currency": currency,
            "display_balance": f"{wallet.balance / 100:.2f}"
        }
    finally:
        db.close()

@app.get("/history/{user_id}")
def get_history(user_id:str):
    db = SessionLocal()
    try:
        history = db.query(Transaction).filter(Transaction.user_id == user_id).order_by(Transaction.timestamp.desc()).all()
        if not history:
            raise HTTPException(
                status_code=404, 
                detail="No transactions found or user doesn't exist"
            )
        return history
    
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not retrieve transaction history. Please try again later.")
    
    finally:
        db.close()