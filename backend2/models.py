# models.py
from geoalchemy2 import Geometry
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text,
    Date, DateTime, Numeric, Enum, Boolean, JSON, ForeignKey,
    UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from db import Database

DATABASE_URL = "mysql+aiomysql://root:wail@localhost/palestine_land_system_v5"
db_instance = Database(DATABASE_URL)
Base = db_instance.Base

# ============================================================
# SECTION A – GEO
# ============================================================

class PalestineBoundary(Base):
    __tablename__ = "palestine_boundary"
    boundary_id = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(100), nullable=False)
    created_at  = Column(DateTime, server_default=func.now())
    geom        = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

class Governorate(Base):
    __tablename__ = "governorates"
    governorate_id = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(100))
    territory      = Column(Enum("West Bank", "Gaza Strip"))
    geom           = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    localities     = relationship("Locality", back_populates="governorate")
    reports        = relationship("Report", back_populates="governorate")
    alerts         = relationship("AIAlert", back_populates="governorate")


class Locality(Base):
    __tablename__ = "localities"
    locality_id    = Column(Integer, primary_key=True, autoincrement=True)
    governorate_id = Column(Integer, ForeignKey("governorates.governorate_id"))
    name           = Column(String(150))
    type           = Column(Enum("city", "village", "camp"))
    geom           = Column(Geometry("POINT", srid=4326), nullable=False)

    governorate    = relationship("Governorate", back_populates="localities")
    parcels        = relationship("LandParcel", back_populates="locality")
    reports        = relationship("Report", back_populates="locality")
    alerts         = relationship("AIAlert", back_populates="locality")


# ============================================================
# SECTION B – LAND CLASSIFICATION
# ============================================================

class LandType(Base):
    __tablename__ = "land_types"
    land_type_id = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String(100), nullable=False)
    description  = Column(Text)

    parcels      = relationship("LandParcel", back_populates="land_type")


class OsloZone(Base):
    __tablename__ = "oslo_zones"
    zone_id = Column(Integer, primary_key=True, autoincrement=True)
    class_  = Column("class", String(50))
    geom    = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    parcels = relationship("LandParcel", back_populates="oslo_zone")


# ============================================================
# SECTION C – OWNERS
# ============================================================

class Owner(Base):
    __tablename__ = "owners"
    owner_id         = Column(BigInteger, primary_key=True, autoincrement=True)
    identity_type    = Column(Enum(
        "West Bank ID", "Jerusalem ID", "Gaza ID", "Israeli_ID",
        "Jordanian Passport", "Foreign Passport", "Corporate/Org"
    ))
    owner_type       = Column(Enum("person", "company", "organization"))
    full_name        = Column(String(200))
    national_id      = Column(String(30))
    residence_country= Column(String(100))
    created_at       = Column(DateTime, server_default=func.now())

    risk_profiles    = relationship("OwnerRiskProfile", back_populates="owner")
    ownerships       = relationship("ParcelOwnership", back_populates="owner")
    sales            = relationship("LandTransaction", back_populates="seller", foreign_keys="LandTransaction.seller_id")
    purchases        = relationship("LandTransaction", back_populates="buyer",  foreign_keys="LandTransaction.buyer_id")
    poa_principal    = relationship("PowerOfAttorney", back_populates="principal_owner", foreign_keys="PowerOfAttorney.principal_owner_id")
    poa_agent        = relationship("PowerOfAttorney", back_populates="agent",           foreign_keys="PowerOfAttorney.agent_id")
    reports          = relationship("Report", back_populates="owner")
    alerts           = relationship("AIAlert", back_populates="owner")


class OwnerRiskProfile(Base):
    __tablename__ = "owner_risk_profiles"
    risk_id    = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_id   = Column(BigInteger, ForeignKey("owners.owner_id", ondelete="CASCADE"), nullable=False)
    risk_type  = Column(Enum(
        "suspicious_activity", "blacklisted", "linked_to_case", "foreign_entity"
    ))
    risk_score = Column(SmallInteger)
    notes      = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    owner      = relationship("Owner", back_populates="risk_profiles")


# ============================================================
# SECTION D – LAND PARCELS
# ============================================================

