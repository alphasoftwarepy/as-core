"""
AS Code — API Routes

OpenAI-compatible endpoints:
- POST /v1/chat/completions — Chat inference (streaming + non-streaming)
- GET  /v1/models           — List available models
- GET  /v1/status           — System status (AS Code extension)
- POST /v1/cancel           — Cancel generation (AS Code extension)
- GET  /v1/providers        — List providers (AS Code extension)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from pydantic import BaseModel
from api.models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelInfo,
    ModelListResponse,
    StatusResponse,
    UsageInfo,
)
from api.streaming import stream_inference_results
from api.document_service import get_document_service
from api.database import get_db
from config.settings import get_settings
from providers.base import InferenceRequest
from router.smart_router import SmartRouter

logger = logging.getLogger("as-code.api.routes")

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])


# ── POST /v1/chat/completions ──────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """OpenAI-compatible chat completion endpoint.

    Supports:
    - Streaming (SSE) and non-streaming responses
    - Smart routing via model="auto"
    - Explicit model selection
    - Temperature and token control
    - RAG NotebookLM context injection into SYSTEM prompt (X-Enable-RAG / X-Mode / X-Pipeline headers)
    - Skill prompt injection (X-Skill header)
    - Working Memory injection (X-Session-Id header)
    - Runtime Coordinator (workflow state, task progression, suggestions)
    """
    engine = getattr(request.app.state, "engine", None)
    smart_router = getattr(request.app.state, "router", None) or SmartRouter()
    settings = getattr(request.app.state, "settings", None) or get_settings()

    # Generate request ID for tracking and cancellation
    request_id = body.get_request_id()

    # Get the last user message for routing
    user_message = body.get_last_user_message()
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message provided")

    # Validate explicit model if requested (R10)
    model_param = body.model if body.model and body.model != "auto" else None
    if model_param:
        registered = []
        if engine and hasattr(engine, "get_registered_models"):
            registered = [m["id"] for m in engine.get_registered_models()]
        elif settings and hasattr(settings, "models") and settings.models:
            registered = list(settings.models.keys())
        else:
            registered = ["chat", "code", "reasoning", "olmoe"]

        if model_param not in registered:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_param}' is not registered or unavailable",
            )

    resident_model = getattr(request.app.state, "selected_model", None)
    model_id, _ = smart_router.route(user_message, model_param, resident_model=resident_model)

    if not engine:
        raise HTTPException(status_code=503, detail="Inference engine not ready")

    # ── Language Detection & Root Prompt Localization ─────────────
    # Heuristically detect if user query is Spanish (FIX 1 & 2)
    spanish_indicators = {"el", "la", "los", "las", "es", "que", "en", "un", "una", "del", "al", "como", "con", "por", "para", "mi", "mis", "de", "no", "cual"}
    msg_words = set(user_message.lower().split())
    is_spanish = len(msg_words & spanish_indicators) >= 2 or any(c in user_message for c in ["¿", "á", "é", "í", "ó", "ú", "ñ"])
    lang = "ES" if is_spanish else "EN"

    session_id = request.headers.get("X-Session-Id", "default_session")

    # Persist user message in chat history
    try:
        from runtime.projects.manager import ProjectManager
        pm = ProjectManager()
        pm.add_chat_message(db, session_id, role="user", content=user_message)
    except Exception as e:
        logger.error(f"Failed to save user message to history: {e}")

    
    # ── Stateless Pending Skill Interception (Phase 4.1.4) ─────────
    from runtime.coordinator.state_store import get_pending_skill_store
    pending_store = get_pending_skill_store()
    pending_capability = pending_store.get_pending(session_id)
    
    if pending_capability:
        clean_msg = user_message.strip().lower()
        
        # Check language
        spanish_indicators = {"el", "la", "los", "las", "es", "que", "en", "un", "una", "del", "al", "como", "con", "por", "para", "mi", "mis", "de", "no", "cual"}
        msg_words = set(clean_msg.split())
        is_spanish = len(msg_words & spanish_indicators) >= 1 or any(c in clean_msg for c in ["¿", "á", "é", "í", "ó", "ú", "ñ", "si", "sí"])
        
        is_yes = clean_msg in ("si", "sí", "yes", "y", "claro", "aceptar", "ok", "confirmar")
        is_no = clean_msg in ("no", "cancelar", "cancel", "reject", "n", "denegar")
        
        if is_yes:
            pending_store.clear_pending(session_id)
            if is_spanish:
                response_text = f"🛠️ Funcionalidad en construcción (creación de skill para '{pending_capability}')."
            else:
                response_text = f"🛠️ Feature under construction (skill creation for '{pending_capability}')."
        elif is_no:
            pending_store.clear_pending(session_id)
            if is_spanish:
                response_text = "Operación cancelada."
            else:
                response_text = "Operation canceled."
        else:
            if is_spanish:
                response_text = f"No he entendido tu respuesta. ¿Deseas crear una nueva habilidad (skill) para '{pending_capability}'? (Sí/No)"
            else:
                response_text = f"I didn't understand your response. Would you like to create a new skill for '{pending_capability}'? (Yes/No)"
                
        if body.stream:
            from providers.base import InferenceResult
            async def stream_pending_msg():
                yield InferenceResult(text=response_text, model_id=body.model)
                yield InferenceResult(text="", finish_reason="stop", model_id=body.model)
                
            return StreamingResponse(
                stream_inference_results(stream_pending_msg(), body.model, request_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Request-ID": request_id,
                },
            )
        else:
            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
                model=body.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=response_text),
                        finish_reason="stop",
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0
                )
            )

    skill_id = request.headers.get("X-Skill")
    skill_service = getattr(request.app.state, "skill_service", None)


    # ── Root Prompt Resolution via Prompt Family ──────────────────
    from runtime.coordinator.prompts import resolve_root_prompt
    prompt_family = None
    if skill_id and skill_service:
        manifest = skill_service.get_skill_manifest(skill_id)
        if manifest:
            prompt_family = manifest.prompt_family

    if model_id == "code" or skill_id == "programming":
        prompt_family = "SOFTWARE_PROMPT"

    root_prompt = resolve_root_prompt(lang, prompt_family)

    # Inject language anchor at POSITION 0
    system_prompt = f"[LANG={lang}]\n{root_prompt}"

    # ── Runtime Contract (Subfase 1A / Continuity) ──────────────
    import time
    from runtime.coordinator.models import RuntimeContract
    from runtime.coordinator.state_store import LightweightStateStore
    
    state_store = LightweightStateStore(db)
    snapshot = state_store.load_session_state(session_id)
    snapshot.turn_number += 1
    
    # Resolve previous user message from multi-turn history
    previous_user_message = None
    if len(body.messages) >= 3:
        user_msgs = [msg.content for msg in body.messages if msg.role == "user"]
        if len(user_msgs) >= 2:
            # The last element is user_message, so the second to last is user_msgs[-2]
            previous_user_message = user_msgs[-2]
            
    contract = RuntimeContract(
        request_id=request_id,
        session_id=session_id,
        model_id=model_id,
        user_message=user_message,
        previous_user_message=previous_user_message,
        manual_skill=skill_id,
        timestamp=time.time(),
        profile=body.profile,
        snapshot=snapshot,
        language_confidence_threshold=2,
        explicit_reset=any(user_message.lower().startswith(cmd) for cmd in ['/reset', '/clear', '/new'])
    )
    logger.info(f"[HARDENING-CONTRACT] Created RuntimeContract: id={contract.request_id} session={contract.session_id} has_prev={previous_user_message is not None} turn={snapshot.turn_number}")

    # ── Pure Context Assembly (Subfase 1C/1D) ──────────────────────
    try:
        from runtime.coordinator.manager import PureCoordinator
        pure_coord = PureCoordinator()
        
        skill_service = getattr(request.app.state, "skill_service", None)
        rag_service = getattr(request.app.state, "rag_service", None)
        memory_service = getattr(request.app.state, "memory", None)
        
        graph_provider = None
        try:
            from runtime.graph.query import GraphQueryEngine
            graph_provider = GraphQueryEngine()
        except Exception as gp_err:
            logger.warning(f"Failed to instantiate GraphQueryEngine (degrading to RAG-only): {gp_err}")
            graph_provider = None

        manifest = pure_coord.assemble(
            db=db,
            contract=contract,
            skill_service=skill_service,
            rag_service=rag_service,
            memory_service=memory_service,
            enable_rag=settings.enable_rag_mode,
            graph_provider=graph_provider,
        )
        system_prompt = manifest.system_prompt_snapshot
        resolved_skill = manifest.active_skill
        logger.info(f"[HARDENING-MANIFEST] PureCoordinator compiled: {manifest.model_dump_json(exclude={'system_prompt_snapshot'})}")
    except Exception as assemble_err:
        logger.error(f"PureCoordinator.assemble failed (degrading): {assemble_err}", exc_info=True)
        # Fallback to a basic prompt if it fails completely
        system_prompt = f"[LANG={lang}]\n{root_prompt}"
        resolved_skill = skill_id
        from runtime.coordinator.models import WorkflowState, ContextManifest
        manifest = ContextManifest(
            contract_id=contract.request_id,
            active_skill=resolved_skill,
            workflow_state=WorkflowState(),
            rag_enabled=False,
            system_prompt_snapshot=system_prompt
        )

    # ── Legacy session-based document injection (backward compat) ─
    legacy_session_id = request.headers.get("X-Document-Session-Id")
    if legacy_session_id and not settings.enable_rag_mode:
        doc_context = get_document_service().get_context(legacy_session_id, max_chars=8000)
        if doc_context and body.messages:
            last = body.messages[-1]
            last.content = f"{doc_context}\n\n---PREGUNTA---\n{last.content}"
            logger.info(f"[LEGACY-INJECT] session_id={legacy_session_id!r} | chars={len(doc_context)}")

    # ── Prompt Assembly Debug Log ────────────────────────────────
    logger.info(
        f"[PROMPT-ASSEMBLY] model={model_id} | "
        f"system_prompt_chars={len(system_prompt)} | "
        f"rag_enabled={manifest.rag_enabled if manifest else False} | "
        f"memory_vars={manifest.memory_variables_count if manifest else 0}"
    )

    # Semantic parameter presets (Backend Parameter Ownership)
    PRESETS = {
        "PRECISE": {"temperature": 0.1, "top_k": 10, "top_p": 0.9, "max_tokens": 4096},
        "BALANCED": {"temperature": 0.5, "top_k": 40, "top_p": 0.95, "max_tokens": 4096},
        "CREATIVE": {"temperature": 0.8, "top_k": 50, "top_p": 1.0, "max_tokens": 5120},
    }

    from runtime.coordinator.profiles import PROFILE_TO_PRESET

    # 1. Base resolution: derive default preset deterministically from Cognitive Profile
    resolved_profile = (
        getattr(manifest, "resolved_profile", None)
        or getattr(contract, "profile", None)
        or "BALANCED"
    )
    default_preset = PROFILE_TO_PRESET.get(resolved_profile, "BALANCED")

    # 2. Check for explicit Advanced / API override
    header_preset = request.headers.get("X-Runtime-Preset")
    body_preset = getattr(body, "preset", None)
    explicit_preset = header_preset or body_preset

    if explicit_preset in PRESETS and explicit_preset not in ("FROM_PROFILE", "AUTO", None):
        preset_name = explicit_preset
        logger.info(
            f"[RUNTIME-PRESET] override={preset_name} explicitly set (profile={resolved_profile})"
        )
    else:
        preset_name = default_preset
        logger.info(
            f"[RUNTIME-PRESET] resolved={preset_name} from profile={resolved_profile}"
        )

    preset = PRESETS[preset_name]
    logger.info(
        f"[SKILL-TRACE] runtime_preset_resolver: "
        f"skill={resolved_skill}, model={model_id} "
        f"-> profile={resolved_profile} "
        f"-> preset_name={preset_name}"
    )

    # Apply preset parameters
    temp = preset["temperature"]
    max_tokens = preset["max_tokens"]
    top_k = preset["top_k"]
    top_p = preset["top_p"]

    # Build the inference request (provider-agnostic)
    inference_request = InferenceRequest(
        prompt=body.build_prompt(),
        model_id=model_id,
        temperature=temp,
        max_tokens=max_tokens,
        top_p=top_p,
        top_k=top_k,
        stop_sequences=body.stop or [],
        stream=body.stream,
        system_prompt=system_prompt,
        request_id=request_id,
    )

    from runtime.coordinator.agent import AgentControlRunner
    agent_runner = AgentControlRunner(engine)
    capability_gate_open = manifest.capability_gate_open if manifest else False

    if body.stream:
        # Streaming response (SSE) via AgentControlRunner
        result_stream = agent_runner.run_inference_loop_stream(
            db=db,
            body=body,
            inference_request=inference_request,
            app_state=request.app,
            session_id=session_id,
            capability_gate_open=capability_gate_open,
        )

        # Apply state mutations post-inference dispatch (Subfase 1D)
        if manifest:
            try:
                from runtime.coordinator.mutator import RuntimeStateMutator
                RuntimeStateMutator.apply_state_mutations(db, contract, manifest)
            except Exception as mut_err:
                logger.warning(f"Failed to apply state mutations in streaming flow: {mut_err}")

        return StreamingResponse(
            stream_inference_results(result_stream, model_id, request_id, session_id, db),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": request_id,
            },
        )
    else:
        # Non-streaming response via AgentControlRunner
        start = time.perf_counter()
        agent_response = await agent_runner.run_inference_loop(
            db=db,
            body=body,
            inference_request=inference_request,
            app_state=request.app,
            session_id=session_id,
            capability_gate_open=capability_gate_open,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Apply state mutations post-inference dispatch (Subfase 1D)
        if manifest:
            try:
                from runtime.coordinator.mutator import RuntimeStateMutator
                RuntimeStateMutator.apply_state_mutations(db, contract, manifest)
            except Exception as mut_err:
                logger.warning(f"Failed to apply state mutations in non-streaming flow: {mut_err}")

        # Persist assistant response in chat history
        if agent_response and agent_response.choices:
            assistant_content = agent_response.choices[0].message.content
            try:
                from runtime.projects.manager import ProjectManager
                pm = ProjectManager()
                pm.add_chat_message(db, session_id, role="assistant", content=assistant_content)
                
                # Autotitle checking
                chat = pm.get_chat_by_session(db, session_id)
                if chat and (chat.title == "Nuevo Chat" or chat.title.startswith("Chat ")):
                    msgs = pm.list_chat_messages(db, session_id)
                    user_msgs = [m for m in msgs if m.role == "user"]
                    if user_msgs:
                        first_user_msg = user_msgs[0].content
                        from api.streaming import generate_auto_title
                        new_title = generate_auto_title(first_user_msg)
                        if new_title and new_title != "Nuevo Chat":
                            pm.rename_chat(db, session_id, new_title)
                            logger.info(f"[AUTOTITLE] Auto-titled chat {session_id} to '{new_title}'")
            except Exception as save_err:
                logger.error(f"Failed to save assistant response or autotitle: {save_err}")

        agent_response.latency_ms = elapsed_ms
        return agent_response


# ── GET /v1/models ─────────────────────────────────────────────


@router.get("/models", response_model=ModelListResponse)
async def list_models(request: Request):
    """List available models."""
    engine = getattr(request.app.state, "engine", None)
    if engine:
        models = engine.get_registered_models()
    else:
        settings = getattr(request.app.state, "settings", None) or get_settings()
        models = [{"id": k, "owned_by": "as-code"} for k in getattr(settings, "models", {}).keys()]

    return ModelListResponse(
        data=[
            ModelInfo(
                id=m["id"],
                owned_by=m.get("owned_by", "as-code"),
            )
            for m in models
        ]
    )


# ── GET /v1/status ─────────────────────────────────────────────


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    """Get system status including hardware, models, and provider info."""
    engine = getattr(request.app.state, "engine", None)
    if engine:
        status = await engine.get_status()
    else:
        status = {
            "active_model": None,
            "loaded_models": [],
            "max_vram_mb": 0,
            "estimated_vram_mb": 0,
            "status": "ready",
            "active_provider": "none",
        }
    status["selected_model"] = getattr(request.app.state, "selected_model", None)
    status["active_physical_model"] = status.get("active_physical_model") or getattr(engine, "active_physical_model", None) or status.get("active_model")
    status["active_provider"] = getattr(getattr(engine, "registry", None), "active_provider_id", None) or (getattr(request.app.state, "settings", None).active_provider if getattr(request.app.state, "settings", None) else None)
    return StatusResponse(**status)



# ── POST /v1/models/select ─────────────────────────────────────


class ModelSelectRequest(BaseModel):
    model: Optional[str] = None
    model_id: Optional[str] = None


@router.post("/models/select")
async def select_model(payload: ModelSelectRequest, request: Request):
    """Explicitly select a physical resident model in the control plane."""
    target_model = payload.model or payload.model_id
    if not target_model:
        raise HTTPException(status_code=400, detail="model or model_id is required")

    engine = getattr(request.app.state, "engine", None)
    settings = getattr(request.app.state, "settings", None) or get_settings()

    registered = []
    if engine and hasattr(engine, "get_registered_models"):
        registered = [m["id"] for m in engine.get_registered_models()]
    elif settings and hasattr(settings, "models") and settings.models:
        registered = list(settings.models.keys())
    else:
        registered = ["chat", "code", "reasoning", "olmoe"]

    if target_model not in registered:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{target_model}' is not registered or unavailable",
        )

    if engine and hasattr(engine, "_ensure_model_loaded"):
        try:
            await engine._ensure_model_loaded(target_model)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load model '{target_model}': {e}")

    request.app.state.selected_model = target_model
    return {"status": "ok", "selected_model": target_model}


# ── POST /v1/cancel ────────────────────────────────────────────


@router.post("/cancel")
async def cancel_generation(request: Request, request_id: str = "", model_id: str = ""):
    """Cancel an in-progress generation."""
    if not request_id:
        raise HTTPException(status_code=400, detail="request_id required")

    engine = request.app.state.engine
    # We don't have model_id here usually, but engine.cancel_generation
    # will fall back to active_provider if not provided.
    # Pass model_id to engine so it can route to the correct provider
    await engine.cancel_generation(request_id, model_id)
    return {"status": "cancelled", "request_id": request_id, "model_id": model_id}


# ── GET /v1/providers ──────────────────────────────────────────


@router.get("/providers")
async def list_providers(request: Request):
    """List registered inference providers and their status."""
    engine = request.app.state.engine
    return engine.registry.list_providers()
