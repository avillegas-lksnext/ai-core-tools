from langchain.messages import HumanMessage, SystemMessage, AnyMessage
from langchain.agents import create_agent as create_langchain_agent, AgentState
from langchain.agents.middleware import SummarizationMiddleware
from models.agent import Agent
from models.silo import Silo, SiloType
from langchain.tools import BaseTool, tool
from tools.outputParserTools import get_parser_model_by_id
from tools.aiServiceTools import get_llm, get_output_parser
from tools.ai.dateTimeTools import get_current_date
from tools.ai.fileTools import fetch_file_in_base64
from tools.ai.workspaceTools import create_download_url_tool
from typing import Any, Optional, Dict, List
from langchain_core.tools.retriever import create_retriever_tool
from services.silo_service import SiloService
from langchain_mcp_adapters.client import MultiServerMCPClient
from services.agent_cache_service import CheckpointerCacheService
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
import json
import asyncio
import os
import base64
import mimetypes
from urllib.parse import parse_qsl, urlparse
from utils.logger import get_logger
from utils.mcp_auth_utils import prepare_mcp_headers, get_user_token_from_context
from utils.mcp_ssl_utils import inject_ssl_config
from tools.skill_tools import (
    create_skill_file_reader_tool,
    create_skill_loader_tool,
    generate_skills_system_prompt_section,
)
from tools.sandbox import (
    create_sandbox_builtin_tools,
    create_sandbox_repl_tools,
    create_sandbox_skill_tools,
    resolve_provider,
)

logger = get_logger(__name__)


_AUTH_QUERY_PARAMS = {
    "access_token",
    "api_key",
    "apikey",
    "api-key",
    "key",
    "tavilyapikey",
    "token",
}


def _url_contains_auth_credentials(url: str) -> bool:
    try:
        query_params = parse_qsl(urlparse(url).query, keep_blank_values=False)
    except ValueError:
        return False
    return any(name.lower() in _AUTH_QUERY_PARAMS for name, _value in query_params)


def _merge_mcp_auth_headers(
    server_name: str,
    server_config: Dict[str, Any],
    auth_headers: Dict[str, str],
) -> None:
    """Add Mattin auth headers without replacing MCP-specific credentials."""
    if 'url' not in server_config:
        return

    existing_headers = server_config.setdefault('headers', {})
    existing_header_names = {str(key).lower() for key in existing_headers}
    applied_headers = {}
    has_url_credentials = _url_contains_auth_credentials(str(server_config.get("url", "")))

    for header_name, header_value in auth_headers.items():
        normalized_header_name = header_name.lower()
        if normalized_header_name in existing_header_names:
            logger.info(
                "Preserving configured MCP header '%s' for server: %s",
                header_name,
                server_name,
            )
            continue
        if normalized_header_name == "authorization" and has_url_credentials:
            logger.info(
                "Skipping Mattin Authorization header for MCP server with URL credentials: %s",
                server_name,
            )
            continue
        applied_headers[header_name] = header_value

    if applied_headers:
        existing_headers.update(applied_headers)
        logger.info(f"Added auth headers to MCP server: {server_name}")


def _redact_mcp_connections(connections: Dict[str, Any]) -> Dict[str, Any]:
    redacted = {}
    sensitive_headers = {"authorization", "x-api-key", "api-key"}

    for server_name, server_config in connections.items():
        if not isinstance(server_config, dict):
            redacted[server_name] = server_config
            continue

        safe_config = dict(server_config)
        headers = safe_config.get("headers")
        if isinstance(headers, dict):
            safe_config["headers"] = {
                key: "<redacted>" if str(key).lower() in sensitive_headers else value
                for key, value in headers.items()
            }
        redacted[server_name] = safe_config

    return redacted


def _tool_name_for_language(language: str) -> str:
    return "python_repl" if language == "python" else f"{language}_repl"


def _sandbox_id_for_log(sandbox_handle: Any) -> str:
    sandbox_id = getattr(sandbox_handle, "sandbox_id_if_created", None)
    if sandbox_id:
        return sandbox_id
    is_materialized = getattr(sandbox_handle, "is_materialized", None)
    if callable(is_materialized) and not is_materialized():
        return "<lazy>"
    return getattr(sandbox_handle, "sandbox_id", "<unknown>")


