"""LLM integration for Explainability (Decision Cards)."""
from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()


def ask_llm(prompt: str, system_prompt: str = "") -> str:
    """Wrapper for Anthropic Claude 3 Haiku for edge tasks (parsing/explaining)."""
    if not settings.ALLOW_EXTERNAL_CALLS or not settings.ANTHROPIC_API_KEY:
        raise ValueError("External LLM calls are disabled or missing API key.")

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    response = client.messages.create(
        model=settings.LLM_MODEL or "claude-3-haiku-20240307",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def explain_decision(
    job_name: str,
    site_id: str,
    shift_hours: float,
    ci_reduction_pct: float,
    binding_constraint: str,
    risk_flag: str,
) -> str:
    """Generate a human-readable 1-sentence explanation of the optimizer's choice."""
    
    # Deterministic fallback logic
    if shift_hours > 0:
        base = f"Shifted {shift_hours}h to find a greener window, saving {ci_reduction_pct:.0f}% carbon."
    else:
        base = f"Scheduled immediately at {site_id} to meet deadline, saving {ci_reduction_pct:.0f}% vs baseline."
        
    if binding_constraint == "H9 Data Residency":
        base += f" Restricted to {site_id} due to data residency constraints."
    elif binding_constraint == "H8 Dependencies":
        base += " Delayed to wait for predecessor jobs to finish."
        
    if risk_flag == "high":
        base += " Note: High forecast uncertainty in this window."
        
    # If LLM is disabled, just return the deterministic base string
    if not settings.ALLOW_EXTERNAL_CALLS or not settings.ANTHROPIC_API_KEY:
        return base
        
    try:
        sys = "You are a concise AI scheduler explaining why you placed a job at a specific time/location. Keep it to one professional sentence. Do not use AI tropes."
        prompt = f"Rewrite this concisely: {base}"
        return ask_llm(prompt, sys)
    except Exception:
        return base
