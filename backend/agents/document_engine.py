"""
WAR ROOM — Document Engine
Finalizes response documents at session end using Z.AI GLM-5 via OpenAI SDK.
Collects agent draft sections and session context, then produces
polished deliverables (regulatory notifications, executive briefings, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from config.settings import get_settings
from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    EVENT_SESSION_FINALIZING,
    EVENT_SESSION_PACKAGE_READY,
)

logger = logging.getLogger(__name__)

# ── Finalization Model ───────────────────────────────────────────────────
# Uses Z.AI GLM-5 (zai_scenario_model) for complex document finalization.

FINALIZATION_PROMPT = """\
You are the Document Finalization Engine for WAR ROOM.

You are given:
1. A DOCUMENT SPEC describing what document to produce
2. AGENT DRAFT SECTIONS written during the crisis session
3. SESSION CONTEXT including crisis brief, decisions, conflicts, and intel

Your job: produce a FINAL, publication-ready document that:
- Follows the template_type format ({template_type})
- Incorporates all agent draft content intelligently
- Fills gaps with session context
- Uses professional, appropriate tone for the document type
- Includes proper structure (headings, sections)
- References applicable legal frameworks if specified: {legal_framework}

DOCUMENT: {doc_title}
OWNER: {owner_agent}
DEADLINE: {deadline_hours}h from session start

AGENT DRAFTS:
{draft_sections}

SESSION CONTEXT:
Crisis Title: {crisis_title}
Crisis Brief: {crisis_brief}
Agreed Decisions: {agreed_decisions}
Open Conflicts: {open_conflicts}
Critical Intel: {critical_intel}
Resolution Score: {resolution_score}
Threat Level: {threat_level}

Produce the complete, finalized document text. No meta-commentary.
"""


async def finalize_all_documents(
    session_id: str,
) -> list[dict]:
    """
    Finalize all required documents for a session.
    Called at session close.

    Returns:
        List of finalized document dicts with doc_id, title, and content.
    """
    from utils.firestore_helpers import _get_db
    from utils.events import push_event

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        logger.warning(f"Session {session_id} not found for document finalization")
        return []

    session_data = doc.to_dict()
    required_docs = session_data.get("required_documents", [])

    if not required_docs:
        logger.info(f"No required documents for session {session_id}")
        return []

    # Push finalizing event
    await push_event(session_id, EVENT_SESSION_FINALIZING, {
        "document_count": len(required_docs),
        "message": "Finalizing response documents...",
    })

    # Finalize each document in parallel
    tasks = [
        finalize_document(doc_spec, session_data)
        for doc_spec in required_docs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    finalized = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"Document finalization failed for {required_docs[i].get('doc_id', '?')}: {result}"
            )
            finalized.append({
                "doc_id": required_docs[i].get("doc_id", "unknown"),
                "title": required_docs[i].get("title", "Unknown"),
                "status": "failed",
                "error": str(result),
            })
        else:
            finalized.append(result)

    # Push package ready event
    await push_event(session_id, EVENT_SESSION_PACKAGE_READY, {
        "documents": [
            {"doc_id": d["doc_id"], "title": d["title"], "status": d.get("status", "finalized")}
            for d in finalized
        ],
    })

    # Store finalized documents back to session
    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id) \
            .update({"finalized_documents": finalized})

    logger.info(f"Finalized {len(finalized)} documents for session {session_id}")
    return finalized


async def finalize_document(
    doc_spec: dict,
    session_data: dict,
) -> dict:
    """
    Finalize a single document using Z.AI GLM-5.

    Args:
        doc_spec: The document specification (from required_documents).
        session_data: The full session data dict.

    Returns:
        Dict with doc_id, title, content, and status.
    """
    settings = get_settings()
    doc_id = doc_spec.get("doc_id", "unknown")
    title = doc_spec.get("title", "Untitled")

    # Collect draft sections for this document
    drafts = session_data.get("document_drafts", {}).get(doc_id, {})
    draft_text = ""
    if drafts:
        for section_name, section_data in drafts.items():
            draft_text += f"\n## {section_name}\n"
            draft_text += f"By: {section_data.get('by', 'unknown')}\n"
            draft_text += f"Status: {section_data.get('status', 'draft')}\n"
            draft_text += f"{section_data.get('content', '')}\n"
    else:
        draft_text = "(No agent drafts were submitted for this document)"

    # Build the prompt
    prompt = FINALIZATION_PROMPT.format(
        template_type=doc_spec.get("template_type", "executive_briefing"),
        legal_framework=doc_spec.get("legal_framework", "N/A"),
        doc_title=title,
        owner_agent=doc_spec.get("owner_agent_id", "unassigned"),
        deadline_hours=doc_spec.get("deadline_hours", 72),
        draft_sections=draft_text,
        crisis_title=session_data.get("crisis_title", ""),
        crisis_brief=session_data.get("crisis_brief", ""),
        agreed_decisions=_format_list(session_data.get("agreed_decisions", [])),
        open_conflicts=_format_list(session_data.get("open_conflicts", [])),
        critical_intel=_format_list(session_data.get("critical_intel", [])),
        resolution_score=session_data.get("resolution_score", 50),
        threat_level=session_data.get("threat_level", "elevated"),
    )

    content = ""

    if settings.zai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.zai_api_key,
                base_url=settings.zai_base_url,
            )

            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=settings.zai_scenario_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a specialist document writer for crisis incident response. "
                            f"You follow {doc_spec.get('legal_framework', 'best practices')} precisely. "
                            f"Produce professional, legally accurate documents. No meta-commentary."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )

            content = (response.choices[0].message.content or "").strip()
            if content:
                logger.info(f"Document '{title}' finalized with Z.AI {settings.zai_scenario_model}")
        except Exception as e:
            logger.warning(f"Document finalization failed: {e}")

    if not content:
        content = f"[DOCUMENT FINALIZATION PENDING]\n\nDraft sections:\n{draft_text}"
        logger.warning(f"Finalization unavailable for document '{title}', using draft fallback")

    return {
        "doc_id": doc_id,
        "title": title,
        "content": content,
        "status": "finalized" if content and not content.startswith("[DOCUMENT") else "draft_fallback",
        "finalized_at": datetime.now(timezone.utc).isoformat(),
        "template_type": doc_spec.get("template_type", "executive_briefing"),
    }


def _format_list(items: list) -> str:
    """Format a list of dicts into readable text for the prompt."""
    if not items:
        return "None"
    lines = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("text", item.get("description", str(item)))
            lines.append(f"- {text}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)