def _build_available_tool_metadata(
    agent: Agent,
    *,
    working_dir: Optional[str],
    code_languages: list[str],
) -> list[dict[str, str]]:
    """Return compact tool metadata for the Skill tool router."""
    metadata: list[dict[str, str]] = [
        {
            "name": "get_current_date",
            "category": "utility",
            "description": "Get the current date.",
        }
    ]

    if working_dir:
        metadata.append({
            "name": "download_url_to_workspace",
            "category": "file",
            "description": "Download a URL into the conversation working directory.",
        })

    for tool_name in getattr(agent, "server_tools", None) or []:
        metadata.append({
            "name": tool_name,
            "category": "provider_tool",
            "description": f"Provider-side tool: {tool_name}.",
        })

    if getattr(agent, "silo_id", None) is not None:
        metadata.append({
            "name": "silo_retriever",
            "category": "retrieval",
            "description": "Search the configured knowledge base.",
        })

    for language in code_languages:
        tool_name = _tool_name_for_language(language)
        if language == "typescript":
            description = (
                "Run TypeScript directly. Prefer for TypeScript/Node implementations, "
                "including PPTX generation with PptxGenJS when dependencies are ready."
            )
        elif language == "bash":
            description = (
                "Run shell commands. Use mainly for setup, dependency checks, "
                "filesystem inspection, or command-line orchestration."
            )
        elif language == "python":
            description = "Run Python code for Python libraries and data/document workflows."
        else:
            description = f"Run {language} code."
        metadata.append({
            "name": tool_name,
            "category": "code_execution",
            "description": description,
        })

    if "bash" in code_languages:
        for name, description in [
            ("SandboxInfo", "Sandbox-only: summarize workspace rules, tools, and actionable limits."),
            ("PWD", "Sandbox-only: print the current sandbox working directory."),
            ("Read", "Sandbox-only: read an absolute-path file with line numbers."),
            ("Write", "Sandbox-only: create or overwrite an absolute-path file."),
            ("Edit", "Sandbox-only: replace exact text in an absolute-path file."),
            ("LS", "Sandbox-only: list directory entries in compact form."),
            ("Glob", "Sandbox-only: find files by glob pattern."),
            ("Grep", "Sandbox-only: search file contents with regex."),
            ("Stat", "Sandbox-only: inspect compact file or directory metadata."),
            ("Bash", "Sandbox-only: run Linux shell commands."),
            ("BashOutput", "Sandbox-only: read output from a background Bash command."),
            ("KillShell", "Sandbox-only: terminate a background Bash command."),
        ]:
            metadata.append({
                "name": name,
                "category": "sandbox_builtin",
                "description": description,
            })

    if getattr(agent, "skill_associations", None):
        metadata.extend([
            {
                "name": "load_skill",
                "category": "skill",
                "description": "Load Skill instructions and prepare bundled sandbox files.",
            },
            {
                "name": "read_skill_file",
                "category": "skill",
                "description": "Read supporting files bundled with a loaded Skill.",
            },
        ])

    if getattr(agent, "enable_code_interpreter", False) and getattr(agent, "skill_associations", None):
        metadata.extend([
            {
                "name": "activate_sandbox_skill",
                "category": "recovery",
                "description": "Retry Skill sandbox activation after load_skill/setup problems.",
            },
            {
                "name": "list_active_sandbox_skills",
                "category": "debug",
                "description": "List Skills currently active in the sandbox.",
            },
        ])

    return metadata


def _build_selected_skill_payloads(skill_associations: list, selected_names: set) -> list[dict]:
    """Return selected Skill instruction snippets for the tool router."""
    selected = {str(name).lower().strip() for name in selected_names}
    if not selected:
        return []

    payloads: list[dict] = []
    for assoc in skill_associations:
        skill = getattr(assoc, "skill", None)
        if skill is None or skill.name.lower().strip() not in selected:
            continue
        allowed_tools = getattr(skill, "allowed_tools", None)
        if isinstance(allowed_tools, str):
            try:
                allowed_tools = json.loads(allowed_tools)
            except Exception:
                allowed_tools = None
        content = getattr(skill, "content", "") or ""
        payloads.append({
            "name": skill.name,
            "description": getattr(skill, "description", "") or "",
            "instructions": content[:6000],
            "allowed_tools": allowed_tools or [],
            "supporting_files": [
                getattr(file, "path", "")
                for file in (getattr(skill, "files", None) or [])
                if getattr(file, "path", "")
            ],
        })
    return payloads


class MCPClientManager:
    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClientManager, cls).__new__(cls)
        return cls._instance

    async def get_client(self, agent: Agent = None, user_context: Optional[Dict] = None):
        """Get or create an MCP client for the given agent with authentication support.
        
        Args:
            agent: The agent to create the client for
            user_context: Optional user context containing authentication tokens
            
        Returns:
            MultiServerMCPClient or None
        """
        # Always create a new client for each agent execution to avoid ClosedResourceError
        # Don't use singleton pattern as the client lifecycle is tied to the agent execution
        if agent is not None:
            connections = {}
            for mcp_assoc in agent.mcp_associations:
                mcp_config = mcp_assoc.mcp
                try:
                    # Get the config from the database
                    connection_config = mcp_config.to_connection_dict()
                    if connection_config:
                        # Add authentication headers if user context is provided
                        if user_context:
                            auth_token = get_user_token_from_context(user_context)
                            if auth_token:
                                # Prepare headers for MCP server authentication
                                headers = prepare_mcp_headers(auth_token)
                                
                                # Add headers to each connection in the config,
                                # preserving provider credentials already configured.
                                for server_name, server_config in connection_config.items():
                                    if isinstance(server_config, dict):
                                        _merge_mcp_auth_headers(server_name, server_config, headers)
                        
                        connections.update(connection_config)
                except ValueError as e:
                    logger.error(f"Error configuring MCP {mcp_config.name}: {e}")
                    continue
                
            if connections:
                # Inject SSL configuration for connections that need it
                # Check each MCP config's ssl_verify setting
                for mcp_assoc in agent.mcp_associations:
                    mcp_cfg = mcp_assoc.mcp
                    ssl_verify = mcp_cfg.ssl_verify if mcp_cfg.ssl_verify is not None else True
                    if not ssl_verify:
                        cfg_dict = mcp_cfg.to_connection_dict()
                        for server_name in cfg_dict:
                            if server_name in connections:
                                inject_ssl_config({server_name: connections[server_name]}, ssl_verify=False)
                
                logger.info(
                    "Creating new MCP client with connections: %s",
                    _redact_mcp_connections(connections),
                )
                # Create a new client each time - don't reuse the singleton
                # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient cannot be used as a context manager
                client = MultiServerMCPClient(connections=connections)
                return client
            else:
                logger.warning("No valid MCP configurations found for agent")
                return None
                
        return None

    async def close(self):
        # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient doesn't need manual cleanup
        # The client is managed internally by the library
        if self._client is not None:
            self._client = None

