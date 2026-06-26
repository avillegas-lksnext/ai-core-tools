"""
MaxToolRoundsMiddleware

Enforces a maximum number of tool rounds:
    (model -> tool(s)) x N
    + final model response (no tools)

A round is counted when a model response includes at least one tool call.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from utils.exceptions import ToolRoundLimitReached
from utils.logger import get_logger

logger = get_logger(__name__)


class MaxToolRoundsMiddleware(AgentMiddleware):
    """Limit the number of model->tools rounds per agent run."""

    TOOL_BUDGET_EXHAUSTED_KEY = "_tool_budget_exhausted"
    TOOL_BUDGET_USED_KEY = "_tool_budget_used"
    TOOL_ROUND_COUNTER_KEY = "_current_tool_rounds"

    def __init__(
        self,
        max_rounds: int,
    ) -> None:
        if max_rounds < 1:
            raise ValueError(
                f"max_rounds must be >= 1, got {max_rounds}"
            )

        self.max_rounds = max_rounds

        logger.info(
            "MaxToolRoundsMiddleware initialized with max_rounds=%d",
            max_rounds,
        )

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        response = handler(request)
        return self._process_model_response(request, response)

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        response = await handler(request)
        return self._process_model_response(request, response)

    def _process_model_response(
        self,
        request: Any,
        response: Any,
    ) -> Any:

        state = getattr(request, "state", None)

        if not isinstance(state, dict):
            return response
        
        messages = self._get_messages(request)
        
        rounds_used = self._count_current_turn_rounds(messages)

        logger.info(
            "Tool rounds used=%d max_rounds=%d",
            rounds_used,
            self.max_rounds,
        )

        ai_message = self._extract_ai_message(response)

        if ai_message is None:
            return response

        tool_calls = getattr(ai_message, "tool_calls", None) or []

        #
        # Final answer
        #
        if not tool_calls:
            return response
        
        next_round = rounds_used + 1

        state[self.TOOL_ROUND_COUNTER_KEY] = next_round

        #
        # Budget exhausted
        #
        if next_round > self.max_rounds:

            state = getattr(request, "state", None)

            if isinstance(state, dict):
                state[self.TOOL_BUDGET_EXHAUSTED_KEY] = True
                state[self.TOOL_BUDGET_USED_KEY] = rounds_used

            raise ToolRoundLimitReached(
                rounds_used=rounds_used,
                max_rounds=self.max_rounds,
            )

        logger.info(
            "Allowing tool round %d/%d",
            next_round,
            self.max_rounds,
        )

        return response

    def _get_messages(
        self,
        request: Any,
    ) -> list[Any]:

        state = getattr(request, "state", {}) or {}

        messages = state.get("messages", [])

        return messages if isinstance(messages, list) else []

    def _count_current_turn_rounds(
        self,
        messages: list[Any],
    ) -> int:

        rounds = 0

        current_turn = []

        for msg in reversed(messages):

            current_turn.append(msg)

            if msg.__class__.__name__ == "HumanMessage":
                break

        for msg in reversed(current_turn):

            if getattr(msg, "tool_calls", None):
                rounds += 1

        return rounds

    def _extract_ai_message(
        self,
        response: Any,
    ) -> Any | None:

        result = getattr(response, "result", None)

        if not isinstance(result, list):
            return None

        if not result:
            return None

        return result[0]