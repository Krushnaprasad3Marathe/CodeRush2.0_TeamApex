"""
Aegis MOS — Google Gemini AI Client.

Provides AI-powered capabilities:
  1. Anomaly diagnosis — plain-language root-cause explanations
  2. Scheduling explanations — human-readable rationale for planning decisions
  3. Procedure suggestions — recovery steps for detected anomalies

Falls back to template-based explanations when the API is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("aegis.ai")

_runtime_api_key: str | None = None
_model = None


def set_api_key(api_key: str) -> bool:
    """Set Gemini API key at runtime."""
    global _runtime_api_key, _model
    _runtime_api_key = api_key.strip()
    _model = None  # Force re-initialization
    os.environ["GEMINI_API_KEY"] = _runtime_api_key
    model = _get_model(_runtime_api_key)
    return model is not None


def get_current_api_key() -> str | None:
    """Return currently active API key if configured."""
    return (
        _runtime_api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
    )


def _call_gemini_rest(prompt: str, api_key: str | None = None) -> str | None:
    """Call Google Gemini 2.0 Flash REST API directly with zero extra dependencies."""
    key = (
        api_key
        or _runtime_api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
        or ""
    ).strip()
    if not key:
        return None

    import json
    import urllib.request
    import urllib.error

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        logger.warning(f"Gemini REST HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        logger.warning(f"Gemini REST call failed: {e}")
        return None


def _get_model(api_key: str | None = None):
    """Lazy-init the Gemini model with fallback model names."""
    global _model
    if _model is not None and not api_key:
        return _model

    key = (
        api_key
        or _runtime_api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
        or ""
    ).strip()

    if not key:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]:
            try:
                model = genai.GenerativeModel(model_name)
                _model = model
                logger.info(f"Gemini AI model initialized successfully ({model_name})")
                return _model
            except Exception:
                continue
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Gemini: {e}")
        return None


SYSTEM_PROMPT = """You are the AI diagnostics engine for Aegis MOS, a spacecraft
mission operations system. You analyze telemetry data and anomaly alerts from
a CubeSat digital twin simulation.

Your responses should be:
- Concise and technical, suitable for mission operators
- Use proper spacecraft terminology
- Focus on actionable insights
- Never speculate beyond the data provided
- Reference specific subsystem names and telemetry values