async def create_agent(
    agent: Agent,
    search_params=None,
    session_id=None,
    user_context: Optional[Dict] = None,
    working_dir: Optional[str] = None,
    sandbox_handle: Optional[Any] = None,
    sandbox_provider: Optional[Any] = None,
    sandbox_session_key: Optional[str] = None,
    sandbox_session_service: Optional[Any] = None,
    recent_messages: Optional[List[Dict]] = None,
):
    """Create a new agent instance with cached checkpointer if memory is enabled.
    
    Args:
        agent: The agent to create
        search_params: Optional search parameters for silo-based retrieval
        session_id: Optional session ID for memory-enabled agents (used to cache checkpointer)
        user_context: Optional user context containing authentication tokens for MCP
        working_dir: Optional per-conversation working directory
        sandbox_handle: Optional sandbox handle created during turn preparation
        sandbox_provider: Optional provider matching sandbox_handle
        sandbox_session_key: Optional key for sandbox active-use leasing
        sandbox_session_service: Optional service used for sandbox active-use leasing
    """
    llm = get_llm(agent)
    if llm is None:
        raise ValueError("No LLM found for agent")

    output_parser = get_output_parser(agent)
    format_instructions = ""
    pydantic_model = None

    if agent.output_parser_id is not None:
        try:
            pydantic_model = get_parser_model_by_id(agent.output_parser_id)
            format_instructions = output_parser.get_format_instructions()
            format_instructions = format_instructions.replace('{', '{{').replace('}', '}}')
        except Exception as e:
            logger.error(f"Error getting Pydantic model: {str(e)}")
            pydantic_model = None

    # Handle checkpointer management for memory-enabled agents
    checkpointer = None
    if agent.has_memory:
        # Use the session_id if provided, otherwise use "default"
        cache_session_id = session_id if session_id else "default"
        # Create the async PostgreSQL checkpointer in the current event loop
        # This ensures the checkpointer uses the same event loop as ainvoke()
        checkpointer = await CheckpointerCacheService.get_async_checkpointer()
        logger.info(f"Using async PostgreSQL checkpointer for agent {agent.agent_id} (session: {cache_session_id})")

    ci_provider_for_prompt = None
    ci_languages: list[str] = []
    if agent.enable_code_interpreter and working_dir:
        ci_provider_for_prompt = sandbox_provider or resolve_provider(agent)
        ci_languages = ci_provider_for_prompt.get_supported_languages()

    # Build system prompt with optional skills section and format instructions
    # In LangChain v1, system_prompt is a static string passed to create_agent
    system_prompt_content = agent.system_prompt
    if hasattr(agent, 'skill_associations') and agent.skill_associations:
        # Step 5.4: run the skill router to pre-select relevant skills.
        # The router makes a small isolated LLM call using only the latest user
        # text plus Skill catalog metadata. It does not receive file contents,
        # conversation memory, the agent prompt, or tool traces.
        router_selected_names: set = set()
        selected_skill_payloads: list[dict] = []
        try:
            from services.skill_router_service import (
                SkillRouterService,
                SkillToolRouterService,
                format_skill_tool_guidance_section,
            )
            import json as _json

            # Build a lightweight catalog from already-loaded ORM objects (no extra DB query)
            inline_catalog = []
            for _assoc in agent.skill_associations:
                _s = _assoc.skill
                if _s is None:
                    continue
                _fm: dict = {}
                if _s.frontmatter:
                    try:
                        _fm = _json.loads(_s.frontmatter)
                    except Exception:
                        pass
                inline_catalog.append({
                    "skill_id": _s.skill_id,
                    "name": _s.name,
                    "description": _s.description or "",
                    "when_to_use": _fm.get("when_to_use"),
                    "disable_model_invocation": bool(_fm.get("disable_model_invocation", False)),
                })

            if inline_catalog:
                _decision = await SkillRouterService().route_with_llm(
                    recent_messages or [],
                    inline_catalog,
                    llm=llm,
                )
                router_selected_names = set(_decision["selected_skill_names"])
                logger.info(
                    "Skill router selected %d skills for agent %s: %s — reason: %s",
                    len(router_selected_names),
                    agent.agent_id,
                    router_selected_names,
                    _decision["reason"],
                )
                selected_skill_payloads = _build_selected_skill_payloads(
                    agent.skill_associations,
                    router_selected_names,
                )

                available_tool_metadata = _build_available_tool_metadata(
                    agent,
                    working_dir=working_dir,
                    code_languages=ci_languages,
                )
                _tool_decision = await SkillToolRouterService().route_with_llm(
                    selected_skills=selected_skill_payloads,
                    available_tools=available_tool_metadata,
                    llm=llm,
                )
                tool_guidance_section = format_skill_tool_guidance_section(_tool_decision)
                if tool_guidance_section:
                    system_prompt_content = (
                        system_prompt_content + "\n" + tool_guidance_section
                    )
                    logger.info(
                        "Skill tool router added guidance for agent %s (%d skills)",
                        agent.agent_id,
                        len(selected_skill_payloads),
                    )
        except Exception as _router_exc:
            logger.warning(
                "Skill router failed for agent %s: %s — proceeding without routing",
                agent.agent_id,
                _router_exc,
            )
            router_selected_names = set()

        skills_section = generate_skills_system_prompt_section(
            agent.skill_associations,
            active_skill_names=router_selected_names,
            handle=sandbox_handle,
        )
        if skills_section:
            system_prompt_content = system_prompt_content + "\n" + skills_section

    if working_dir:
        system_prompt_content = (
            system_prompt_content
            + "\n\n<workspace>\n"
            + f"Working directory: {working_dir}\n"
            + "Workspace layout:\n"
            + "- input/: user-provided files. Treat these as source material.\n"
            + "- work/: scratch files, scripts, dependencies, extracted content, and intermediate data.\n"
            + "- output/: final files intended for the user to download.\n"
            + "User-uploaded files are available under input/; reference them as input/<filename>.\n"
            + "Use `download_url_to_workspace` to save any URL (generated image, PDF, report…) "
            + "to output/ so the user can download it from the files panel.\n"
            + "</workspace>"
        )

    if agent.enable_code_interpreter and working_dir:
        _ci_provider = sandbox_provider or ci_provider_for_prompt or resolve_provider(agent)
        _ci_languages = ci_languages or _ci_provider.get_supported_languages()
        _tool_names = ", ".join(f"`{_tool_name_for_language(lang)}`" for lang in _ci_languages)
        system_prompt_content = (
            system_prompt_content
            + "\n\n<code_interpreter>\n"
            + f"You have access to the following code execution tools: {_tool_names}.\n"
            + "Each tool accepts source code in the corresponding language and returns stdout + stderr.\n"
            + (
                "When bash is available, you also have sandbox builtin tools: "
                "`SandboxInfo`, `PWD`, `Read`, `Write`, `Edit`, `LS`, `Glob`, `Grep`, `Stat`, `Bash`, "
                "`BashOutput`, and `KillShell`. These operate exclusively inside the Linux sandbox. "
                "Use `SandboxInfo` for workspace rules and limits; use `PWD` when you need "
                "the sandbox workspace root. Use absolute sandbox paths with file editing tools.\n"
                if "bash" in _ci_languages else ""
            )
            + "Read uploaded files from input/<filename>.\n"
            + "Use work/ for temporary files, package installs, scripts, and dependencies.\n"
            + "Save only final user-facing deliverables in output/ and print the output/<filename> path.\n"
            + "</code_interpreter>"
        )

    if format_instructions:
        system_prompt_content = (
            system_prompt_content
            + "\n<output_format_instructions>"
            + format_instructions
            + "</output_format_instructions>"
        )

    middleware = []
    if agent.has_memory:
        max_tokens = agent.memory_max_tokens or 4000
        max_messages = agent.memory_max_messages or 20
        from models.agent import DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
        trim_tokens = agent.memory_summarize_threshold or DEFAULT_MEMORY_SUMMARIZE_THRESHOLD
        summarization = SummarizationMiddleware(
            model=llm,
            trigger=("tokens", max_tokens),
            keep=("messages", max_messages),
            trim_tokens_to_summarize=trim_tokens,
        )
        middleware.append(summarization)
        logger.info(
            f"SummarizationMiddleware configured for agent {agent.agent_id}: "
            f"trigger=('tokens', {max_tokens}), keep=('messages', {max_messages}), "
            f"trim_tokens_to_summarize={trim_tokens}"
        )

    tools = []

    # Provider-side tools — injected from agent.server_tools using provider-specific formats
    _SERVER_TOOL_FORMATS = {
        "OpenAI":     {"web_search": {"type": "web_search"}, "image_generation": {"type": "image_generation"}, "code_interpreter": {"type": "code_interpreter"}, "file_search": {"type": "file_search"}},
        "Azure":      {"web_search": {"type": "web_search"}, "image_generation": {"type": "image_generation"}, "code_interpreter": {"type": "code_interpreter"}, "file_search": {"type": "file_search"}},
        "Anthropic":  {"web_search": {"type": "web_search_20250305"}, "code_interpreter": {"type": "codeExecution_20250825"}},
        "Google":     {"web_search": {"type": "google_search"}, "code_interpreter": {"type": "code_execution"}},
        "MistralAI":  {},
        "Custom":     {},
    }
    provider_name = agent.ai_service.provider if agent.ai_service else None
    provider_map = _SERVER_TOOL_FORMATS.get(provider_name, {})
    for tool_name in (getattr(agent, 'server_tools', None) or []):
        tool_def = provider_map.get(tool_name)
        if tool_def:
            tools.append(tool_def)
            logger.info("Server-side tool '%s' injected for provider %s", tool_name, provider_name)
        else:
            logger.warning("Server-side tool '%s' not supported by provider %s — skipped", tool_name, provider_name)

    for tool in agent.tool_associations:
        sub_agent = tool.tool
        tools.append(await IACTTool.create(
            sub_agent,
            user_context=user_context,
            working_dir=working_dir,
            sandbox_handle=sandbox_handle,
            sandbox_provider=sandbox_provider,
            sandbox_session_key=sandbox_session_key,
            sandbox_session_service=sandbox_session_service,
        ))

    # Base tools — always available for every agent
    tools.append(get_current_date)
    if working_dir:
        tools.append(create_download_url_tool(working_dir))

    if agent.silo_id is not None:

        retriever_tool = get_retriever_tool(agent.silo, search_params)
        if retriever_tool is not None:
            tools.append(retriever_tool)

    if agent.enable_code_interpreter and working_dir:
        os.makedirs(working_dir, exist_ok=True)
        if sandbox_provider is None:
            sandbox_provider = resolve_provider(agent)
        if sandbox_handle is None:
            logger.warning(
                "Code interpreter tool requested without prepared sandbox handle; "
                "creating fallback sandbox during tool assembly for agent %s",
                agent.agent_id,
            )
            sandbox_handle = sandbox_provider.create_sandbox(working_dir=working_dir)
        if sandbox_session_service is None and sandbox_session_key is not None:
            try:
                from services.sandbox_session_service import sandbox_session_service as _sss
                sandbox_session_service = _sss
            except Exception:
                sandbox_session_service = None
        repl_tools = create_sandbox_repl_tools(
            sandbox_handle,
            sandbox_provider,
            session_key=sandbox_session_key,
            session_service=sandbox_session_service,
        )
        tools.extend(repl_tools)
        builtin_tools = create_sandbox_builtin_tools(sandbox_handle, sandbox_provider)
        tools.extend(builtin_tools)
        logger.info(
            "Sandbox tools added for agent %s (repl=%s, builtins=%s, working_dir=%s, sandbox_id=%s, provider=%s)",
            agent.agent_id,
            [t.name for t in repl_tools],
            [t.name for t in builtin_tools],
            working_dir,
            _sandbox_id_for_log(sandbox_handle),
            sandbox_handle.provider_name,
        )

        # IT-3: lazy skill activation tools (only when runtime skills are attached)
        skill_associations = getattr(agent, 'skill_associations', None) or []
        sandbox_skill_tools = create_sandbox_skill_tools(sandbox_handle, sandbox_provider, skill_associations)
        if sandbox_skill_tools:
            tools.extend(sandbox_skill_tools)
            runtime_skill_count = sum(
                1 for a in skill_associations
                if a.skill and a.skill.runtime == "python-sandbox"
            )
            logger.info(
                "Sandbox skill tools added for agent %s (%d runtime skills)",
                agent.agent_id, runtime_skill_count,
            )

    mcp_client = None
    try:
        logger.info("Starting MCP tools loading...")
        mcp_client = await MCPClientManager().get_client(agent, user_context)
        if (mcp_client):
            mcp_tools = await mcp_client.get_tools()
            logger.info(f"MCP tools loaded successfully: {len(mcp_tools)} tools")
            if (mcp_tools):
                tools.extend(mcp_tools)
    except Exception as e:
        logger.error(f"Error loading MCP tools: {e}", exc_info=True)
        # As of langchain-mcp-adapters 0.1.0, no manual cleanup needed
        mcp_client = None

    # Add skill loader tool if agent has skills
    if hasattr(agent, 'skill_associations') and agent.skill_associations:
        skill_tool = create_skill_loader_tool(
            agent.skill_associations,
            sandbox_handle=sandbox_handle,
            sandbox_provider=sandbox_provider,
        )
        if skill_tool:
            tools.append(skill_tool)
            logger.info(f"Skill loader tool added with {len(agent.skill_associations)} skills")
        skill_file_tool = create_skill_file_reader_tool(agent.skill_associations)
        if skill_file_tool:
            tools.append(skill_file_tool)
            logger.info(
                "Skill file reader tool added with %d skills",
                len(agent.skill_associations),
            )

    if pydantic_model:
        # In LangChain v1, response_format accepts the pydantic model directly.
        # It defaults to ProviderStrategy (native structured output) if supported,
        # falling back to ToolStrategy (artificial tool calling) otherwise.
        agent_chain = create_langchain_agent(
            model=llm,
            system_prompt=system_prompt_content,
            response_format=pydantic_model,
            tools=tools,
            checkpointer=checkpointer,
            middleware=middleware or [],
        )
    else:
        agent_chain = create_langchain_agent(
            model=llm,
            system_prompt=system_prompt_content,
            tools=tools,
            checkpointer=checkpointer,
            middleware=middleware or [],
        )

    # Add logging for the created agent
    logger.info(f"Created agent with {len(tools)} tools")
    logger.info(f"Memory enabled: {agent.has_memory}")
    logger.info(f"Output parser: {agent.output_parser_id is not None}")

    return agent_chain, mcp_client