class LandParcel(Base):
    __tablename__ = "land_parcels"
    parcel_id           = Column(BigInteger, primary_key=True, autoincrement=True)
    basin_number        = Column(String(10))
    parcel_number       = Column(String(10))
    locality_id         = Column(Integer, ForeignKey("localities.locality_id"))
    land_type_id        = Column(Integer, ForeignKey("land_types.land_type_id", ondelete="SET NULL"))
    oslo_id             = Column(Integer, ForeignKey("oslo_zones.zone_id", ondelete="SET NULL"))
    leakage_label       = Column(Enum("safe", "leaked", "suspected"), default="safe")
    registration_status = Column(Enum(
        "Tabu", "Maliya", "In_Settlement", "Unregistered", "Israeli_Register"
    ), nullable=False, default="Unregistered")
    area_m2             = Column(Numeric(12, 2))
    geom                = Column(Geometry("POLYGON", srid=4326), nullable=False)

    __table_args__ = (
        UniqueConstraint("basin_number", "parcel_number", "locality_id", name="uq_parcel"),
    )

    locality        = relationship("Locality",    back_populates="parcels")
    land_type       = relationship("LandType",    back_populates="parcels")
    oslo_zone       = relationship("OsloZone",    back_populates="parcels")
    documents       = relationship("LegalDocument",   back_populates="parcel")
    ownerships      = relationship("ParcelOwnership", back_populates="parcel")
    transactions    = relationship("LandTransaction", back_populates="parcel")
    history         = relationship("ParcelHistory",   back_populates="parcel")
    leakage_cases   = relationship("LeakageCase",     back_populates="parcel")
    confiscations   = relationship("ConfiscationOrder", back_populates="parcel")
    poa             = relationship("PowerOfAttorney", back_populates="parcel")
    reports         = relationship("Report", back_populates="parcel")
    alerts          = relationship("AIAlert", back_populates="parcel")


# ============================================================
# SECTION E – DOCUMENTS
# ============================================================

class LegalDocument(Base):
    __tablename__ = "legal_documents"
    document_id     = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id       = Column(BigInteger, ForeignKey("land_parcels.parcel_id", ondelete="CASCADE"))
    document_number = Column(String(100))
    document_type   = Column(Enum(
        "sale_contract", "inheritance_deed", "gift_deed",
        "court_order", "confiscation_order", "power_of_attorney", "other"
    ))
    issue_date      = Column(Date)

    parcel          = relationship("LandParcel",       back_populates="documents")
    versions        = relationship("DocumentVersion",  back_populates="document")
    transactions    = relationship("LandTransaction",  back_populates="document")
    confiscations   = relationship("ConfiscationOrder",back_populates="document")
    poa             = relationship("PowerOfAttorney",  back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    version_id     = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id    = Column(BigInteger, ForeignKey("legal_documents.document_id", ondelete="CASCADE"))
    file_path      = Column(String(255))
    version_number = Column(Integer)
    uploaded_at    = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
    )

    document = relationship("LegalDocument", back_populates="versions")


# ============================================================
# SECTION F – OWNERSHIP
# ============================================================

class ParcelOwnership(Base):
    __tablename__ = "parcel_ownership"
    ownership_id     = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id        = Column(BigInteger, ForeignKey("land_parcels.parcel_id", ondelete="CASCADE"))
    owner_id         = Column(BigInteger, ForeignKey("owners.owner_id",        ondelete="CASCADE"))
    ownership_shares = Column(Integer, nullable=False)
    start_date       = Column(Date)
    end_date         = Column(Date, nullable=False, default="9999-12-31")

    __table_args__ = (
        UniqueConstraint("parcel_id", "owner_id", "end_date", name="uq_active_owner"),
        CheckConstraint("ownership_shares > 0", name="chk_shares_positive"),
    )

    parcel = relationship("LandParcel", back_populates="ownerships")
    owner  = relationship("Owner",      back_populates="ownerships")


# ============================================================
# SECTION G – TRANSACTIONS
# ============================================================

class LandTransaction(Base):
    __tablename__ = "land_transactions"
    transaction_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id        = Column(BigInteger, ForeignKey("land_parcels.parcel_id"))
    seller_id        = Column(BigInteger, ForeignKey("owners.owner_id"))
    buyer_id         = Column(BigInteger, ForeignKey("owners.owner_id"))
    shares_sold      = Column(Integer, nullable=False)
    transaction_date = Column(Date)
    price            = Column(Numeric(15, 2))
    transaction_type = Column(Enum(
        "sale", "inheritance", "gift", "court_transfer", "confiscation"
    ), default="sale")
    document_id      = Column(BigInteger, ForeignKey("legal_documents.document_id"))

    __table_args__ = (
        CheckConstraint("shares_sold > 0", name="chk_shares_sold_positive"),
        CheckConstraint("price >= 0",      name="chk_price_positive"),
        CheckConstraint("seller_id <> buyer_id", name="chk_different_parties"),
    )

    parcel   = relationship("LandParcel",    back_populates="transactions")
    seller   = relationship("Owner", back_populates="sales",     foreign_keys=[seller_id])
    buyer    = relationship("Owner", back_populates="purchases",  foreign_keys=[buyer_id])
    document = relationship("LegalDocument", back_populates="transactions")
    history  = relationship("ParcelHistory", back_populates="transaction")
    cases    = relationship("CaseTransaction", back_populates="transaction")


