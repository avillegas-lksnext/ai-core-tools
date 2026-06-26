"""
Streaming agent execution service.

A thin SSE adapter over AgentExecutionService.  The setup and post-processing
phases are fully delegated to AgentExecutionService._prepare_turn() and
_finalize_turn(); this service only owns the astream loop that yields tokens
and tool events to the client.
"""

from typing import AsyncGenerator, Dict, List, Any

import psycopg.errors
from sqlalchemy.orm import Session

from langgraph.errors import GraphRecursionError
from langchain_core.messages import AIMessage

from tools.agentTools import create_agent, prepare_agent_config, build_human_message
from tools.langsmith_config import (
    apply_tracing_to_config,
    build_tracing_config,
    resolve_langsmith_settings,
)
from tools.streaming_utils import (
    format_sse_event,
    map_stream_event,
    SSE_TOKEN,
)
from services.agent_execution_service import AgentExecutionService
from utils.logger import get_logger
from utils.exceptions import ToolRoundLimitReached

logger = get_logger(__name__)


class AgentStreamingService:
    """Service for streaming agent responses via Server-Sent Events."""

    def __init__(self, db: Session = None) -> None:
        self.execution_service = AgentExecutionService()
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_agent_chat(
        self,
        agent_id: int,
        message: str,
        file_references: list | None = None,
        search_params: dict | None = None,
        user_context: dict | None = None,
        conversation_id: int | None = None,
        execution_profile: str | None = None,
        db: Session | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream an agent chat turn as SSE events.

        Yields ``format_sse_event`` strings for each event in the following
        sequence:

        1. ``metadata`` — emitted immediately after setup with conversation/agent
           metadata so the client can bind the conversation ID before tokens
           arrive.
        2. ``thinking`` / ``tool_start`` / ``tool_end`` — emitted while the agent
           reasons and calls tools.
        3. ``token`` — one per partial LLM text chunk.
        4. ``done`` — emitted once after the stream finishes, carrying the full
           parsed response, conversation ID, and any generated files.
        5. ``error`` — emitted instead of ``done`` if an unhandled exception
           occurs.

        Args:
            agent_id: Primary key of the agent to execute.
            message: The user's text message.
            file_references: Pre-resolved file-reference objects as returned by
                ``FileManagementService``.  Each object must expose
                ``filename``, ``content``, ``file_type``, ``file_id``, and
                ``file_path``.
            search_params: Optional silo search parameters forwarded to
                ``create_agent``.
            user_context: Caller context dict (``user_id``, ``app_id``,
                ``email``, …).
            conversation_id: ID of an existing conversation to continue.  When
                ``None`` and the agent has memory enabled a new conversation is
                created automatically.
            db: SQLAlchemy session.  If omitted the instance-level ``self.db``
                is used.

        Yields:
            SSE-formatted strings (``"data: {...}\\n\\n"``).
        """

        effective_db = db or self.db
        mcp_client = None

        try:
            # ----------------------------------------------------------------
            # 1. Setup phase — delegates entirely to AgentExecutionService
            # ----------------------------------------------------------------
            ctx = await self.execution_service._prepare_turn(
                agent_id=agent_id,
                message=message,
                file_references=file_references,
                search_params=search_params,
                user_context=user_context,
                conversation_id=conversation_id,
                execution_profile=execution_profile,
                db=effective_db,
            )

            # ----------------------------------------------------------------
            # 2. Emit early metadata event so the client has conversation_id
            # ----------------------------------------------------------------
            yield format_sse_event(
                "metadata",
                {
                    "conversation_id": ctx.effective_conv_id,
                    "agent_id": agent_id,
                    "agent_name": ctx.agent.name,
                    "has_memory": ctx.agent.has_memory,
                },
            )

            # ----------------------------------------------------------------
            # 3. Build agent chain
            # ----------------------------------------------------------------
            agent_chain, mcp_client, llm = await create_agent(
                ctx.fresh_agent,
                ctx.search_params,
                ctx.session_id_for_cache,
                ctx.user_context,
                ctx.working_dir,
                ctx.runtime_llm_config,
            )

            config = prepare_agent_config(ctx.fresh_agent, ctx.runtime_llm_config)

            if ctx.fresh_agent.has_memory and ctx.session_id_for_cache:
                config["configurable"]["thread_id"] = (
                    f"thread_{ctx.fresh_agent.agent_id}_{ctx.session_id_for_cache}"
                )
                logger.info(
                    "Using session-aware thread_id: %s",
                    config["configurable"]["thread_id"],
                )
            else:
                config["configurable"]["thread_id"] = (
                    f"thread_{ctx.fresh_agent.agent_id}"
                )

            config["configurable"]["question"] = ctx.enhanced_message

            # ----------------------------------------------------------------
            # 4. Build the HumanMessage payload (handles multimodal images)
            # ----------------------------------------------------------------
            message_payload = build_human_message(
                ctx.fresh_agent, ctx.enhanced_message, ctx.image_files, ctx.user_context
            )

            # ----------------------------------------------------------------
            # 5. Attach LangSmith tracer + metadata when configured
            # ----------------------------------------------------------------
            ls_settings = resolve_langsmith_settings(ctx.fresh_agent.app)
            if ls_settings:
                tracer, overrides = build_tracing_config(
                    ls_settings,
                    agent=ctx.fresh_agent,
                    user_context=ctx.user_context,
                    conversation_id=ctx.effective_conv_id,
                    session_id=ctx.session_id_for_cache,
                )
                apply_tracing_to_config(config, tracer, overrides)
                logger.info(
                    "LangSmith tracing ENABLED — project='%s' source='%s'",
                    ls_settings.project_name,
                    ls_settings.source,
                )

            # ----------------------------------------------------------------
            # 6. Streaming loop — the only part that stays in this service
            # ----------------------------------------------------------------
            # Return the sync connection to the pool for the duration of the
            # stream: astream uses the async checkpointer, not this session, so
            # holding it across LLM I/O would exhaust the pool. ctx objects expire
            # but stay attached, so _finalize_turn reloads them on demand.
            if effective_db is not None:
                effective_db.commit()

            accumulated_content = ""

            max_iters = None
            if ctx.runtime_llm_config and ctx.runtime_llm_config.agent_limits:
                max_iters = ctx.runtime_llm_config.agent_limits.get("max_iterations")
            
            input_state = {
                "messages": [message_payload],
                "_current_tool_rounds": 0,
            }

            tool_budget_exhausted = False

            tool_outputs: List[str] = []

            partial_response = False

            try:
                async for mode, chunk in agent_chain.astream(
                    input_state,
                    config=config,
                    stream_mode=["messages", "updates"],
                ):
                    events = map_stream_event(mode, chunk)

                    if events:
                        for event in events:
                            if event["type"] == SSE_TOKEN:
                                accumulated_content += event["data"].get(
                                    "content",
                                    ""
                                )

                            yield format_sse_event(
                                event["type"],
                                event["data"],
                            )
                    
                    if mode == "updates":
                        def extract_messages(obj):
                            if isinstance(obj, dict):

                                if "messages" in obj:
                                    yield from obj["messages"]

                                for value in obj.values():
                                    yield from extract_messages(value)

                            elif isinstance(obj, list):

                                for item in obj:
                                    yield from extract_messages(item)
                        
                        for msg in extract_messages(chunk):

                            if msg.__class__.__name__ == "ToolMessage":

                                content = getattr(msg, "content", None)

                                if content:
                                    tool_outputs.append(str(content))

            except ToolRoundLimitReached as exc:

                logger.info(
                    "Tool round limit reached for agent %s "
                    "(used=%d max=%d)",
                    ctx.agent_id,
                    exc.rounds_used,
                    exc.max_rounds,
                )

                tool_budget_exhausted = True

            except GraphRecursionError as gre:

                logger.warning(
                    "Streaming hit recursion/tool limit for agent %s; "
                    "finishing with partial output: %s",
                    ctx.agent_id,
                    str(gre),
                )

                if not accumulated_content.strip():
                    accumulated_content = (
                        "I reached the operational limit while solving "
                        "this request. Here is the best result I could "
                        "produce so far."
                    )
                
                partial_response = True
                
            if tool_budget_exhausted:
                logger.info(
                    "Generating final answer from gathered tool results"
                )

                if tool_outputs:

                    synthesis_prompt = f"""
                        You have reached the maximum tool budget.

                        ORIGINAL USER REQUEST:

                        {message}

                        INSTRUCTIONS:

                        1. Respond in exactly the same language as the original user request.
                        2. Use only information contained in the tool results.
                        3. Never invent information that was not obtained from the tools.
                        4. Complete every part of the request that can be answered.
                        5. If some parts cannot be completed because the required tool results are missing, explicitly state that.
                        6. Do not mention tool budgets, tool limits, internal system details, or implementation details.
                        7. Provide a coherent final answer, not a list of limitations.

                        TOOL RESULTS:

                        {chr(10).join(tool_outputs)}
                    """

                    final_response = await llm.ainvoke(
                        synthesis_prompt
                    )

                    accumulated_content = str(
                        getattr(
                            final_response,
                            "content",
                            final_response,
                        )
                    )

                    await agent_chain.aupdate_state(
                        config,
                        {
                            "messages": [
                                AIMessage(content=accumulated_content)
                            ]
                        },
                    )

            # ----------------------------------------------------------------
            # 7. Post-processing phase — delegates to AgentExecutionService
            # ----------------------------------------------------------------
            result = await self.execution_service._finalize_turn(
                ctx, accumulated_content, effective_db
            )

            # ----------------------------------------------------------------
            # 8. Emit done event
            # ----------------------------------------------------------------
            done_payload = {
                "response": result["parsed_response"],
                "conversation_id": result["effective_conv_id"],
                "files": result["files_data"],
                "partial": partial_response,    # only when recursion error occurred
            }

            yield format_sse_event(
                "done",
                done_payload,
            )

            logger.info(
                "DONE EVENT YIELDED"
            )

        except (
            psycopg.errors.AdminShutdown,
            psycopg.errors.ConnectionFailure,
            psycopg.OperationalError,
        ) as exc:
            # Stale pool connection terminated by PostgreSQL (e.g. server
            # restart or pg_terminate_backend). The pool discards the bad
            # connection automatically; a single retry will receive a fresh one.
            logger.warning(
                "Checkpointer connection lost (%s), retrying once: %s",
                type(exc).__name__,
                str(exc),
            )
            yield format_sse_event("error", {"message": "Connection error, please retry."})
        except Exception as exc:
            logger.error("Error in streaming agent chat: %s", str(exc), exc_info=True)
            yield format_sse_event("error", {"message": str(exc)})

        finally:
            if mcp_client:
                logger.info("MCP client will be cleaned up automatically")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