def prepare_agent_config(agent):
    """Helper function to prepare agent configuration."""
    config = {
        "configurable": {
            "thread_id": f"thread_{agent.agent_id}"
        },
        "recursion_limit": 200,
    }
    return config


def parse_agent_response(response_text, agent):
    """Helper function to parse agent response.
    
    In LangChain v1, structured output is returned in the 'structured_response' key
    of the agent result when response_format is used with create_agent.
    """
    if agent.output_parser_id is not None:
        # If response is already a dict (from structured output), return it directly
        if isinstance(response_text, dict):
            return response_text
        
        # If response is a Pydantic model instance, convert to dict
        if hasattr(response_text, 'model_dump'):
            return response_text.model_dump()
        
        # If response is a string, try to parse it as JSON
        content = response_text.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return response_text
    return response_text


def build_human_message(
    agent: Agent,
    message: str,
    image_files: List[Dict],
    user_context: Optional[Dict] = None,
) -> HumanMessage:
    """Build the HumanMessage that will be fed into the agent chain.

    When ``image_files`` is non-empty the content becomes a multimodal list of
    text + image_url blocks.  Images are served via a signed URL when
    ``AICT_BASE_URL`` is set (production), or inlined as base64 data URIs in
    development mode.

    Args:
        agent: The (freshly loaded) Agent ORM instance.
        message: The already-enhanced text message (with file content appended
            if applicable).
        image_files: List of image-file dicts (``file_path`` key required).
        user_context: Caller context dict used to generate signed URLs.

    Returns:
        A ``HumanMessage`` instance ready for ``agent_chain.ainvoke()`` /
        ``agent_chain.astream()``.
    """
    from utils.config import get_app_config

    formatted_message = agent.prompt_template.format(question=message)

    if not image_files:
        return HumanMessage(content=formatted_message)

    app_config = get_app_config()
    tmp_base_folder = app_config["TMP_BASE_FOLDER"]
    aict_base_url = os.getenv("AICT_BASE_URL")

    content: List[Dict] = [{"type": "text", "text": formatted_message}]

    for img in image_files:
        file_path: str = img.get("file_path", "")
        if not file_path:
            logger.warning("Image file has no file_path — skipping: %s", img)
            continue

        # Normalise to forward slashes and strip leading slash
        file_path = file_path.replace("\\", "/").lstrip("/")

        if aict_base_url:
            # Production mode — generate a signed static URL
            aict_base_url = aict_base_url.rstrip("/")
            user_email: Optional[str] = (
                user_context.get("email") if user_context else None
            )
            if user_email:
                from utils.security import generate_signature

                sig = generate_signature(file_path, user_email)
                url = (
                    f"{aict_base_url}/static/{file_path}"
                    f"?user={user_email}&sig={sig}"
                )
            else:
                url = f"{aict_base_url}/static/{file_path}"

            logger.info("Adding image to message using signed URL: %s", url)
            content.append({"type": "image_url", "image_url": {"url": url}})
        else:
            # Development mode — inline as base64 data URI
            full_path = os.path.join(tmp_base_folder, file_path)
            if os.path.exists(full_path):
                try:
                    mime_type, _ = mimetypes.guess_type(full_path)
                    if not mime_type:
                        mime_type = "image/jpeg"
                    with open(full_path, "rb") as fh:
                        encoded = base64.b64encode(fh.read()).decode("utf-8")
                    data_url = f"data:{mime_type};base64,{encoded}"
                    logger.info(
                        "Adding image as base64 (length: %d)", len(encoded)
                    )
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                except Exception as exc:
                    logger.error(
                        "Error encoding image as base64: %s — falling back to URL",
                        exc,
                    )
                    url = f"http://localhost:8000/static/{file_path}"
                    content.append(
                        {"type": "image_url", "image_url": {"url": url}}
                    )
            else:
                url = f"http://localhost:8000/static/{file_path}"
                logger.warning(
                    "Image not found at %s — falling back to URL: %s",
                    full_path,
                    url,
                )
                content.append(
                    {"type": "image_url", "image_url": {"url": url}}
                )

    return HumanMessage(content=content)


