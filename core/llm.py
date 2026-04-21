# backend/core/llm.py
import os, httpx
from dotenv import load_dotenv
load_dotenv()

BASE   = os.getenv("OLLAMA_BASE_URL")
VISION = os.getenv("VISION_MODEL", "llama3.2-vision:11b")
CHAT   = os.getenv("CHAT_MODEL",   "gemma3:4b")
EMBED  = os.getenv("EMBED_MODEL",  "nomic-embed-text")

NGROK_HEADERS = {
    "ngrok-skip-browser-warning": "true",
    "Content-Type": "application/json",
}

async def chat(messages: list, model=None) -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{BASE}/api/chat", headers=NGROK_HEADERS, json={
            "model": model or CHAT,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.3}
        })
        r.raise_for_status()
        return r.json()["message"]["content"]

async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as c:
        # Try new endpoint first, fall back to old one
        try:
            r = await c.post(f"{BASE}/api/embed", headers=NGROK_HEADERS, json={
                "model": EMBED, "input": text
            })
            r.raise_for_status()
            return r.json()["embeddings"][0]
        except httpx.HTTPStatusError:
            # Fall back to old Ollama endpoint
            r = await c.post(f"{BASE}/api/embeddings", headers=NGROK_HEADERS, json={
                "model": EMBED, "prompt": text
            })
            r.raise_for_status()
            return r.json()["embedding"]

async def describe_image(b64: str, hint="") -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{BASE}/api/chat", headers=NGROK_HEADERS, json={
            "model": VISION,
            "messages": [{
                "role": "user",
                "content": f"Describe this image in detail for an educational AI. {hint}",
                "images": [b64]
            }],
            "stream": False
        })
        r.raise_for_status()
        return r.json()["message"]["content"]