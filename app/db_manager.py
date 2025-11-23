"""
Database manager for banking application.
Handles all database operations using SQLAlchemy ORM.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

# Load environment variables ONLY when this module is actually used
# NOT at import time - this avoids credential detection issues
_env_loaded = False

def _ensure_env_loaded():
    global _env_loaded
    if not _env_loaded:
        print(f"[DB_MANAGER] Loading environment variables via load_dotenv()...")
        load_dotenv()
        print(f"[DB_MANAGER] Environment variables loaded successfully")
        _env_loaded = True

print(f"[DB_MANAGER] Module imported, calling _ensure_env_loaded()")
_ensure_env_loaded()
print(f"[DB_MANAGER] Environment loaded")

# Database URL from .env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://banking_user:banking_password123@localhost:5432/banking_db")
print(f"[DB_MANAGER] DATABASE_URL set to: {DATABASE_URL[:50] if DATABASE_URL else 'None'}...")

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for debugging
    pool_pre_ping=True,  # Test connection before using
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """User profile"""
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    preferences = Column(JSON, default={})  # language, timezone, etc
    
    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user")
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    """Bank account"""
    __tablename__ = "accounts"
    
    account_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    account_type = Column(String(50), nullable=False)  # checking, savings, etc
    balance = Column(Numeric(15, 2), nullable=False, default=0)
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="accounts")
    transactions_from = relationship(
        "Transaction",
        foreign_keys="Transaction.from_account_id",
        back_populates="from_account"
    )
    transactions_to = relationship(
        "Transaction",
        foreign_keys="Transaction.to_account_id",
        back_populates="to_account"
    )


class Transaction(Base):
    """Transaction history"""
    __tablename__ = "transactions"
    
    transaction_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    from_account_id = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    to_account_id = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    transaction_type = Column(String(50), nullable=False)  # transfer, deposit, withdrawal
    status = Column(String(50), default="completed")  # pending, completed, failed
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    from_account = relationship(
        "Account",
        foreign_keys=[from_account_id],
        back_populates="transactions_from"
    )
    to_account = relationship(
        "Account",
        foreign_keys=[to_account_id],
        back_populates="transactions_to"
    )


class AuthToken(Base):
    """Authentication tokens"""
    __tablename__ = "auth_tokens"
    
    token_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_valid = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="auth_tokens")


class CreditScore(Base):
    """User credit scores"""
    __tablename__ = "credit_scores"
    
    credit_score_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True, unique=True)
    score = Column(Integer, nullable=False)  # 300-900
    last_updated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")


class LoanProduct(Base):
    """Available loan products"""
    __tablename__ = "loan_products"
    
    product_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    loan_type = Column(String(50), nullable=False)  # personal, home, auto, education
    min_amount = Column(Numeric(15, 2), nullable=False)
    max_amount = Column(Numeric(15, 2), nullable=False)
    interest_rate = Column(Numeric(5, 2), nullable=False)  # 12.5%
    min_tenure = Column(Integer, nullable=False)  # months
    max_tenure = Column(Integer, nullable=False)
    processing_fee_percent = Column(Numeric(5, 2), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LoanApplication(Base):
    """Loan applications"""
    __tablename__ = "loan_applications"
    
    application_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    loan_type = Column(String(50), nullable=False)
    requested_amount = Column(Numeric(15, 2), nullable=False)
    tenure_months = Column(Integer, nullable=False)
    status = Column(String(50), default="pending")  # pending, approved, rejected, disbursed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")


class Loan(Base):
    """Approved loans"""
    __tablename__ = "loans"
    
    loan_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey("loan_applications.application_id"), nullable=True)
    loan_type = Column(String(50), nullable=False)
    loan_amount = Column(Numeric(15, 2), nullable=False)
    outstanding_balance = Column(Numeric(15, 2), nullable=False)
    interest_rate = Column(Numeric(5, 2), nullable=False)
    tenure_months = Column(Integer, nullable=False)
    emi_amount = Column(Numeric(15, 2), nullable=False)
    disbursed_date = Column(DateTime, nullable=False)
    maturity_date = Column(DateTime, nullable=False)
    status = Column(String(50), default="active")  # active, closed, defaulted
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")


class LoanPayment(Base):
    """Loan EMI payments"""
    __tablename__ = "loan_payments"
    
    payment_id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)
    due_date = Column(DateTime, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    principal_amount = Column(Numeric(15, 2), nullable=False)
    interest_amount = Column(Numeric(15, 2), nullable=False)
    status = Column(String(50), default="pending")  # pending, paid, overdue
    paid_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    loan = relationship("Loan")


class LoanSchedule(Base):
    """Loan payment schedule"""
    __tablename__ = "loan_schedules"
    
    schedule_id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)
    month = Column(Integer, nullable=False)  # 1, 2, 3...
    due_date = Column(DateTime, nullable=False)
    opening_balance = Column(Numeric(15, 2), nullable=False)
    emi_amount = Column(Numeric(15, 2), nullable=False)
    principal = Column(Numeric(15, 2), nullable=False)
    interest = Column(Numeric(15, 2), nullable=False)
    closing_balance = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    loan = relationship("Loan")


class LoanClosureRequest(Base):
    """Loan closure/prepayment requests"""
    __tablename__ = "loan_closure_requests"
    
    closure_request_id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    closure_type = Column(String(50), nullable=False)  # prepayment, foreclosure
    payoff_amount = Column(Numeric(15, 2), nullable=False)
    status = Column(String(50), default="pending")  # pending, approved, rejected, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    loan = relationship("Loan")
    user = relationship("User")


# ============================================================================
# DATABASE MANAGER CLASS
# ============================================================================

class DBManager:
    """Manager for all database operations"""
    
    @staticmethod
    def init_db():
        """Create all tables"""
        Base.metadata.create_all(bind=engine)
        print("[DB] Tables created successfully")
    
    @staticmethod
    def get_session():
        """Get a database session"""
        return SessionLocal()
    
    # ========== USER OPERATIONS ==========
    
    @staticmethod
    def create_user(phone_number, name=None, email=None):
        """Create a new user"""
        session = SessionLocal()
        try:
            user = User(
                phone_number=phone_number,
                name=name,
                email=email
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            result = user
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to create user: {e}")
            return None
    
    @staticmethod
    def get_user_by_phone(phone_number):
        """Get user by phone number"""
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(phone_number=phone_number).first()
            if user:
                # Convert to dict to avoid lazy loading issues
                result = {
                    "user_id": user.user_id,
                    "phone_number": user.phone_number,
                    "name": user.name,
                    "email": user.email,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                }
                session.close()
                return result
            session.close()
            return None
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get user: {e}")
            return None
    
    @staticmethod
    def update_last_login(phone_number):
        """Update user's last login time"""
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(phone_number=phone_number).first()
            if user:
                user.last_login = datetime.utcnow()
                session.commit()
                session.close()
                return True
            session.close()
            return False
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to update last login: {e}")
            return False
    
    # ========== ACCOUNT OPERATIONS ==========
    
    @staticmethod
    def create_account(user_id, account_type, balance=0, currency="USD"):
        """Create an account for user"""
        session = SessionLocal()
        try:
            account = Account(
                user_id=user_id,
                account_type=account_type,
                balance=balance,
                currency=currency
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            result = account
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to create account: {e}")
            return None
    
    @staticmethod
    def get_user_accounts(user_id):
        """Get all accounts for a user"""
        session = SessionLocal()
        try:
            accounts = session.query(Account).filter_by(user_id=user_id, is_active=True).all()
            print(f"[DB_MANAGER] get_user_accounts() fetching {len(accounts)} accounts for user_id={user_id}")
            result = [
                {
                    "account_id": a.account_id,
                    "account_type": a.account_type,
                    "balance": float(a.balance),
                    "currency": a.currency,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in accounts
            ]
            for i, acc in enumerate(result):
                print(f"[DB_MANAGER]   Account {i}: db_id={acc['account_id']}, type={acc['account_type']}, balance={acc['balance']}")
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get accounts: {e}")
            return []
    
    @staticmethod
    def get_account_balance(account_id):
        """Get balance of an account"""
        session = SessionLocal()
        try:
            account = session.query(Account).filter_by(account_id=account_id).first()
            if account:
                balance = float(account.balance)
                session.close()
                return balance
            session.close()
            return None
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get balance: {e}")
            return None
    
    @staticmethod
    def update_account_balance(account_id, new_balance):
        """Update account balance"""
        session = SessionLocal()
        try:
            account = session.query(Account).filter_by(account_id=account_id).first()
            if account:
                account.balance = new_balance
                session.commit()
                session.close()
                return True
            session.close()
            return False
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to update balance: {e}")
            return False
    
    # ========== TRANSACTION OPERATIONS ==========
    
    @staticmethod
    def save_transaction(user_id, from_account_id, to_account_id, amount, transaction_type, description=None):
        """Save a transaction to history"""
        session = SessionLocal()
        try:
            transaction = Transaction(
                user_id=user_id,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                status="completed"
            )
            session.add(transaction)
            session.commit()
            session.refresh(transaction)
            result = transaction
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to save transaction: {e}")
            return None
    
    @staticmethod
    def get_transaction_history(user_id, limit=50):
        """Get transaction history for user"""
        session = SessionLocal()
        try:
            transactions = session.query(Transaction)\
                .filter_by(user_id=user_id)\
                .order_by(Transaction.created_at.desc())\
                .limit(limit)\
                .all()
            
            result = [
                {
                    "transaction_id": t.transaction_id,
                    "from_account_id": t.from_account_id,
                    "to_account_id": t.to_account_id,
                    "amount": float(t.amount),
                    "type": t.transaction_type,
                    "status": t.status,
                    "description": t.description,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in transactions
            ]
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get transaction history: {e}")
            return []
    
    # ========== AUTH TOKEN OPERATIONS ==========
    
    @staticmethod
    def save_auth_token(user_id, token_hash, expires_at):
        """Save an authentication token"""
        session = SessionLocal()
        try:
            auth_token = AuthToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                is_valid=True
            )
            session.add(auth_token)
            session.commit()
            session.refresh(auth_token)
            result = auth_token
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to save auth token: {e}")
            return None
    
    @staticmethod
    def verify_auth_token(token_hash):
        """Verify if auth token is valid"""
        session = SessionLocal()
        try:
            token = session.query(AuthToken).filter_by(
                token_hash=token_hash,
                is_valid=True
            ).first()
            
            if token and token.expires_at > datetime.utcnow():
                session.close()
                return True
            session.close()
            return False
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to verify token: {e}")
            return False
    
    # ========== CREDIT SCORE OPERATIONS ==========
    
    @staticmethod
    def get_credit_score(user_id):
        """Get user's credit score"""
        session = SessionLocal()
        try:
            credit = session.query(CreditScore).filter_by(user_id=user_id).first()
            if credit:
                score = credit.score
                session.close()
                return score
            session.close()
            # Return default score if not found
            return 650
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get credit score: {e}")
            return None
    
    @staticmethod
    def set_credit_score(user_id, score):
        """Set or update user's credit score"""
        session = SessionLocal()
        try:
            credit = session.query(CreditScore).filter_by(user_id=user_id).first()
            if credit:
                credit.score = score
                credit.last_updated = datetime.utcnow()
            else:
                credit = CreditScore(user_id=user_id, score=score)
                session.add(credit)
            session.commit()
            session.close()
            return True
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to set credit score: {e}")
            return False
    
    # ========== LOAN PRODUCT OPERATIONS ==========
    
    @staticmethod
    def get_loan_products():
        """Get all active loan products"""
        session = SessionLocal()
        try:
            products = session.query(LoanProduct).filter_by(is_active=True).all()
            result = [
                {
                    "product_id": p.product_id,
                    "name": p.name,
                    "loan_type": p.loan_type,
                    "min_amount": float(p.min_amount),
                    "max_amount": float(p.max_amount),
                    "interest_rate": float(p.interest_rate),
                    "min_tenure": p.min_tenure,
                    "max_tenure": p.max_tenure,
                    "processing_fee_percent": float(p.processing_fee_percent),
                }
                for p in products
            ]
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get loan products: {e}")
            return []
    
    # ========== LOAN APPLICATION OPERATIONS ==========
    
    @staticmethod
    def create_loan_application(user_id, loan_type, requested_amount, tenure_months, status="pending"):
        """Create a new loan application"""
        session = SessionLocal()
        try:
            application = LoanApplication(
                user_id=user_id,
                loan_type=loan_type,
                requested_amount=requested_amount,
                tenure_months=tenure_months,
                status=status
            )
            session.add(application)
            session.commit()
            session.refresh(application)
            
            result = {
                "application_id": application.application_id,
                "user_id": application.user_id,
                "loan_type": application.loan_type,
                "requested_amount": float(application.requested_amount),
                "tenure_months": application.tenure_months,
                "status": application.status,
                "created_at": application.created_at.isoformat() if application.created_at else None,
            }
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to create loan application: {e}")
            return None
    
    @staticmethod
    def get_loan_application(application_id):
        """Get loan application details"""
        session = SessionLocal()
        try:
            app = session.query(LoanApplication).filter_by(application_id=application_id).first()
            if app:
                result = {
                    "application_id": app.application_id,
                    "user_id": app.user_id,
                    "loan_type": app.loan_type,
                    "requested_amount": float(app.requested_amount),
                    "tenure_months": app.tenure_months,
                    "status": app.status,
                    "created_at": app.created_at.isoformat() if app.created_at else None,
                }
                session.close()
                return result
            session.close()
            return None
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get loan application: {e}")
            return None
    
    # ========== LOAN OPERATIONS ==========
    
    @staticmethod
    def get_active_loans(user_id):
        """Get all active loans for user"""
        session = SessionLocal()
        try:
            loans = session.query(Loan).filter_by(user_id=user_id, status="active").all()
            result = [
                {
                    "loan_id": l.loan_id,
                    "loan_type": l.loan_type,
                    "loan_amount": float(l.loan_amount),
                    "outstanding_balance": float(l.outstanding_balance),
                    "interest_rate": float(l.interest_rate),
                    "emi_amount": float(l.emi_amount),
                    "tenure_months": l.tenure_months,
                    "disbursed_date": l.disbursed_date.isoformat() if l.disbursed_date else None,
                    "maturity_date": l.maturity_date.isoformat() if l.maturity_date else None,
                }
                for l in loans
            ]
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get active loans: {e}")
            return []
    
    @staticmethod
    def get_loan_details(loan_id):
        """Get detailed information for a loan"""
        session = SessionLocal()
        try:
            loan = session.query(Loan).filter_by(loan_id=loan_id).first()
            if loan:
                result = {
                    "loan_id": loan.loan_id,
                    "loan_type": loan.loan_type,
                    "loan_amount": float(loan.loan_amount),
                    "outstanding_balance": float(loan.outstanding_balance),
                    "interest_rate": float(loan.interest_rate),
                    "emi_amount": float(loan.emi_amount),
                    "tenure_months": loan.tenure_months,
                    "disbursed_date": loan.disbursed_date.isoformat() if loan.disbursed_date else None,
                    "maturity_date": loan.maturity_date.isoformat() if loan.maturity_date else None,
                    "status": loan.status,
                }
                session.close()
                return result
            session.close()
            return None
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get loan details: {e}")
            return None
    
    # ========== LOAN PAYMENT OPERATIONS ==========
    
    @staticmethod
    def get_next_payment_due(loan_id):
        """Get next EMI payment due for a loan"""
        session = SessionLocal()
        try:
            payment = session.query(LoanPayment).filter_by(
                loan_id=loan_id,
                status="pending"
            ).order_by(LoanPayment.due_date).first()
            
            if payment:
                from datetime import datetime as dt
                days_remaining = (payment.due_date - dt.utcnow()).days
                
                result = {
                    "payment_id": payment.payment_id,
                    "loan_id": payment.loan_id,
                    "amount": float(payment.amount),
                    "due_date": payment.due_date.isoformat() if payment.due_date else None,
                    "days_remaining": days_remaining,
                    "principal": float(payment.principal_amount),
                    "interest": float(payment.interest_amount),
                }
                session.close()
                return result
            session.close()
            return None
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to get next payment: {e}")
            return None
    
    # ========== LOAN CLOSURE OPERATIONS ==========
    
    @staticmethod
    def create_loan_closure_request(loan_id, user_id, closure_type, payoff_amount, status="pending"):
        """Create a loan closure/prepayment request"""
        session = SessionLocal()
        try:
            closure = LoanClosureRequest(
                loan_id=loan_id,
                user_id=user_id,
                closure_type=closure_type,
                payoff_amount=payoff_amount,
                status=status
            )
            session.add(closure)
            session.commit()
            session.refresh(closure)
            
            result = {
                "closure_request_id": closure.closure_request_id,
                "loan_id": closure.loan_id,
                "closure_type": closure.closure_type,
                "payoff_amount": float(closure.payoff_amount),
                "status": closure.status,
                "created_at": closure.created_at.isoformat() if closure.created_at else None,
            }
            session.close()
            return result
        except Exception as e:
            session.close()
            print(f"[DB ERROR] Failed to create closure request: {e}")
            return None


# ============================================================================
# HELPER FUNCTIONS FOR SEEDING
# ============================================================================

def seed_demo_data():
    """Seed database with demo user and accounts"""
    db = DBManager()
    session = SessionLocal()
    
    try:
        # Check if demo user exists
        demo_user = session.query(User).filter_by(phone_number="+919999999999").first()
        
        if not demo_user:
            print("[DB] Seeding demo data...")
            
            # Create demo user
            demo_user = User(
                phone_number="+919999999999",
                name="Demo User",
                email="demo@example.com"
            )
            session.add(demo_user)
            session.commit()
            
            # Create demo accounts
            acc1 = Account(
                user_id=demo_user.user_id,
                account_type="checking",
                balance=5000.00,
                currency="USD"
            )
            acc2 = Account(
                user_id=demo_user.user_id,
                account_type="savings",
                balance=15000.00,
                currency="USD"
            )
            session.add(acc1)
            session.add(acc2)
            session.commit()
            
            print("[DB] Demo data created successfully")
        else:
            print("[DB] Demo data already exists")
        
        session.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to seed demo data: {e}")
        session.close()


if __name__ == "__main__":
    print("Initializing database...")
    DBManager.init_db()
    seed_demo_data()
    print("Database ready!")
