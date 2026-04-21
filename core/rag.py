# backend/core/rag.py
from core.llm import embed, chat
from core.supabase import get_db

LANG_PROMPTS = {
    "en":    "Respond in English.",
    "tl":    "Tumugon sa Tagalog.",
    "hil":   "Magsabat sa Hiligaynon.",
    "mixed": "Mix English, Tagalog, and Hiligaynon naturally.",
}

NO_MATCH_MESSAGES = {
    "en":    "I'm sorry, I couldn't find anything about that in the uploaded school materials. Try rephrasing your question, or ask your instructor directly.",
    "tl":    "Paumanhin, wala akong nahanap tungkol dito sa mga na-upload na materyales. Subukang ibang paraan ng pagtatanong, o direktang tanungin ang iyong guro.",
    "hil":   "Pasensya na, wala ako nakit-an parte sini sa mga na-upload nga materyales. Try to rephrase it, or ask your instructor directly — they know best! 💪",
    "mixed": "Sorry, wala akong nahanap about that in the uploaded materials. Try rephrasing, or ask your instructor directly.",
}

VAGUE_INPUTS = {
    "i need help", "help", "hello", "hi", "hey", "ok", "okay", "sure",
    "yes", "no", "thanks", "thank you", "salamat", "oo", "hindi",
    "kumusta", "good morning", "good afternoon", "good evening",
    "what can you do", "who are you", "ano ka", "pwede mo ba",
}

async def clean_query(question: str) -> str:
    """Fix typos and grammar before embedding for better search accuracy."""
    prompt = (
        "Fix any typos, spelling errors, and grammar mistakes in this student question. "
        "Return ONLY the corrected question with no explanation, no quotes, nothing else. "
        "Preserve the original meaning exactly. "
        "If already correct, return it unchanged.\n\n"
        f"Question: {question}"
    )
    try:
        corrected = await chat([{"role": "user", "content": prompt}])
        corrected = corrected.strip().strip('"').strip("'")
        print(f"[RAG] Original: {question}")
        print(f"[RAG] Cleaned:  {corrected}")
        return corrected if corrected else question
    except Exception as e:
        print(f"[RAG] Query cleaning failed, using original: {e}")
        return question


async def answer_text_query(
    question: str,
    program:  str | None = None,
    language: str = "en"
) -> dict:
    db = get_db()

    print(f"\n[RAG] Question: {question}")
    print(f"[RAG] Program: {program} | Language: {language}")

    # 1. Reject greetings and vague inputs
    cleaned_input = question.strip().lower().rstrip("!?.")
    if len(cleaned_input) < 10 or cleaned_input in VAGUE_INPUTS:
        return {
            "answer": (
                "Hello! I'm KALAW, your academic assistant at CPSU. 👋\n\n"
                "I can answer questions based on your instructor's uploaded materials. "
                "Try asking something like:\n"
                "• \"What is software engineering?\"\n"
                "• \"Explain the Waterfall model\"\n"
                "• \"What are the SDLC models?\"\n\n"
                "What subject would you like help with?"
            ),
            "citations": [],
            "found": False,
        }

    # 2. Fix typos and grammar
    question = await clean_query(question)

    # 3. Embed the cleaned question
    print("[RAG] Generating embedding...")
    q_embedding = await embed(question)
    print(f"[RAG] Embedding length: {len(q_embedding)}")

    # 4. Vector search
    params = {
        "query_embedding": q_embedding,
        "match_threshold": 0.55,
        "match_count":     5,
        "program_filter":  program,
    }
    results = db.rpc("match_text_chunks", params).execute()
    print(f"[RAG] Results found: {len(results.data) if results.data else 0}")

    if results.data:
        for i, r in enumerate(results.data):
            print(f"[RAG]   Match {i+1}: similarity={r['similarity']:.3f} | {r['document_name']}")

    # 5. No results
    if not results.data:
        print("[RAG] No matches — returning no-match message")
        return {
            "answer":    NO_MATCH_MESSAGES.get(language, NO_MATCH_MESSAGES["en"]),
            "citations": [],
            "found":     False,
        }

    # 6. Build context
    context = "\n\n---\n\n".join(
        f"[SOURCE {i+1}: \"{r['document_name']}\" uploaded by {r['uploader_name']}, "
        f"{r['program']} - {r['subject']}]\n{r['chunk_text']}"
        for i, r in enumerate(results.data)
    )

    # 7. Generate answer with strict prompt
    lang_inst = LANG_PROMPTS.get(language, LANG_PROMPTS["en"])
    system = (
        "You are KALAW, the academic AI assistant of Central Philippine State University. "
        "Your ONLY job is to answer student questions using the provided school materials below. "
        "\n\nSTRICT RULES:"
        "\n1. ONLY use information explicitly stated in the [SOURCE] blocks."
        "\n2. If the answer is NOT in the sources, say: \"I'm sorry, I couldn't find information "
        "about that in the uploaded school materials. Please ask your instructor directly.\""
        "\n3. NEVER make up or infer information not in the sources."
        "\n4. NEVER use your general training knowledge to fill gaps."
        "\n5. Always cite the instructor name and document in your answer."
        "\n6. Be friendly, clear, and academic in tone."
        "\n7. If the student used informal language or typos, respond naturally — "
        "you already understand what they meant."
        f"\n8. {lang_inst}"
    )

    user = (
        f"School materials:\n\n{context}"
        f"\n\n---\n\nStudent question: {question}"
        f"\n\nAnswer using only the sources above. Cite the instructor and document."
    )

    print("[RAG] Calling LLM...")
    answer = await chat([
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ])
    print(f"[RAG] Answer preview: {answer[:100]}...")

    citations = [{
        "instructor": r["uploader_name"],
        "document":   r["document_name"],
        "program":    r["program"],
        "subject":    r["subject"],
        "similarity": round(r["similarity"], 3),
    } for r in results.data]

    return {"answer": answer, "citations": citations, "found": True}