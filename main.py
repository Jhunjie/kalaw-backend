# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from api.upload_router import router as upload_router
from api.chat_router   import router as chat_router
from api.admin_router  import router as admin_router

app = FastAPI(title="CPSU AI", version="1.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(admin_router)

@app.get("/")
async def root():
    return {"status": "KALAW AI is running"}