class IACTTool(BaseTool):
    name: str = "agent_tool"
    description: str = "Search for a repository"
    agent: Agent
    user_context: Optional[Dict] = None
    react_agent: Any = None
    mcp_client: Any = None
    llm: Any = None
    working_dir: Optional[str] = None
    sandbox_handle: Any = None
    sandbox_provider: Any = None
    sandbox_session_key: Optional[str] = None
    sandbox_session_service: Any = None

    def __init__(
        self,
        agent: Agent,
        user_context: Optional[Dict] = None,
        working_dir: Optional[str] = None,
        sandbox_handle: Optional[Any] = None,
        sandbox_provider: Optional[Any] = None,
        sandbox_session_key: Optional[str] = None,
        sandbox_session_service: Optional[Any] = None,
    ) -> None:
        super().__init__(
            agent=agent,
            user_context=user_context,
            working_dir=working_dir,
            sandbox_handle=sandbox_handle,
            sandbox_provider=sandbox_provider,
            sandbox_session_key=sandbox_session_key,
            sandbox_session_service=sandbox_session_service,
        )

        self.agent = agent
        self.user_context = user_context
        self.working_dir = working_dir
        self.sandbox_handle = sandbox_handle
        self.sandbox_provider = sandbox_provider
        self.sandbox_session_key = sandbox_session_key
        self.sandbox_session_service = sandbox_session_service
        self.name = agent.name.replace(" ", "_")
        self.description = agent.description or "Agent tool"
        self.llm = get_llm(agent)
        if self.llm is None:
            raise ValueError("No LLM found for agent")
        self.react_agent = None
        self.mcp_client = None

    @classmethod
    async def create(
        cls,
        agent: Agent,
        user_context: Optional[Dict] = None,
        working_dir: Optional[str] = None,
        sandbox_handle: Optional[Any] = None,
        sandbox_provider: Optional[Any] = None,
        sandbox_session_key: Optional[str] = None,
        sandbox_session_service: Optional[Any] = None,
    ) -> "IACTTool":
        """Build an agent-as-tool, including the sub-agent's MCP tools.

        MCP tools are loaded with an awaited MultiServerMCPClient, which is not
        possible inside a synchronous ``__init__``; hence this async factory. It
        is the only supported way to obtain a ready-to-use ``IACTTool``.
        """
        instance = cls(
            agent,
            user_context=user_context,
            working_dir=working_dir,
            sandbox_handle=sandbox_handle,
            sandbox_provider=sandbox_provider,
            sandbox_session_key=sandbox_session_key,
            sandbox_session_service=sandbox_session_service,
        )

        tools = []
        # Add nested tool agents recursively
        for tool in agent.tool_associations:
            sub_agent = tool.tool
            tools.append(await IACTTool.create(
                sub_agent,
                user_context=user_context,
                working_dir=working_dir,
                sandbox_handle=sandbox_handle,
                sandbox_provider=sandbox_provider,
                sandbox_session_key=sandbox_session_key,
                sandbox_session_service=sandbox_session_service,
            ))

        # Add base useful tools
        tools.append(get_current_date)
        tools.append(fetch_file_in_base64)

        # Add silo retriever if configured
        if agent.silo_id is not None:
            retriever_tool = get_retriever_tool(agent.silo)
            if retriever_tool is not None:
                tools.append(retriever_tool)

        if agent.enable_code_interpreter and working_dir and sandbox_handle is not None:
            if sandbox_provider is None:
                sandbox_provider = resolve_provider(agent)
                instance.sandbox_provider = sandbox_provider
            repl_tools = create_sandbox_repl_tools(
                sandbox_handle,
                sandbox_provider,
                session_key=sandbox_session_key,
                session_service=sandbox_session_service,
            )
            tools.extend(repl_tools)
            logger.info(
                "Shared sandbox REPL tools added for sub-agent %s "
                "(languages=%s, working_dir=%s, sandbox_id=%s, provider=%s)",
                agent.agent_id,
                [t.name for t in repl_tools],
                working_dir,
                _sandbox_id_for_log(sandbox_handle),
                sandbox_handle.provider_name,
            )

            skill_associations = getattr(agent, 'skill_associations', None) or []
            sandbox_skill_tools = create_sandbox_skill_tools(
                sandbox_handle,
                sandbox_provider,
                skill_associations,
            )
            if sandbox_skill_tools:
                tools.extend(sandbox_skill_tools)

        # Add skill tools for sub-agents too. When a parent sandbox was prepared,
        # bind load_skill to the same handle so runtime Skills activate there.
        if hasattr(agent, 'skill_associations') and agent.skill_associations:
            skill_tool = create_skill_loader_tool(
                agent.skill_associations,
                sandbox_handle=sandbox_handle,
                sandbox_provider=sandbox_provider,
            )
            if skill_tool:
                tools.append(skill_tool)
            skill_file_tool = create_skill_file_reader_tool(agent.skill_associations)
            if skill_file_tool:
                tools.append(skill_file_tool)

        # Add MCP tools — mirrors create_agent. A failing MCP server degrades the
        # sub-agent but never breaks its construction.
        try:
            logger.info(f"Starting MCP tools loading for sub-agent {agent.agent_id}...")
            instance.mcp_client = await MCPClientManager().get_client(agent, user_context)
            if instance.mcp_client:
                mcp_tools = await instance.mcp_client.get_tools()
                logger.info(
                    f"MCP tools loaded successfully for sub-agent {agent.agent_id}: "
                    f"{len(mcp_tools)} tools"
                )
                if mcp_tools:
                    tools.extend(mcp_tools)
        except Exception as e:
            logger.error(
                f"Error loading MCP tools for sub-agent {agent.agent_id}: {e}",
                exc_info=True,
            )
            instance.mcp_client = None

        # Build system prompt with optional skills section (LangChain v1 pattern)
        tool_system_prompt = agent.system_prompt or ""
        if agent.system_prompt and hasattr(agent, 'skill_associations') and agent.skill_associations:
            skills_section = generate_skills_system_prompt_section(
                agent.skill_associations,
                handle=sandbox_handle,
            )
            if skills_section:
                tool_system_prompt = tool_system_prompt + "\n" + skills_section

        if working_dir:
            tool_system_prompt = (
                tool_system_prompt
                + "\n\n<workspace>\n"
                + f"Working directory: {working_dir}\n"
                + "Workspace layout:\n"
                + "- input/: user-provided files. Treat these as source material.\n"
                + "- work/: scratch files, scripts, dependencies, extracted content, and intermediate data.\n"
                + "- output/: final files intended for the user to download.\n"
                + "User-uploaded files are available under input/; reference them as input/<filename>.\n"
                + "</workspace>"
            )

        if agent.enable_code_interpreter and working_dir and sandbox_handle is not None:
            _ci_provider = sandbox_provider or resolve_provider(agent)
            _ci_languages = _ci_provider.get_supported_languages()
            _tool_names = ", ".join(f"`{_tool_name_for_language(lang)}`" for lang in _ci_languages)
            tool_system_prompt = (
                tool_system_prompt
                + "\n\n<code_interpreter>\n"
                + f"You have access to the following code execution tools: {_tool_names}.\n"
                + "They run in the same sandbox used by the parent agent and sibling tools.\n"
                + "Read uploaded files from input/<filename>.\n"
                + "Use work/ for temporary files, package installs, scripts, and dependencies.\n"
                + "Save only final user-facing deliverables in output/ and print the output/<filename> path.\n"
                + "</code_interpreter>"
            )

        # Create sub-agent
        instance.react_agent = create_langchain_agent(
            model=instance.llm,
            tools=tools,
            system_prompt=tool_system_prompt if tool_system_prompt else None,
        )
        return instance

    def _run(self, query: str, *args, **kwargs) -> str:
        """Synchronous execution of the agent tool"""
        if self.react_agent is None:
            raise RuntimeError(
                "IACTTool must be built via 'await IACTTool.create(...)' before use."
            )
        try:
            # Format the message using prompt_template if available, otherwise use query directly
            if self.agent.prompt_template:
                try:
                    formatted_prompt = self.agent.prompt_template.format(question=query)
                except KeyError:
                    # If 'question' is not in template, try other common placeholders
                    try:
                        formatted_prompt = self.agent.prompt_template.format(query=query)
                    except KeyError:
                        # If no placeholder works, just use the query
                        logger.warning(f"Could not format prompt_template for agent {self.agent.name}, using query directly")
                        formatted_prompt = query
            else:
                formatted_prompt = query
            
            messages = [HumanMessage(content=formatted_prompt)]
            result = self.react_agent.invoke({"messages": messages})
            
            # Extract the content from the last AI message
            if isinstance(result, dict) and "messages" in result:
                messages_list = result["messages"]
                # Find the last AI message with content
                for msg in reversed(messages_list):
                    if hasattr(msg, 'content') and msg.content:
                        return str(msg.content)
                # Fallback: return the last message content
                if messages_list:
                    last_msg = messages_list[-1]
                    return str(last_msg.content) if hasattr(last_msg, 'content') else str(last_msg)
            
            # If result is a string, return it directly
            return str(result)
            
        except Exception as e:
            logger.error(f"Error executing agent tool {self.name}: {str(e)}")
            return f"Error executing agent tool: {str(e)}"

    def _format_tool_query(self, query: str) -> str:
        """Apply the sub-agent prompt template to a tool query."""
        if self.agent.prompt_template:
            try:
                return self.agent.prompt_template.format(question=query)
            except KeyError:
                try:
                    return self.agent.prompt_template.format(query=query)
                except KeyError:
                    logger.warning(
                        f"Could not format prompt_template for agent {self.agent.name}, using query directly"
                    )
        return query

    @staticmethod
    def _extract_last_message_content(result: Any) -> str:
        """Return the last non-empty message content from a LangGraph result/state."""
        if isinstance(result, dict) and "messages" in result:
            messages_list = result["messages"]
            for msg in reversed(messages_list):
                if hasattr(msg, 'content') and msg.content:
                    return str(msg.content)
            if messages_list:
                last_msg = messages_list[-1]
                return str(last_msg.content) if hasattr(last_msg, 'content') else str(last_msg)
        return str(result)

    def _get_stream_writer_or_none(self):
        try:
            from langgraph.config import get_stream_writer

            return get_stream_writer()
        except Exception:
            return None

    def _emit_subagent_stream_event(self, writer: Any, event: dict) -> None:
        """Forward a nested sub-agent event to the parent graph custom stream."""
        if writer is None or not isinstance(event, dict):
            return

        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}

        if event_type in {"tool_start", "tool_end", "thinking"}:
            raw_tool_call_id = data.get("tool_call_id")
            data = {
                **data,
                "parent_tool_name": self.name,
                "subagent_name": self.agent.name,
                "subagent_id": self.agent.agent_id,
            }
            if raw_tool_call_id:
                data["raw_tool_call_id"] = raw_tool_call_id
                data["tool_call_id"] = f"{self.name}:{self.agent.agent_id}:{raw_tool_call_id}"
            try:
                writer({"type": event_type, "data": data})
            except Exception:
                pass
            return

        if event_type == "code_output":
            try:
                writer({
                    "type": "code_output",
                    "tool_name": data.get("tool_name"),
                    "stream": data.get("stream", "stdout"),
                    "line": data.get("line", ""),
                    "parent_tool_name": self.name,
                    "subagent_name": self.agent.name,
                    "subagent_id": self.agent.agent_id,
                })
            except Exception:
                pass
    
    async def _arun(self, query: str, *args, **kwargs) -> str:
        """Asynchronous execution of the agent tool"""
        if self.react_agent is None:
            raise RuntimeError(
                "IACTTool must be built via 'await IACTTool.create(...)' before use."
            )
        try:
            formatted_prompt = self._format_tool_query(query)
            messages = [HumanMessage(content=formatted_prompt)]
            stream_writer = self._get_stream_writer_or_none()

            if stream_writer is None:
                result = await self.react_agent.ainvoke({"messages": messages})
                return self._extract_last_message_content(result)

            if not hasattr(self.react_agent, "astream"):
                result = await self.react_agent.ainvoke({"messages": messages})
                return self._extract_last_message_content(result)

            from tools.streaming_utils import map_stream_event

            latest_state: Any = None
            async for mode, chunk in self.react_agent.astream(
                {"messages": messages},
                stream_mode=["updates", "custom"],
            ):
                if mode == "updates" and isinstance(chunk, dict):
                    for state_delta in chunk.values():
                        if isinstance(state_delta, dict) and "messages" in state_delta:
                            latest_state = state_delta

                events = map_stream_event(mode, chunk)
                if not events:
                    continue
                for event in events:
                    self._emit_subagent_stream_event(stream_writer, event)

            if latest_state is not None:
                return self._extract_last_message_content(latest_state)

            return ""
            
        except Exception as e:
            logger.error(f"Error executing agent tool {self.name} (async): {str(e)}")
            return f"Error executing agent tool: {str(e)}"

