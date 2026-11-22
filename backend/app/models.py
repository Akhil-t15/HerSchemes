from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Scheme(Base):
    __tablename__ = "schemes"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name_en = Column(String(255), nullable=False)
    name_te = Column(String(255), nullable=True)
    level = Column(String(20), nullable=False)  # state / central / addon
    lane = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    benefit_en = Column(Text, nullable=True)
    benefit_te = Column(Text, nullable=True)
    official_url = Column(String(500), nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft / published

    rules = relationship(
        "SchemeRule", back_populates="scheme", cascade="all, delete-orphan"
    )
    documents = relationship(
        "SchemeDocument", back_populates="scheme", cascade="all, delete-orphan"
    )


class SchemeRule(Base):
    __tablename__ = "scheme_rules"

    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey("schemes.id"), nullable=False, index=True)
    rule_key = Column(String(100), nullable=False)
    rule_value = Column(JSON, nullable=True)
    needs_verification = Column(Boolean, nullable=False, default=True)

    scheme = relationship("Scheme", back_populates="rules")


class SchemeDocument(Base):
    __tablename__ = "scheme_documents"

    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey("schemes.id"), nullable=False, index=True)
    title_en = Column(String(255), nullable=False)
    title_te = Column(String(255), nullable=True)
    fee_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    processing_days = Column(Integer, nullable=True)
    is_free = Column(Boolean, nullable=False, default=False)
    source_url = Column(String(500), nullable=True)
    needs_verification = Column(Boolean, nullable=False, default=True)

    scheme = relationship("Scheme", back_populates="documents")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    actor = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)


class RuleProposal(Base):
    __tablename__ = "rule_proposals"

    id = Column(Integer, primary_key=True)
    scheme_id = Column(Integer, ForeignKey("schemes.id"), nullable=False, index=True)
    source_text = Column(Text, nullable=True)
    changes_json = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending / approved / dismissed
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class PartnerLead(Base):
    """Opt-in lead for partner organisations. Only rows with consent are ever stored.

    Purged after 30 days by purge_expired_leads() in partner_api.py.
    """

    __tablename__ = "partner_leads"

    id = Column(Integer, primary_key=True)
    scheme_slug = Column(String(100), nullable=False, index=True)
    phone = Column(String(15), nullable=False)
    consent_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class PartnerAccount(Base):
    """Partner or sponsor login. Created only by an admin (see partner_api.py)."""

    __tablename__ = "partner_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # partner / sponsor
    org_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ServiceSession(Base):
    """One row per help session, used only for aggregate sponsor impact numbers.

    district and cost_amount are nullable because the project does not record them
    yet; the impact endpoint reports only what is present.
    """

    __tablename__ = "service_sessions"

    id = Column(Integer, primary_key=True)
    session_key = Column(String(64), nullable=False, index=True)
    scheme_slug = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True)
    cost_amount = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

