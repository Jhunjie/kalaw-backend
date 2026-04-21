"""
KALAW AI - Upload Router
"""

import os
import uuid
import tempfile
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from supabase import create_client, Client

from ingestion.text_pipeline import ingest_document_text
from ingestion.image_pipeline import ingest_document_images, chunk_to_supabase_row

router = APIRouter(prefix="/upload", tags=["upload"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".png", ".jpg", ".jpeg"}


def get_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@router.post("/document")
async def upload_document(
    file:          UploadFile = File(...),
    program:       str        = Form(...),
    subject:       str        = Form(...),
    uploader_name: str        = Form(...),
    uploader_id:   str        = Form(...),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not supported.")

    document_id   = str(uuid.uuid4())
    document_name = file.filename
    content       = await file.read()
    tmp_path      = None
    db            = get_db()

    print(f"\n[UPLOAD] Starting upload: {document_name}")
    print(f"[UPLOAD] Program: {program} | Subject: {subject} | Uploader: {uploader_name}")

    try:
        # 1. Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        print(f"[UPLOAD] Temp file: {tmp_path}")

        # 2. Upload to Supabase Storage
        storage_path = f"{program}/{uploader_id}/{document_id}{ext}"
        try:
            db.storage.from_("documents").upload(
                storage_path, content,
                {"content-type": file.content_type or "application/octet-stream"}
            )
            print(f"[UPLOAD] File uploaded to storage: {storage_path}")
        except Exception as e:
            print(f"[UPLOAD] Storage upload failed (continuing anyway): {e}")

        # 3. Insert document record
        db.table("documents").insert({
            "id":            document_id,
            "name":          document_name,
            "uploader_id":   uploader_id,
            "uploader_name": uploader_name,
            "program":       program,
            "subject":       subject,
            "storage_path":  storage_path,
            "file_type":     ext.lstrip("."),
        }).execute()
        print(f"[UPLOAD] Document record inserted: {document_id}")

        results = {"document_id": document_id, "text_chunks": 0, "image_chunks": 0, "errors": []}

        # 4. Text ingestion
        if ext in {".pdf", ".pptx", ".ppt", ".docx", ".doc"}:
            print(f"[UPLOAD] Starting text ingestion...")
            try:
                text_chunks = await ingest_document_text(
                    file_path=tmp_path,
                    document_id=document_id,
                    document_name=document_name,
                    uploader_name=uploader_name,
                    program=program,
                    subject=subject,
                )
                print(f"[UPLOAD] Text chunks generated: {len(text_chunks)}")

                if text_chunks:
                    # Insert in batches of 50 to avoid payload limits
                    batch_size = 50
                    for i in range(0, len(text_chunks), batch_size):
                        batch = text_chunks[i:i+batch_size]
                        db.table("text_chunks").insert(batch).execute()
                        print(f"[UPLOAD] Inserted batch {i//batch_size + 1}: {len(batch)} chunks")
                    results["text_chunks"] = len(text_chunks)
                else:
                    print("[UPLOAD] Warning: text ingestion returned 0 chunks")
                    results["errors"].append("Text extraction returned 0 chunks — file may be empty or image-only")

            except Exception as e:
                err = traceback.format_exc()
                print(f"[UPLOAD] TEXT INGESTION ERROR:\n{err}")
                results["errors"].append(f"Text ingestion failed: {str(e)}")

        # 5. Image ingestion
        if ext in {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".png", ".jpg", ".jpeg"}:
            print(f"[UPLOAD] Starting image ingestion...")
            try:
                image_chunks = await ingest_document_images(
                    file_path=tmp_path,
                    document_id=document_id,
                    document_name=document_name,
                    uploader_name=uploader_name,
                    program=program,
                    subject=subject,
                )
                print(f"[UPLOAD] Image chunks generated: {len(image_chunks)}")

                if image_chunks:
                    rows = [chunk_to_supabase_row(c) for c in image_chunks]
                    db.table("image_chunks").insert(rows).execute()
                    results["image_chunks"] = len(image_chunks)

            except Exception as e:
                err = traceback.format_exc()
                print(f"[UPLOAD] IMAGE INGESTION ERROR:\n{err}")
                results["errors"].append(f"Image ingestion failed: {str(e)}")

        success = results["text_chunks"] > 0 or results["image_chunks"] > 0
        print(f"[UPLOAD] Done. text={results['text_chunks']} image={results['image_chunks']} errors={results['errors']}")

        return {
            "success": success,
            "message": f"'{document_name}' processed — {results['text_chunks']} text chunks, {results['image_chunks']} image chunks.",
            **results,
        }

    except Exception as e:
        err = traceback.format_exc()
        print(f"[UPLOAD] FATAL ERROR:\n{err}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/documents/{uploader_id}")
async def get_teacher_documents(uploader_id: str):
    db = get_db()
    result = db.table("documents").select("*").eq("uploader_id", uploader_id).order("created_at", desc=True).execute()
    return result.data or []


@router.get("/accuracy/{uploader_id}")
async def get_accuracy_dashboard(uploader_id: str):
    db = get_db()
    result = db.table("instructor_accuracy_dashboard").select("*").eq("uploader_id", uploader_id).execute()
    return result.data or []


@router.delete("/document/{document_id}")
async def delete_document(document_id: str):
    db = get_db()
    db.table("text_chunks").delete().eq("document_id", document_id).execute()
    db.table("image_chunks").delete().eq("document_id", document_id).execute()
    db.table("documents").delete().eq("id", document_id).execute()
    return {"success": True}