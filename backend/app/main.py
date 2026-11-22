from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)


import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, SessionLocal, engine
from app.matching import match_schemes
from app.schemes_repo import is_stale, list_published_schemes
from app.checklist import get_checklist
from app.content import load_quick_queries
from app.privacy_api import router as privacy_router
from app.followup_api import router as followup_router
from app.admin_api import router as admin_router
from app.partner_api import router as partner_router
from app.voice_api import router as voice_router

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not list_published_schemes(db):
            from app.seed import seed_schemes
            from app.seed_demo import seed_demo_data
            seed_schemes(db)
            seed_demo_data(db)
    except Exception:
        pass
    finally:
        db.close()
    yield


app = FastAPI(title="HerScheme API", lifespan=lifespan)

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if "*" not in origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(privacy_router)
app.include_router(followup_router)
app.include_router(admin_router)
app.include_router(partner_router)
app.include_router(voice_router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/schemes")
def list_schemes(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    return [
        {
            "id": s.id,
            "slug": s.slug,
            "name_en": s.name_en,
            "name_te": s.name_te,
            "level": s.level,
            "lane": s.lane,
            "description": s.description,
            "official_url": s.official_url,
            "last_verified_at": s.last_verified_at.isoformat() if s.last_verified_at else None,
            "is_stale": is_stale(s.last_verified_at, now),
        }
        for s in list_published_schemes(db)
    ]

@app.get("/api/schemes/{slug}/checklist")
def scheme_checklist(slug: str, db: Session = Depends(get_db)):
    result = get_checklist(db, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return result


@app.get("/api/match")
def match(
    business_type: Optional[str] = Query(None),
    location_type: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    shg_member: Optional[bool] = Query(None),
    stage: Optional[str] = Query(None),
    loan_amount_band: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    raw = {
        "business_type": business_type,
        "location_type": location_type,
        "district": district,
        "shg_member": shg_member,
        "stage": stage,
        "loan_amount_band": loan_amount_band,
    }
    answers = {k: v for k, v in raw.items() if v is not None}
    return match_schemes(db, answers, datetime.utcnow())


@app.get("/api/quick-queries")
def quick_queries():
    return load_quick_queries()


frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/admin")
    def serve_admin():
        return FileResponse(frontend_dist / "admin.html")

    @app.get("/partners")
    def serve_partners():
        return FileResponse(frontend_dist / "partners.html")

    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend_static")