def convert_search_params_to_types(search_params: dict, metadata_definition) -> dict:
    """
    Convert search parameters to their proper types based on metadata definition.
    The search_params dictionary should have a 'filter' key containing the metadata filters.
    
    Args:
        search_params: Dictionary containing search parameters with a 'filter' key
        metadata_definition: OutputParser instance containing field definitions
        
    Returns:
        Dictionary with converted parameter values
    """
    if not search_params or not metadata_definition:
        return search_params
        
    # Create a copy of search_params to avoid modifying the original
    converted_params = search_params.copy()
    
    # Only process the 'filter' key if it exists
    if 'filter' in search_params and search_params['filter']:
        field_definitions = {f['name']: f for f in metadata_definition.fields}
        converted_filter = {}
        
        for key, value in search_params['filter'].items():
            if key in field_definitions:
                field_type = field_definitions[key]['type']
                try:
                    if field_type == 'int':
                        converted_filter[key] = int(value)
                    elif field_type == 'float':
                        converted_filter[key] = float(value)
                    elif field_type == 'bool':
                        converted_filter[key] = bool(value)
                    else:
                        converted_filter[key] = value
                except (ValueError, TypeError):
                    # If conversion fails, keep original value
                    converted_filter[key] = value
            else:
                converted_filter[key] = value
                
        converted_params['filter'] = converted_filter
            
    return converted_params

