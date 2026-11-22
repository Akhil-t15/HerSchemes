"""LLM-powered follow-up chat endpoint for HerScheme (Module 3).

The client sends the message, known facts, conversation history and turn
counters every time. Nothing is stored or logged here. See app.followup for
the logic.
"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.followup import run_followup

router = APIRouter(prefix="/api/chat")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class FollowUpIn(BaseModel):
    message: str = Field(max_length=2000)
    lang: Literal["en", "te"]
    known_facts: Dict[str, Any] = Field(default_factory=dict)
    rounds_asked: int = Field(default=0, ge=0)
    skipped: bool = False
    history: List[ChatMessage] = Field(default_factory=list)
    last_question_key: Optional[str] = None


class MatchOut(BaseModel):
    slug: str
    name_en: str
    name_te: Optional[str] = None
    official_url: Optional[str] = None
    level: Optional[str] = None
    lane: Optional[str] = None
    status: Literal["Likely Eligible", "Needs More Info"]
    is_bank_loan: bool = False
    benefit_en: Optional[str] = None
    benefit_te: Optional[str] = None
    description: Optional[str] = None


class FollowUpOut(BaseModel):
    reply: Optional[str] = None
    questions: List[str]
    matches: List[MatchOut]
    masked_text: str
    done: bool
    known_facts: Dict[str, Any] = Field(default_factory=dict)
    warning: Optional[str] = None
    question_key: Optional[str] = None


@router.post("/follow-up", response_model=FollowUpOut)
def follow_up(body: FollowUpIn, db: Session = Depends(get_db)):
    history = [{"role": m.role, "content": m.content} for m in body.history]
    return run_followup(
        db,
        body.message,
        body.lang,
        body.known_facts,
        body.rounds_asked,
        body.skipped,
        history=history,
        last_question_key=body.last_question_key,
    )
