# backend/api/admin_router.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.supabase import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Programs ──────────────────────────────────────────────────────────────────

@router.get("/programs")
async def get_programs():
    db = get_db()
    result = db.table("programs").select("*").eq("is_active", True).order("code").execute()
    return result.data or []

class ProgramBody(BaseModel):
    name: str
    code: str

@router.post("/programs")
async def create_program(body: ProgramBody):
    db = get_db()
    result = db.table("programs").insert({
        "name": body.name,
        "code": body.code.upper(),
    }).execute()
    return result.data[0]

@router.delete("/programs/{program_id}")
async def delete_program(program_id: str):
    db = get_db()
    db.table("programs").delete().eq("id", program_id).execute()
    return {"success": True}


# ── Subjects ──────────────────────────────────────────────────────────────────

@router.get("/subjects")
async def get_all_subjects():
    db = get_db()
    result = db.table("subjects").select("*, programs(code, name)").eq("is_active", True).order("name").execute()
    return result.data or []

@router.get("/subjects/program/{program_id}")
async def get_subjects_by_program(program_id: str):
    db = get_db()
    result = db.table("subjects").select("*").eq("program_id", program_id).eq("is_active", True).order("name").execute()
    return result.data or []

class SubjectBody(BaseModel):
    name: str
    code: Optional[str] = None
    program_id: str

@router.post("/subjects")
async def create_subject(body: SubjectBody):
    db = get_db()
    result = db.table("subjects").insert({
        "name":       body.name,
        "code":       body.code,
        "program_id": body.program_id,
    }).execute()
    return result.data[0]

@router.delete("/subjects/{subject_id}")
async def delete_subject(subject_id: str):
    db = get_db()
    db.table("teacher_subjects").delete().eq("subject_id", subject_id).execute()
    db.table("subjects").delete().eq("id", subject_id).execute()
    return {"success": True}


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
async def get_all_users():
    db = get_db()
    result = db.table("profiles").select("*").order("created_at", desc=True).execute()
    return result.data or []

class RoleBody(BaseModel):
    role: str

@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, body: RoleBody):
    db = get_db()
    db.table("profiles").update({"role": body.role}).eq("id", user_id).execute()
    return {"success": True}

class ProgramAssignBody(BaseModel):
    program_code: str

@router.patch("/users/{user_id}/program")
async def assign_teacher_program(user_id: str, body: ProgramAssignBody):
    """Admin assigns a program to a teacher."""
    db = get_db()
    db.table("profiles").update({
        "program": body.program_code
    }).eq("id", user_id).execute()
    return {"success": True}


# ── Teacher-Subject assignments ───────────────────────────────────────────────

@router.get("/teacher-subjects/{teacher_id}")
async def get_teacher_subjects(teacher_id: str):
    """Get all subjects assigned to a specific teacher."""
    db = get_db()
    result = db.table("teacher_subjects").select(
        "*, subjects(id, name, code, program_id, programs(code, name))"
    ).eq("teacher_id", teacher_id).execute()
    return result.data or []

class AssignSubjectBody(BaseModel):
    teacher_id: str
    subject_id: str

@router.post("/teacher-subjects")
async def assign_subject_to_teacher(body: AssignSubjectBody):
    """Admin assigns a subject to a teacher."""
    db = get_db()
    try:
        result = db.table("teacher_subjects").insert({
            "teacher_id": body.teacher_id,
            "subject_id": body.subject_id,
        }).execute()
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Assignment failed: {str(e)}")

@router.delete("/teacher-subjects/{teacher_id}/{subject_id}")
async def remove_subject_from_teacher(teacher_id: str, subject_id: str):
    """Admin removes a subject assignment from a teacher."""
    db = get_db()
    db.table("teacher_subjects").delete().eq("teacher_id", teacher_id).eq("subject_id", subject_id).execute()
    return {"success": True}


# ── Documents (admin view) ────────────────────────────────────────────────────

@router.get("/documents")
async def get_all_documents():
    db = get_db()
    result = db.table("documents").select("*").order("created_at", desc=True).execute()
    return result.data or []

class ToggleDocBody(BaseModel):
    is_active: bool

@router.patch("/documents/{document_id}")
async def toggle_document(document_id: str, body: ToggleDocBody):
    db = get_db()
    db.table("documents").update({"is_active": body.is_active}).eq("id", document_id).execute()
    return {"success": True}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_system_stats():
    db = get_db()
    try:
        users     = db.table("profiles").select("*", count="exact").execute()
        teachers  = db.table("profiles").select("*", count="exact").eq("role", "teacher").execute()
        students  = db.table("profiles").select("*", count="exact").eq("role", "student").execute()
        docs      = db.table("documents").select("*", count="exact").execute()
        txt       = db.table("text_chunks").select("*", count="exact").execute()
        img       = db.table("image_chunks").select("*", count="exact").execute()
        feedback  = db.table("feedback").select("*", count="exact").execute()
        programs  = db.table("programs").select("*", count="exact").execute()
        subjects  = db.table("subjects").select("*", count="exact").execute()
        return {
            "total_users":        users.count,
            "total_teachers":     teachers.count,
            "total_students":     students.count,
            "total_documents":    docs.count,
            "total_text_chunks":  txt.count,
            "total_img_chunks":   img.count,
            "total_feedback":     feedback.count,
            "total_programs":     programs.count,
            "total_subjects":     subjects.count,
        }
    except Exception as e:
        return {"error": str(e)}