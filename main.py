from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from datetime import datetime, timezone 
from sqlalchemy.ext.declarative import declarative_base
from fastapi import HTTPException
import requests

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
    description = Column(String, nullable=True)
    exchange_rate = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# fetches real-time rate from Frankfurter API
def get_live_rate(from_currency:str, to_currency:str) -> float:
    if from_currency == to_currency:
        return 1.0
    url = f"https://api.frankfurter.dev/v1/latest?base={from_currency}&symbols={to_currency}"

    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        data=response.json()
        if "rates" in data and to_currency in data["rates"]:
            return float(data["rates"][to_currency])
        else:
            raise HTTPException(status_code=400, detail=f"Currency {to_currency} not supported")
    
    except requests.exceptions.RequestException as e:
        # If the internet is down or API is unreachable
        raise HTTPException(
            status_code=503, 
            detail="Exchange rate service is currently unavailable. Please try again later."
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Currency conversion error:{str(e)}")


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
            "balance": f"{wallet.balance / 100:.2f}",
            "amount": f"{amount / 100:.2f}"        
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

        if wallet and wallet.balance>=amount:
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
                "balance": f"{wallet.balance / 100:.2f}",
                "amount": f"{amount / 100:.2f}"
            }
        
        # automatic conversion incase balance isnt available in required currency
        all_wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id, 
            Wallet.currency == currency
        ).all()

        for alt_wallet in all_wallet:
            # to make sure that the currency its already in is not checked
            if alt_wallet.currency == currency: 
                continue
            rate = get_live_rate(currency, alt_wallet.currency)
            converted_amt = int(round(amount * rate))
            if alt_wallet.balance >= converted_amt:
                alt_wallet.balance -= converted_amt

                # Record the transaction as a converted withdrawal
                db.add(Transaction(
                    user_id=user_id, 
                    type="WITHDRAW_CONVERTED", 
                    amount=converted_amt, 
                    currency=alt_wallet.currency,
                    description=f"Converted to {amount/100:.2f} {currency} at rate {rate}", 
                    exchange_rate=str(rate)
                ))
                
                db.commit()
                return {
                    "message": "Auto-converted withdrawal successful",
                    "source_wallet": alt_wallet.currency,
                    "deducted_balance": f"{converted_amt / 100:.2f}",
                    "target_received": f"{amount / 100:.2f}",
                    "exchange_rate": rate
                }
        raise HTTPException(status_code=400, detail= "Insufficient funds")    

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# @app.post("/transfer")
# def transfer_money(sender_id: str, receiver_id: str, amount: int, currency: str):
#     db = SessionLocal()
#     try:
#         sender = db.query(Wallet).filter(Wallet.user_id == sender_id, Wallet.currency == currency).first()
#         receiver = db.query(Wallet).filter(Wallet.user_id == receiver_id, Wallet.currency == currency).first()

#         # Safety check
#         if not sender or sender.balance < amount:
#             raise HTTPException(status_code=400, detail="Insufficient funds in sender account")
#         if not receiver:
#             raise HTTPException(status_code=404, detail="Receiver wallet not found")

#         sender.balance -= amount
#         receiver.balance += amount

#         # Record transaction
#         sender_tx = Transaction(
#             user_id = sender_id,
#             type = "TRANSFER_OUT",
#             amount = amount,
#             currency = currency,
#             related_user = receiver_id
#         )
#         db.add(sender_tx)

#         receiver_tx = Transaction(
#             user_id = receiver_id,
#             type = "TRANSFER_IN",
#             amount = amount,
#             currency = currency,
#             related_user = sender_id
#         )
#         db.add(receiver_tx)

#         db.commit()
#         return {"message": "Transfer successful", "amount": amount}
    
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         db.close()

@app.post("/transfer")
def transfer_money(sender_id: str, receiver_id: str, amount: int, transaction_currency: str):
    db = SessionLocal()
    try:
        # SENDER LOGIC try to find the exact currency first
        s_wallet = db.query(Wallet).filter(Wallet.user_id == sender_id, Wallet.currency == transaction_currency).first()
        
        actual_sender_wallet = None
        deducted_amount = amount
        
        if s_wallet and s_wallet.balance >= amount:
            actual_sender_wallet = s_wallet
        else:
            # look other wallets the sender has
            other_wallets = db.query(Wallet).filter(Wallet.user_id == sender_id).all()
            for ow in other_wallets:
                rate = get_live_rate(transaction_currency, ow.currency)
                cost = int(round(amount * rate))
                if ow.balance >= cost:
                    actual_sender_wallet = ow
                    deducted_amount = cost
                    break
        
        if not actual_sender_wallet:
            raise HTTPException(status_code=400, detail="Sender has insufficient funds")

        # RECEIVER LOGIC try to find receiver's wallet in transaction currency
        r_wallet = db.query(Wallet).filter(Wallet.user_id == receiver_id, Wallet.currency == transaction_currency).first()
        
        receive_amount = amount
        final_receiver_wallet = r_wallet

        if not r_wallet:
            # if receiver doesn't have that currency convert to their first available wallet
            first_r_wallet = db.query(Wallet).filter(Wallet.user_id == receiver_id).first()
            if first_r_wallet:
                rate = get_live_rate(transaction_currency, first_r_wallet.currency)
                receive_amount = int(round(amount * rate))
                final_receiver_wallet = first_r_wallet
            else:
                # if receiver has no wallets at all create one in the transaction currency
                final_receiver_wallet = Wallet(user_id=receiver_id, currency=transaction_currency, balance=0)
                db.add(final_receiver_wallet)

        actual_sender_wallet.balance -= deducted_amount
        final_receiver_wallet.balance += receive_amount

        # Sender Record
        sender_tx = Transaction(
            user_id=sender_id, 
            type="TRANSFER_OUT", 
            amount=deducted_amount, 
            currency=actual_sender_wallet.currency, 
            related_user=receiver_id,
            description=f"Sent {amount/100:.2f} {transaction_currency}"
        )
        db.add(sender_tx)
        
        # Receiver Record
        receiver_tx = Transaction(
            user_id=receiver_id, 
            type="TRANSFER_IN", 
            amount=receive_amount, 
            currency=final_receiver_wallet.currency, 
            related_user=sender_id,
            description=f"Received via {transaction_currency} transfer"
        )
        db.add(receiver_tx)

        db.commit()
        return {
            "status": "success", 
            "sent_amount": f"{deducted_amount / 100:.2f} {actual_sender_wallet.currency}", 
            "received_amount": f"{receive_amount / 100:.2f} {final_receiver_wallet.currency}"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/balance/{user_id}")
def get_balance(user_id: str, currency: str):
    db = SessionLocal()
    try:
        wallets = db.query(Wallet).filter(
            Wallet.user_id == user_id, 
        ).all()

        # Safety check
        if not wallets:
            raise HTTPException(status_code=404, detail="Wallet not found or is empty")
        
        # logic for total balance independent of currency it was deposited or withdrawn in
        total_balance = 0
        for wallet in wallets:
            if wallet.currency == currency:
                contribution = wallet.balance
                rate = 1.0
            else:
                rate = get_live_rate(wallet.currency, currency)
                contribution = int(round(rate * wallet.balance))
            
            total_balance+=contribution

        return {
            "user_id": user_id, 
            "balance": f"{total_balance / 100:.2f}", 
            "currency": currency
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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