When explaining root causes, follow the subsystem coupling chain:
Attitude → Solar input → SOC → Bus voltage
Power draw → Heat → Temperature → Heater → More power draw
Eclipse → No solar → SOC drops → Thermal changes
Downlink → Power draw + Storage changes
"""


async def diagnose_anomaly(
    alerts: list[dict],
    state: dict,
    correlator_output: dict | None = None,
    api_key: str | None = None,
) -> str:
    """
    Generate a plain-language anomaly diagnosis.

    Uses Gemini if available, otherwise falls back to template.
    """
    import json

    state_summary = (
        f"Battery SOC: {state.get('battery_soc', 0):.1%}, "
        f"Bus Voltage: {state.get('bus_voltage', 0):.2f}V, "
        f"Temperature: {state.get('temp_c', 0):.1f}°C, "
        f"Solar Input: {state.get('solar_input_w', 0):.1f}W, "
        f"Storage: {state.get('storage_used_mb', 0):.0f}/{state.get('storage_capacity_mb', 2048):.0f}MB, "
        f"In Eclipse: {state.get('in_eclipse', False)}, "
        f"Attitude: {state.get('attitude_deg', 0):.1f}°"
    )

    alert_text = "\n".join(
        f"- [{a.get('severity', 'unknown').upper()}] {a.get('description', 'No description')} "
        f"(subsystem: {a.get('subsystem', '?')}, variable: {a.get('variable', '?')})"
        for a in alerts
    )

    correlator_text = ""
    if correlator_output:
        correlator_text = (
            f"\nCorrelator analysis: Root cause identified as "
            f"'{correlator_output.get('root_subsystem', 'unknown')}' subsystem. "
            f"Downstream effects: {', '.join(correlator_output.get('downstream_effects', []))}"
        )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Current spacecraft state:\n{state_summary}\n\n"
        f"Active anomaly alerts:\n{alert_text}\n"
        f"{correlator_text}\n\n"
        f"Provide a concise (2-3 sentence) diagnosis explaining the root cause "
        f"and its cascading effects. Address the operator directly."
    )

    rest_result = _call_gemini_rest(prompt, api_key)
    if rest_result:
        return rest_result

    return _fallback_diagnosis(alerts, correlator_output)


async def explain_scheduling_decision(
    decision_context: dict,
    api_key: str | None = None,
) -> str:
    """
    Generate a human-readable explanation for a scheduling decision.
    """
    model = _get_model(api_key)

    if model is None:
        return _fallback_schedule_explanation(decision_context)

    try:
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"A scheduling decision was made:\n"
            f"Node: {decision_context.get('node_name', 'unknown')}\n"
            f"Decision type: {decision_context.get('decision_type', 'unknown')}\n"
            f"Activity: {decision_context.get('activity_type', 'N/A')}\n"
            f"Input state: {decision_context.get('input_state', {})}\n"
            f"Output state: {decision_context.get('output_state', {})}\n\n"
            f"Explain this decision in one clear sentence for the mission planner."
        )

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"Gemini scheduling explanation failed: {e}")
        return _fallback_schedule_explanation(decision_context)


async def suggest_procedure(
    anomaly: dict,
    state: dict,
    api_key: str | None = None,
) -> list[dict]:
    """
    Suggest recovery procedure steps for an anomaly.
    """
    model = _get_model(api_key)

    if model is None:
        return _fallback_procedure(anomaly, state)

    try:
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"An anomaly has been detected:\n"
            f"Subsystem: {anomaly.get('subsystem', 'unknown')}\n"
            f"Description: {anomaly.get('description', 'N/A')}\n"
            f"Severity: {anomaly.get('severity', 'unknown')}\n\n"
            f"Current state: Battery {state.get('battery_soc', 0):.0%}, "
            f"Temp {state.get('temp_c', 0):.1f}°C, "
            f"Voltage {state.get('bus_voltage', 0):.2f}V\n\n"
            f"Suggest 3-5 recovery procedure steps. "
            f"Format each step as: Step N: [Title] - [Description]\n"
            f"Keep each step concise."
        )

        response = model.generate_content(prompt)
        # Parse response into steps
        steps = []
        for line in response.text.strip().split("\n"):
            line = line.strip()
            if line and line.lower().startswith("step"):
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    title = parts[1].strip().split("-")[0].strip()
                    desc = parts[1].strip().split("-", 1)[1].strip() if "-" in parts[1] else ""
                    steps.append({
                        "step": len(steps) + 1,
                        "title": title,
                        "description": desc,
                        "status": "pending",
                    })
        return steps if steps else _fallback_procedure(anomaly, state)

    except Exception as e:
        logger.error(f"Gemini procedure suggestion failed: {e}")
        return _fallback_procedure(anomaly, state)


# ── Fallback templates ──────────────────────────────────────────────
def _fallback_diagnosis(
    alerts: list[dict],
    correlator_output: dict | None = None,
) -> str:
    """Template-based diagnosis when Gemini is unavailable."""
    n_alerts = len(alerts)
    subsystems = list(set(a.get("subsystem", "unknown") for a in alerts))

    if correlator_output:
        root = correlator_output.get("root_subsystem", "unknown")
        downstream = correlator_output.get("downstream_effects", [])
        return (
            f"{n_alerts} alert{'s' if n_alerts != 1 else ''} across "
            f"{len(subsystems)} subsystem{'s' if len(subsystems) != 1 else ''} — "
            f"root cause: {root} subsystem fault"
            + (f" causing cascading effects in: {', '.join(downstream)}" if downstream else "")
        )

    if n_alerts == 1:
        a = alerts[0]
        return f"Anomaly detected in {a.get('subsystem', 'unknown')}: {a.get('description', 'Unknown issue')}"

    return f"{n_alerts} anomalies detected across {', '.join(subsystems)} subsystems. Investigation recommended."


def _fallback_schedule_explanation(context: dict) -> str:
    """Template-based scheduling explanation."""
    node = context.get("node_name", "scheduler")
    dtype = context.get("decision_type", "scheduling")
    activity = context.get("activity_type", "activity")
    return f"{node}: {dtype} decision for {activity}"


def _fallback_procedure(anomaly: dict, state: dict) -> list[dict]:
    """Template-based recovery procedure."""
    subsystem = anomaly.get("subsystem", "unknown")
    steps = [
        {"step": 1, "title": "Assess Current State", "description": f"Review {subsystem} subsystem telemetry and confirm anomaly.", "status": "pending"},
        {"step": 2, "title": "Reduce Load", "description": "Pause non-essential operations to reduce resource consumption.", "status": "pending"},
        {"step": 3, "title": "Isolate Subsystem", "description": f"Isolate {subsystem} to prevent cascade to other systems.", "status": "pending"},
        {"step": 4, "title": "Apply Corrective Action", "description": f"Apply standard recovery procedure for {subsystem}.", "status": "pending"},
        {"step": 5, "title": "Verify Recovery", "description": "Monitor telemetry to confirm subsystem returns to nominal.", "status": "pending"},
    ]
    return steps
