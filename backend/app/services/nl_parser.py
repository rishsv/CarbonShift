"""Natural Language parser for jobs."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.time import now_utc

settings = get_settings()


def parse_nl_job(text: str) -> dict:
    """Parse a natural language prompt into a Draft Job spec.
    
    Uses regex for the hackathon, falls back to LLM if configured and enabled.
    """
    text_lower = text.lower()
    now = now_utc()
    
    # Defaults
    draft = {
        "name": "Draft Job",
        "archetype": "batch_inference",
        "priority": 3,
        "duration_h": 1.0,
        "gpus": 0,
        "gpu_type": None,
        "cpu_cores": 4,
        "preemptible": False,
        "green_only": False,
        "release_ts": now.isoformat(),
        "deadline_ts": (now + timedelta(hours=24)).isoformat(),
    }
    
    # Simple regex heuristics
    
    # GPUs
    gpu_match = re.search(r"(\d+)\s*(a100|v100|t4|h100)s?", text_lower)
    if gpu_match:
        draft["gpus"] = int(gpu_match.group(1))
        draft["gpu_type"] = gpu_match.group(2).upper()
        draft["archetype"] = "ml_training"
    else:
        # Fallback for just "gpu"
        g_match = re.search(r"(\d+)\s*gpu", text_lower)
        if g_match:
            draft["gpus"] = int(g_match.group(1))
            draft["gpu_type"] = "T4" # default
            draft["archetype"] = "ml_training"

    # Duration
    dur_match = re.search(r"(\d+(?:\.\d+)?)\s*h(?:our)?s?", text_lower)
    if dur_match:
        draft["duration_h"] = float(dur_match.group(1))

    # Preemptible
    if "interrupt" in text_lower or "preempt" in text_lower or "spot" in text_lower:
        draft["preemptible"] = True
        
    # Priority
    if "urgent" in text_lower or "high priority" in text_lower or "p1" in text_lower:
        draft["priority"] = 5
        draft["deadline_ts"] = (now + timedelta(hours=max(4.0, draft["duration_h"] + 1))).isoformat()
    elif "low priority" in text_lower or "background" in text_lower or "p5" in text_lower:
        draft["priority"] = 1
        draft["deadline_ts"] = (now + timedelta(hours=72)).isoformat()

    # Green only
    if "green" in text_lower or "zero carbon" in text_lower:
        draft["green_only"] = True
        
    # Name
    if "train" in text_lower:
        draft["name"] = "ML Model Training"
        draft["archetype"] = "ml_training"
    elif "render" in text_lower:
        draft["name"] = "Video Rendering"
        draft["archetype"] = "render_transcode"

    # If LLM is enabled and an API key is present, we could call it here.
    if settings.ALLOW_EXTERNAL_CALLS and settings.ANTHROPIC_API_KEY:
        try:
            from app.services.llm import ask_llm
            prompt = f"""Extract job scheduling parameters from this text and return ONLY valid JSON matching this schema:
            {{ "name": str, "archetype": str, "priority": int(1-5), "duration_h": float, "gpus": int, "gpu_type": str|null, "cpu_cores": int, "preemptible": bool, "green_only": bool, "deadline_hours_from_now": float }}
            Text: "{text}"
            """
            response = ask_llm(prompt)
            import json
            
            # Strip markdown json block if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
                
            llm_draft = json.loads(cleaned)
            
            # Merge
            for k, v in llm_draft.items():
                if k == "deadline_hours_from_now":
                    draft["deadline_ts"] = (now + timedelta(hours=v)).isoformat()
                elif k in draft:
                    draft[k] = v
        except Exception as e:
            from app.core.logging import logger
            logger.warning(f"LLM parsing failed: {e}")

    return draft