# ============================================================
# SECTION H – CASES
# ============================================================

class LeakageCase(Base):
    __tablename__ = "leakage_cases"
    case_id          = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id        = Column(BigInteger, ForeignKey("land_parcels.parcel_id"))
    case_status      = Column(Enum("open", "closed"))
    suspicion_score  = Column(SmallInteger)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

    parcel       = relationship("LandParcel",    back_populates="leakage_cases")
    transactions = relationship("CaseTransaction", back_populates="case")


class CaseTransaction(Base):
    __tablename__ = "case_transactions"
    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    case_id        = Column(BigInteger, ForeignKey("leakage_cases.case_id",     ondelete="CASCADE"))
    transaction_id = Column(BigInteger, ForeignKey("land_transactions.transaction_id", ondelete="CASCADE"))

    case        = relationship("LeakageCase",   back_populates="transactions")
    transaction = relationship("LandTransaction", back_populates="cases")


# ============================================================
# SECTION I – EXTRA TABLES
# ============================================================

class Settlement(Base):
    __tablename__ = "settlements"
    settlement_id    = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(150))
    type             = Column(Enum("settlement", "outpost"))
    established_year = Column(Integer)
    geom             = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    

    expansions = relationship("SettlementExpansionHistory", back_populates="settlement")


class SettlementRoad(Base):
    __tablename__ = "settlement_roads"
    road_id       = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(150))
    width_meters  = Column(Numeric(5, 2))
    geom         = Column(Geometry("LINESTRING", srid=4326), nullable=False)

    __table_args__ = (
        CheckConstraint("width_meters > 0", name="chk_width_positive"),
    )


class SettlementExpansionHistory(Base):
    __tablename__ = "settlement_expansion_history"
    expansion_id  = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, ForeignKey("settlements.settlement_id"))
    recorded_year = Column(Integer)
    geom          = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    settlement = relationship("Settlement", back_populates="expansions")


class ConfiscationOrder(Base):
    __tablename__ = "confiscation_orders"
    order_id     = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id    = Column(BigInteger, ForeignKey("land_parcels.parcel_id", ondelete="CASCADE"), nullable=False)
    order_number = Column(String(100))
    order_type   = Column(String(100))
    issue_date   = Column(Date)
    issued_by    = Column(String(200))
    document_id  = Column(BigInteger, ForeignKey("legal_documents.document_id", ondelete="SET NULL"))

    parcel   = relationship("LandParcel",    back_populates="confiscations")
    document = relationship("LegalDocument", back_populates="confiscations")


class PowerOfAttorney(Base):
    __tablename__ = "power_of_attorney"
    poa_id            = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id         = Column(BigInteger, ForeignKey("land_parcels.parcel_id",  ondelete="SET NULL"))
    principal_owner_id= Column(BigInteger, ForeignKey("owners.owner_id",         ondelete="CASCADE"))
    agent_id          = Column(BigInteger, ForeignKey("owners.owner_id",         ondelete="CASCADE"))
    document_id       = Column(BigInteger, ForeignKey("legal_documents.document_id", ondelete="SET NULL"))
    issue_date        = Column(Date)
    expiry_date       = Column(Date)
    notary            = Column(String(200))

    __table_args__ = (
        CheckConstraint("expiry_date > issue_date", name="chk_poa_dates"),
    )

    parcel         = relationship("LandParcel",    back_populates="poa")
    principal_owner= relationship("Owner", back_populates="poa_principal", foreign_keys=[principal_owner_id])
    agent          = relationship("Owner", back_populates="poa_agent",     foreign_keys=[agent_id])
    document       = relationship("LegalDocument", back_populates="poa")


# ============================================================
# SECTION J – USERS & AUTH
# ============================================================