def get_retriever_tool(silo: Silo, search_params=None):
    
    if silo.silo_id is not None:
        # Convert search parameters to proper types based on metadata definition
        if search_params:
            search_params = convert_search_params_to_types(search_params, silo.metadata_definition)

        retriever = SiloService.get_silo_retriever(silo.silo_id, search_params)
        name = "silo_retriever"
        description = "Use this tool to search for documents in the pgvector collection."
        if silo.silo_type == SiloType.REPO:
            #todo: add description to repository model to compose description
            description = "Use this tool to search for relevant documents in the repository."
        elif silo.silo_type == SiloType.DOMAIN:
            description = f"Use this tool to search for documents. This tool stores information about a web site and this is its description: {silo.domain.description}"
        else:
            description = f"Use this tool to search for documents and information about {silo.description}"

        # Create a wrapper retriever that includes metadata in page_content
        # This ensures the agent can see metadata like holiday_item_id, type, etc.
        # We'll use a closure to capture the retriever instead of storing it as an attribute
        original_retriever = retriever
        
        def format_docs_with_metadata(docs: List[Document]) -> List[Document]:
            """Format documents to include metadata in page_content"""
            formatted_docs = []
            for doc in docs:
                metadata_str = json.dumps(doc.metadata, ensure_ascii=False) if doc.metadata else "{}"
                # Include metadata in the page_content so the agent can see it
                formatted_content = f"Content: {doc.page_content}\nMetadata: {metadata_str}"
                formatted_doc = Document(
                    page_content=formatted_content,
                    metadata=doc.metadata  # Keep original metadata for filtering
                )
                formatted_docs.append(formatted_doc)
            return formatted_docs
        
        class MetadataRetrieverWrapper(BaseRetriever):
            """Wrapper retriever that includes metadata in document content"""
            
            def _get_relevant_documents(self, query: str) -> List[Document]:
                docs = original_retriever.invoke(query)
                return format_docs_with_metadata(docs)
            
            async def _aget_relevant_documents(self, query: str) -> List[Document]:
                docs = await original_retriever.ainvoke(query)
                return format_docs_with_metadata(docs)
        
        # Wrap the retriever to include metadata in content
        wrapped_retriever = MetadataRetrieverWrapper()
        
        # Use default document prompt since metadata is now in page_content
        from langchain_core.prompts import PromptTemplate
        document_prompt = PromptTemplate.from_template("{page_content}")

        return create_retriever_tool(
            retriever=wrapped_retriever, 
            name=name, 
            description=description, 
            response_format="content_and_artifact",
            document_prompt=document_prompt
        )
    return None
