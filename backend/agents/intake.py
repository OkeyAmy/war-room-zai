"""
WAR ROOM — Document Intake (Multimodal)
Processes uploaded files (PDFs, images, text) using Z.AI GLM-4.6V
to extract crisis-relevant context before scenario generation.

Uses Z.AI via OpenAI-compatible SDK.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path

from config.settings import get_settings

logger = logging.getLogger(__name__)

# ── Extraction Prompt ────────────────────────────────────────────────────

INTAKE_PROMPT = """\
You are the Document Intake Engine for WAR ROOM.

You have been given uploaded files related to a crisis scenario.
Your job: extract ALL crisis-relevant information from these documents.

For each document, extract:
1. Key facts, figures, and data points
2. Stakeholder names and relationships
3. Timeline of events
4. Legal or regulatory references
5. Financial figures or impact estimates
6. Technical details (systems, infrastructure)
7. Risk factors and vulnerabilities

Output a structured summary that can be used by the Scenario Analyst
to generate a more accurate and detailed crisis simulation.

Be thorough but concise. Focus on actionable intelligence.
"""


async def process_uploaded_documents(
    files: list[dict],
) -> str:
    """
    Process uploaded files using Z.AI GLM-4.6V multimodal.

    Args:
        files: List of dicts with keys:
            - filename: str
            - content: bytes (raw file content)
            - content_type: str (MIME type)

    Returns:
        Concatenated extracted context string for the scenario analyst.
    """
    if not files:
        return ""

    extracted_parts = []

    for file_info in files:
        filename = file_info.get("filename", "unknown")
        content = file_info.get("content", b"")
        content_type = file_info.get("content_type", "")

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        try:
            extracted = await _extract_from_file(
                filename=filename,
                content=content,
                content_type=content_type,
            )
            if extracted:
                extracted_parts.append(f"--- FILE: {filename} ---\n{extracted}\n")
                logger.info(f"Intake: extracted {len(extracted)} chars from {filename}")
        except Exception as e:
            logger.warning(f"Intake: failed to process {filename}: {e}")
            extracted_parts.append(f"--- FILE: {filename} ---\n[Processing failed: {e}]\n")

    return "\n".join(extracted_parts)


async def _extract_from_file(
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    """
    Extract text content from a single file using Z.AI GLM.

    Supports:
    - Plain text / markdown: decoded directly (no LLM needed)
    - Binary files (PDF, images): Z.AI GLM-4.6V multimodal vision call
    """
    # For plain text files, just decode directly
    if content_type.startswith("text/"):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            return content.decode("latin-1", errors="replace")

    # For binary files (PDF, images), use Z.AI multimodal
    settings = get_settings()
    if not settings.zai_api_key:
        logger.warning("ZAI_API_KEY not set — cannot process binary file via vision LLM")
        return f"[Could not extract content from {filename}: ZAI_API_KEY not configured]"

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.zai_api_key,
            base_url=settings.zai_base_url,
        )

        b64_content = base64.b64encode(content).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64_content}"

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.zai_vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"{INTAKE_PROMPT}\n\n"
                            f"File: {filename}\n"
                            f"Extract all crisis-relevant information from this file. "
                            f"Include key facts, dates, names, figures, legal references, and risk factors. "
                            f"Be thorough and structured."
                        ),
                    },
                ],
            }],
            max_tokens=3000,
        )

        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"Intake extraction failed for {filename}: {e}")

    return f"[Could not extract content from {filename}]"


async def process_uploaded_file_path(file_path: str) -> str:
    """
    Convenience: process a single file from a filesystem path.
    Used in local development.
    """
    path = Path(file_path)
    if not path.exists():
        return f"[File not found: {file_path}]"

    content_type, _ = mimetypes.guess_type(str(path))
    content = path.read_bytes()

    return await process_uploaded_documents([{
        "filename": path.name,
        "content": content,
        "content_type": content_type or "application/octet-stream",
    }])