class User(Base):
    __tablename__ = "users"
    user_id       = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(100))
    email         = Column(String(150), unique=True)
    password_hash = Column(String(255))
    is_verified   = Column(Boolean, default=False)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime, server_default=func.now())

    tokens  = relationship("AuthToken", back_populates="user")
    reports = relationship("Report",    back_populates="created_by_user")


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token_id   = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    token      = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="tokens")


# ============================================================
# SECTION K – HISTORY
# ============================================================

class ParcelHistory(Base):
    __tablename__ = "parcel_history"
    history_id             = Column(BigInteger, primary_key=True, autoincrement=True)
    parcel_id              = Column(BigInteger, ForeignKey("land_parcels.parcel_id"))
    change_type            = Column(Enum(
        "sale", "inheritance", "gift", "court_transfer", "confiscation"
    ), nullable=False)
    old_owner_id           = Column(BigInteger, ForeignKey("owners.owner_id"))
    new_owner_id           = Column(BigInteger, ForeignKey("owners.owner_id"))
    related_transaction_id = Column(BigInteger, ForeignKey("land_transactions.transaction_id"))
    change_date            = Column(DateTime, server_default=func.now())

    parcel      = relationship("LandParcel",     back_populates="history")
    old_owner   = relationship("Owner",          foreign_keys=[old_owner_id])
    new_owner   = relationship("Owner",          foreign_keys=[new_owner_id])
    transaction = relationship("LandTransaction",back_populates="history")


# ============================================================
# SECTION L – REPORTS
# ============================================================

class Report(Base):
    __tablename__ = "reports"
    report_id      = Column(BigInteger, primary_key=True, autoincrement=True)
    report_type    = Column(Enum(
        "owner", "parcel", "locality", "governorate", "time_period", "general"
    ), nullable=False)
    title          = Column(String(255), nullable=False)
    owner_id       = Column(BigInteger, ForeignKey("owners.owner_id",           ondelete="SET NULL"), nullable=True)
    parcel_id      = Column(BigInteger, ForeignKey("land_parcels.parcel_id",    ondelete="SET NULL"), nullable=True)
    locality_id    = Column(Integer,    ForeignKey("localities.locality_id",    ondelete="SET NULL"), nullable=True)
    governorate_id = Column(Integer,    ForeignKey("governorates.governorate_id",ondelete="SET NULL"),nullable=True)
    period_from    = Column(Date, nullable=True)
    period_to      = Column(Date, nullable=True)
    file_path      = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    created_by     = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at     = Column(DateTime, server_default=func.now())

    owner           = relationship("Owner",       back_populates="reports")
    parcel          = relationship("LandParcel",  back_populates="reports")
    locality        = relationship("Locality",    back_populates="reports")
    governorate     = relationship("Governorate", back_populates="reports")
    created_by_user = relationship("User",        back_populates="reports")


# ============================================================
# SECTION M – ALERTS
# ============================================================

class AIAlert(Base):
    __tablename__ = "ai_alerts"
    alert_id       = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_type     = Column(Enum(
        "ownership_risk", "fraud_suspected", "unusual_transaction",
        "parcel_conflict", "high_activity", "price_anomaly",
        "system_warning", "custom"
    ), nullable=False)
    title          = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    severity       = Column(Enum("low", "medium", "high", "critical"), default="medium")
    owner_id       = Column(BigInteger, ForeignKey("owners.owner_id",            ondelete="SET NULL"), nullable=True)
    parcel_id      = Column(BigInteger, ForeignKey("land_parcels.parcel_id",     ondelete="SET NULL"), nullable=True)
    locality_id    = Column(Integer,    ForeignKey("localities.locality_id",     ondelete="SET NULL"), nullable=True)
    governorate_id = Column(Integer,    ForeignKey("governorates.governorate_id",ondelete="SET NULL"), nullable=True)
    period_from    = Column(Date, nullable=True)
    period_to      = Column(Date, nullable=True)
    ai_payload     = Column(JSON, nullable=True)
    status         = Column(Enum("new", "reviewed", "resolved", "ignored"), default="new")
    created_at     = Column(DateTime, server_default=func.now())
    created_by     = Column(String(50), default="AI_SYSTEM")

    owner       = relationship("Owner",       back_populates="alerts")
    parcel      = relationship("LandParcel",  back_populates="alerts")
    locality    = relationship("Locality",    back_populates="alerts")
    governorate = relationship("Governorate", back_populates="alerts")