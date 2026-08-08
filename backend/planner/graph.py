"""
Aegis MOS / Space Aegis — LangGraph Mission Planner State Graph (F5).

Constructs the directed state graph for autonomous mission activity scheduling.
Connects separate node passes:
  [propose_observation] ➔ [check_power_budget] ➔ [check_comms_window] ➔ [resolve_conflict] ➔ [commit_to_plan]

Every decision node generates human-readable explanations and persists the execution trace.
"""

from __future__ import annotations
import logging
import uuid
from typing import Any

from planner.nodes.propose_observation import propose_observation_node
from planner.nodes.check_power_budget import check_power_budget_node
from planner.nodes.check_comms_window import check_comms_window_node
from planner.nodes.resolve_conflict import resolve_conflict_node
from planner.nodes.commit_to_plan import commit_to_plan_node

logger = logging.getLogger("aegis.planner.graph")


class MissionPlannerGraph:
    """
    LangGraph StateGraph for satellite mission planning and constraint verification.
    """

    def __init__(self, suspect_streams: set[str] | None = None):
        self.suspect_streams = suspect_streams or set()
        self._last_result: dict[str, Any] = {}
        self._decisions: list[dict[str, Any]] = []

    @property
    def activities(self) -> list[dict[str, Any]]:
        return self._last_result.get("activities", [])

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return self._decisions

    @property
    def violations(self) -> list[dict[str, Any]]:
        return self._last_result.get("violations", [])

    async def run(self, current_state: dict[str, Any], mission_day_ticks: int = 86400) -> dict[str, Any]:
        """
        Executes the LangGraph pipeline from initial state through commit.
        """
        pipeline_state: dict[str, Any] = {
            **current_state,
            "suspect_streams": list(self.suspect_streams),
            "mission_day_ticks": mission_day_ticks,
            "decisions": [],
            "warnings": [],
            "conflicts": [],
        }

        # 1. Node: Propose Observation candidates
        pipeline_state = propose_observation_node(pipeline_state)

        # 2. Node: Check Power Budget & Solar Charging
        pipeline_state = check_power_budget_node(pipeline_state)

        # 3. Node: Check Comms Contact Windows & Downlinks
        pipeline_state = check_comms_window_node(pipeline_state)

        # 4. Node: Resolve Conflicts & Validate Hard Constraints
        pipeline_state = resolve_conflict_node(pipeline_state)

        # 5. Node: Commit to Plan & Persist Execution Trace
        final_result = await commit_to_plan_node(pipeline_state)

        self._last_result = final_result
        self._decisions = final_result.get("decisions", [])

        logger.info(
            "Plan generated via LangGraph: %d activities, %d violations, %d decisions",
            len(final_result.get("activities", [])),
            len(final_result.get("violations", [])),
            len(self._decisions),
        )
        return final_result

    def generate_plan_sync(self, current_state: dict[str, Any]) -> dict[str, Any]:
        """Synchronous wrapper for local fallback loops."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In running loop, run nodes directly
                s = {
                    **current_state,
                    "suspect_streams": list(self.suspect_streams),
                    "decisions": [],
                    "warnings": [],
                }
                s = propose_observation_node(s)
                s = check_power_budget_node(s)
                s = check_comms_window_node(s)
                s = resolve_conflict_node(s)
                
                acts = s.get("resolved_activities", [])
                acts.sort(key=lambda a: a.start_t)
                act_dicts = [a.to_dict() if hasattr(a, 'to_dict') else a for a in acts]
                viol_dicts = [v.to_dict() if hasattr(v, 'to_dict') else v for v in s.get("violations", [])]
                
                res = {
                    "status": "scheduled",
                    "activities": act_dicts,
                    "decisions": s.get("decisions", []),
                    "violations": viol_dicts,
                    "total_activities": len(act_dicts),
                    "constraint_violations": len(viol_dicts),
                }
                self._last_result = res
                self._decisions = s.get("decisions", [])
                return res
            else:
                return loop.run_until_complete(self.run(current_state))
        except Exception:
            return self.generate_plan_sync_fallback(current_state)

    def generate_plan_sync_fallback(self, current_state: dict[str, Any]) -> dict[str, Any]:
        s = {
            **current_state,
            "suspect_streams": list(self.suspect_streams),
            "decisions": [],
            "warnings": [],
        }
        s = propose_observation_node(s)
        s = check_power_budget_node(s)
        s = check_comms_window_node(s)
        s = resolve_conflict_node(s)
        
        acts = s.get("resolved_activities", [])
        acts.sort(key=lambda a: a.start_t)
        act_dicts = [a.to_dict() if hasattr(a, 'to_dict') else a for a in acts]
        viol_dicts = [v.to_dict() if hasattr(v, 'to_dict') else v for v in s.get("violations", [])]
        
        res = {
            "status": "scheduled",
            "activities": act_dicts,
            "decisions": s.get("decisions", []),
            "violations": viol_dicts,
            "total_activities": len(act_dicts),
            "constraint_violations": len(viol_dicts),
        }
        self._last_result = res
        self._decisions = s.get("decisions", [])
        return res

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        """Retrieve a specific decision by ID for /plan/explain/{decision_id}."""
        for d in self._decisions:
            if d.get("decision_id") == decision_id:
                return d
        return None
