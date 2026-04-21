# backend/api/chat_router.py
from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import base64
from core.rag import answer_text_query
from ingestion.image_pipeline import query_image
from core.llm import chat
from core.supabase import get_db

router = APIRouter(prefix="/chat", tags=["chat"])

class TextQuery(BaseModel):
    question: str
    program:  Optional[str] = None
    language: str = "en"     # en | tl | hil | mixed

@router.post("/text")
async def text_query(body: TextQuery):
    return await answer_text_query(
        body.question, body.program, body.language
    )

@router.post("/image")
async def image_query(
    file:           UploadFile = File(...),
    program_filter: Optional[str] = Form(None),
    language:       str           = Form("en"),
):
    content = await file.read()
    b64     = base64.b64encode(content).decode()
    return await query_image(b64, program_filter, language)

@router.post("/feedback")
async def submit_feedback(
    query_type:    str           = Form(...),
    document_id:   str           = Form(...),
    rating:        int           = Form(...),  # 1 or -1
    student_query: Optional[str] = Form(None),
    ai_response:   Optional[str] = Form(None),
):
    db = get_db()
    db.table("feedback").insert({
        "query_type":    query_type,
        "document_id":   document_id,
        "rating":        rating,
        "student_query": student_query,
        "ai_response":   ai_response,
    }).execute()
    return {"success": True}