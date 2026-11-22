"""Seed realistic evaluation/judge demo data for Admin, Partner, and Sponsor views."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from app.db import Base, SessionLocal, engine
from app.models import AuditLog, PartnerAccount, PartnerLead, RuleProposal, Scheme, SchemeRule, ServiceSession
from app.partner_api import hash_password

def seed_demo_data(session):
    # 1. Partner Accounts
    if not session.query(PartnerAccount).filter_by(username="judge_partner").first():
        session.add(
            PartnerAccount(
                username="judge_partner",
                password_hash=hash_password("Password123!"),
                role="partner",
                org_name="State Bank of India - MSME Branch",
            )
        )
    if not session.query(PartnerAccount).filter_by(username="judge_sponsor").first():
        session.add(
            PartnerAccount(
                username="judge_sponsor",
                password_hash=hash_password("Password123!"),
                role="sponsor",
                org_name="Telangana CSR Consortium",
            )
        )

    # 2. Rule Proposals for Admin Console
    pmegp = session.query(Scheme).filter_by(slug="pmegp").first()
    if pmegp and not session.query(RuleProposal).filter_by(scheme_id=pmegp.id, status="pending").first():
        session.add(
            RuleProposal(
                scheme_id=pmegp.id,
                source_text="Ministry of MSME G.O. No. 42/2026: Enhancing maximum project cost under PMEGP manufacturing sector for women entrepreneurs to Rs. 50,00,000 and subsidy to 35% in rural areas.",
                changes_json=[
                    {"rule_key": "max_loan", "old_value": 2500000, "new_value": 5000000},
                    {"rule_key": "subsidy_rural_women", "old_value": "30%", "new_value": "35%"},
                ],
                status="pending",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )

    stree = session.query(Scheme).filter_by(slug="stree-nidhi").first()
    if stree and not session.query(RuleProposal).filter_by(scheme_id=stree.id, status="pending").first():
        session.add(
            RuleProposal(
                scheme_id=stree.id,
                source_text="SERP Telangana Circular 18/2026: Additional interest rebate on prompt repayment for SHG women micro-enterprises.",
                changes_json=[
                    {"rule_key": "interest_rebate_pct", "old_value": 3, "new_value": 4},
                ],
                status="pending",
                created_at=datetime.now(timezone.utc) - timedelta(hours=6),
            )
        )

    # 3. Partner Leads
    if session.query(PartnerLead).count() == 0:
        leads = [
            PartnerLead(
                scheme_slug="pm-mudra",
                phone="9876543210",
                consent_at=datetime.utcnow() - timedelta(hours=2),
            ),
            PartnerLead(
                scheme_slug="pmegp",
                phone="9440123456",
                consent_at=datetime.utcnow() - timedelta(hours=14),
            ),
            PartnerLead(
                scheme_slug="stree-nidhi",
                phone="9123456789",
                consent_at=datetime.utcnow() - timedelta(days=1, hours=3),
            ),
            PartnerLead(
                scheme_slug="indira-mahila-shakti",
                phone="9848011223",
                consent_at=datetime.utcnow() - timedelta(days=2),
            ),
        ]
        session.add_all(leads)

    # 4. Service Sessions (for Sponsor Impact metrics)
    if session.query(ServiceSession).count() == 0:
        districts = ["Hyderabad", "Rangareddy", "Warangal", "Medchal-Malkajgiri", "Karimnagar", "Nalgonda"]
        schemes = ["pmegp", "pm-mudra", "stree-nidhi", "indira-mahila-shakti"]
        sessions = []
        for i in range(1, 48):
            sess_key = f"demo-session-{i:03d}"
            dist = districts[i % len(districts)]
            sch = schemes[i % len(schemes)]
            cost = 1.15 + (i % 7) * 0.22
            sessions.append(
                ServiceSession(
                    session_key=sess_key,
                    scheme_slug=sch,
                    district=dist,
                    cost_amount=cost,
                    created_at=datetime.utcnow() - timedelta(days=i % 15, hours=i % 12),
                )
            )
        session.add_all(sessions)

    session.commit()
    print("Demo data seeded successfully.")

def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_demo_data(session)

if __name__ == "__main__":
    main()
