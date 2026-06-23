"""
AgentExecutionContext — plain data container produced by _prepare_turn().

Carries every field that the execution and finalization phases need so that
_prepare_turn, _execute_agent_async, and _finalize_turn can pass state without
a growing argument list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from schemas.execution_profile_schemas import ExecutionProfile, ToolDepth
from schemas.runtime_llm_config_schemas import RuntimeLLMConfig


@dataclass
class AgentExecutionContext:
    """Immutable snapshot of all setup state for one agent chat turn."""

    # Core identity
    agent_id: int
    agent: Any                          # Agent ORM instance (lightweight, pre-access-check)
    fresh_agent: Any                    # Agent ORM instance with all relationships loaded

    # Immutable config layer (v0)
    agent_config_id: Optional[int] = None  # AgentConfigVersion.config_id (None if no config version)
    agent_config_version: Optional[int] = None  # AgentConfigVersion.version_number (None if no config version)
    system_prompt: str = ""             # Resolved system prompt (from config version or agent)
    persona: Optional[str] = None       # Resolved persona (from config version or agent)
    domain: Optional[str] = None        # Resolved domain (from config version or agent)
    tone: Optional[str] = None          # Resolved tone (from config version or agent)
    constraints: List[str] = field(default_factory=list)  # Resolved constraints (from config version or agent)
    allowed_tools: List[str] = field(default_factory=list)  # Resolved allowed tools (from config version or agent)
    memory_scope: str = "none"          # Resolved memory scope (from config version or agent)

    # Dynamic execution state (v0)
    execution_profile: Optional[ExecutionProfile] = None  # ExecutionProfile instance (None if no profile)
    derived_tool_policy: ToolDepth = ToolDepth.NONE  # Derived tool depth (from execution profile or agent)
    derived_rag_policy: bool = False  # Derived RAG enabled (from execution profile or agent)

    # Message
    enhanced_message: str = ""               # Text message after file-content injection
    image_files: List[Dict[str, Any]] = field(default_factory=list)   # Image file dicts extracted from processed_files

    # Session / conversation
    session: Optional[Any] = None       # SessionManagementService session object
    conversation: Optional[Any] = None  # Conversation ORM instance (None when no memory)
    effective_conv_id: Optional[int] = None  # Resolved conversation ID (auto-created or passed)
    session_id_for_cache: Optional[str] = None  # LangGraph thread ID suffix

    # Working directory
    working_dir: Optional[str] = None
    pre_existing_files: set = field(default_factory=set)

    # Original inputs (needed by finalize for metadata)
    processed_files: List[Dict[str, Any]] = field(default_factory=list)
    search_params: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None

    # Runtime provider config
    runtime_llm_config: Optional[RuntimeLLMConfig] = None  # Resolved runtime LLM config for this turn
