"""
AS-Core — Fase 2.2E: Real RAG Baseline Runner (R0 vs R1)
=============================================================================
Orchestrates the frozen 20-case real document benchmark (A-T).
Evaluates exclusively:
  R0 = Core mínimo congelado (Fase 2.1) con RAG OFF.
  R1 = Pipeline RAG actual AS-IS (FAISS + BM25, candidate_pool=250, top_k=5/8, max_chars=6000).

Hardware & Model: Gemma 3n E2B int4 via litert_embedded (WebGPU).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.database import init_db, get_session
from api.document_parser import parse_document
from api.rag_models import RAGDocument, RAGDocumentChunk
from api.project_models import ProjectChat, ProjectDocument
from api.rag_service import build_rag_service, RAGService
from providers.base import InferenceRequest
from api.models import ChatCompletionRequest, ChatMessage
from runtime.coordinator.manager import PureCoordinator
from runtime.coordinator.models import RuntimeContract, SessionSnapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("benchmarks.phase_2_2e")

BENCHMARK_DB_PATH = "data/rag_benchmark_2_2e.db"
BENCHMARK_FAISS_PATH = "data/embeddings/faiss_benchmark_2_2e.index"
RESULTS_OUTPUT_PATH = ROOT / "benchmarks" / "results" / "phase_2_2e_r0_r1_results.json"

# Real Document Roots
DOCS_CONTRATOS = Path(r"D:\Mis documentos\Alpha Software\contratos")
DOCS_PRESUPUESTOS = Path(r"D:\Mis documentos\Alpha Software\presupuestos")
DOCS_LEGADO = Path(r"D:\Mis documentos\Libro RVA El Legado\La Tierra que Quedó.pdf")

# Synthetic documents temp dir
SYNTH_DIR = ROOT / "scratch" / "phase_2_2e_fixtures"


# ── Benchmark Case Definitions (A to T) ─────────────────────────

BENCHMARK_CASES = [
    {
        "id": "CASE_A",
        "name": "Consulta General (RAG OFF Esperado)",
        "prompt": "Explica qué es la memoria RAM en una computadora y cuál es su función principal.",
        "expected_rag": False,
        "min_chunks": 0,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["memoria", "temporal", "acceso aleatorio", "instrucciones", "procesador"],
        "gt_anti_keywords": ["nancy", "sanabria", "alpha software", "alquiler", "mipymes"],
        "eval_type": "non_documental",
    },
    {
        "id": "CASE_B",
        "name": "Pregunta Explícita sobre Contrato",
        "prompt": "¿Cuál es el costo mensual de alquiler y qué penalización se aplica por cancelación anticipada según el contrato de Nancy Sanabria?",
        "expected_rag": True,
        "min_chunks": 2,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["250.000", "30%", "penalización"],
        "eval_type": "factual_multi",
    },
    {
        "id": "CASE_C",
        "name": "Pregunta Explícita sobre Presupuesto",
        "prompt": "¿Cuál es el precio al contado con 30% de descuento ofrecido a Bryan Insfran para el Plan Full de Punto de Venta?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_PRESUPUESTOS / "2026" / "Punto de Venta" / "Bryan Insfran 5 marzo.pdf"],
        "distractors": [],
        "gt_keywords": ["4.550.000", "6.500.000"],
        "eval_type": "factual_single",
    },
    {
        "id": "CASE_D",
        "name": "Dato Exacto en Fragmento Único",
        "prompt": "¿A los cuántos días de mora en el pago queda facultado el programador para suspender el servicio y eliminar la base de datos en el contrato de Nancy Sanabria?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["90 días", "noventa días"],
        "eval_type": "factual_single",
    },
    {
        "id": "CASE_E",
        "name": "Pregunta que Requiere Múltiples Fragmentos",
        "prompt": "¿Qué incluye la propuesta técnica de Coopersam en cuanto a cantidad de boxes y pantallas, y cuál es el precio final abonando al contado?",
        "expected_rag": True,
        "min_chunks": 2,
        "docs": [DOCS_PRESUPUESTOS / "2026" / "Gestion de Turnos" / "Coopersam 10 marzo.pdf"],
        "distractors": [],
        "gt_keywords": ["16 boxes", "3 pantallas", "14.560.000"],
        "eval_type": "factual_multi",
    },
    {
        "id": "CASE_F",
        "name": "Varios Documentos, Solo Uno Relevante",
        "prompt": "¿Cuál es la penalización por cancelación anticipada en el contrato de alquiler de Nancy Sanabria?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [
            DOCS_PRESUPUESTOS / "2026" / "Gestion de Turnos" / "Coopersam 10 marzo.pdf",
            DOCS_PRESUPUESTOS / "2026" / "Punto de Venta" / "Bryan Insfran 5 marzo.pdf",
        ],
        "gt_keywords": ["30%"],
        "gt_anti_keywords": ["coopersam", "turnos", "bryan"],
        "eval_type": "factual_distractors",
    },
    {
        "id": "CASE_G",
        "name": "Dos Versiones con Conflicto de Información",
        "prompt": "¿Qué monto o compensación ofreció Alpha Software en su propuesta conciliatoria inicial frente a la propuesta final en el caso Cristian Banegas?",
        "expected_rag": True,
        "min_chunks": 2,
        "docs": [
            DOCS_CONTRATOS / "2026" / "Cristian Banegas" / "PROPUESTA CONCILIATORIA.docx",
            DOCS_CONTRATOS / "2026" / "Cristian Banegas" / "Propuesta Concilatoria final.pdf",
        ],
        "distractors": [],
        "gt_keywords": ["12 meses", "3.900.000"],
        "eval_type": "version_conflict",
    },
    {
        "id": "CASE_H",
        "name": "Mismo Contenido en DOCX y PDF (Duplicación)",
        "prompt": "¿Cuáles son los planes y precios de Punto de Venta detallados para Victor Morales en julio de 2025?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [
            DOCS_PRESUPUESTOS / "2025" / "Punto de Venta" / "Victor Morales 22 07 25.docx",
            DOCS_PRESUPUESTOS / "2025" / "Punto de Venta" / "Victor Morales 22 07 25.pdf",
        ],
        "distractors": [],
        "gt_keywords": ["6.500.000", "10.000.000"],
        "eval_type": "duplication_check",
    },
    {
        "id": "CASE_I",
        "name": "Pregunta Ambigua sobre Doc Activo",
        "prompt": "¿Qué dice sobre la pérdida de datos y las copias de seguridad?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["responsabilidad exclusiva", "cliente", "copias de seguridad", "elimina"],
        "eval_type": "ambiguous_retrieval",
    },
    {
        "id": "CASE_J",
        "name": "Follow-Up Documental Corto (2 Turnos)",
        "prompt": "¿Y qué pasa si se atrasa en el pago?",
        "turn1_prompt": "¿Cuánto cuesta el alquiler en el contrato de Nancy?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["90 días", "suspender", "elimina"],
        "eval_type": "followup_doc",
    },
    {
        "id": "CASE_K",
        "name": "Follow-Up NO Documental (2 Turnos)",
        "prompt": "Muchas gracias, me quedó muy claro.",
        "turn1_prompt": "¿Cuál es el monto de la propuesta final de Banegas?",
        "expected_rag": False,
        "min_chunks": 0,
        "docs": [DOCS_CONTRATOS / "2026" / "Cristian Banegas" / "Propuesta Concilatoria final.pdf"],
        "distractors": [],
        "gt_keywords": ["orden", "disposición", "placer", "nada", "bienvenido"],
        "gt_anti_keywords": ["3.900.000", "sedeco", "conciliatorio", "banegas"],
        "eval_type": "followup_nondoc",
    },
    {
        "id": "CASE_L",
        "name": "Información Inexistente en Documento",
        "prompt": "¿Cuál es la dirección de correo electrónico personal del Sr. Cristian Banegas según el acta final de conciliación?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Cristian Banegas" / "Propuesta Concilatoria final.pdf"],
        "distractors": [],
        "gt_keywords": ["no figura", "no contiene", "no se menciona", "no aparece", "no especifica"],
        "eval_type": "absence_recognition",
    },
    {
        "id": "CASE_M",
        "name": "El Legado: Hecho en Chunk Único",
        "prompt": "¿Cuántos años transcurrieron desde el primer contacto extraterrestre según el prólogo del libro La Tierra que Quedó?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_LEGADO],
        "distractors": [],
        "gt_keywords": ["25 años", "veinticinco años"],
        "eval_type": "book_single_fact",
    },
    {
        "id": "CASE_N",
        "name": "El Legado: Síntesis Distante (Inicio y Final)",
        "prompt": "Al inicio del libro se detecta una primera explosión y al final se revela el destino de las naves. ¿Quién sintió esa primera vibración y cuántas nodrizas llegaron y cuántas se alejaron al final?",
        "expected_rag": True,
        "min_chunks": 2,
        "docs": [DOCS_LEGADO],
        "distractors": [],
        "gt_keywords": ["kael", "5 nodrizas", "cinco nodrizas", "4 nodrizas", "cuatro nodrizas"],
        "eval_type": "book_distant_synthesis",
    },
    {
        "id": "CASE_O",
        "name": "Consulta General con El Legado Cargado",
        "prompt": "Escribe una receta tradicional para preparar una sopa de verduras sencilla.",
        "expected_rag": False,
        "min_chunks": 0,
        "docs": [DOCS_LEGADO],
        "distractors": [],
        "gt_keywords": ["verduras", "agua", "sal", "olla", "zanahoria"],
        "gt_anti_keywords": ["kael", "marcus", "nodrizas", "elena", "nova", "tierra que quedó"],
        "eval_type": "book_contamination_guard",
    },
    {
        "id": "CASE_P",
        "name": "El Legado: Retrieval en Documento Extenso",
        "prompt": "¿Cómo se describe a Marcus y cuál es su relación con Kael en el programa de instrucción en la Tierra que Quedó?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_LEGADO],
        "distractors": [],
        "gt_keywords": ["instructor", "no impresionarse", "consola", "daren"],
        "eval_type": "book_character_retrieval",
    },
    {
        "id": "CASE_Q",
        "name": "Conflicto Comercial Interanual (Presupuesto)",
        "prompt": "¿Cuál era el costo del soporte mensual en la propuesta de Victor Morales de 2025 frente al costo del alquiler en el contrato de Nancy Sanabria de 2026?",
        "expected_rag": True,
        "min_chunks": 2,
        "docs": [
            DOCS_PRESUPUESTOS / "2025" / "Punto de Venta" / "Victor Morales 09 07 25.docx",
            DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx",
        ],
        "distractors": [],
        "gt_keywords": ["300.000", "250.000"],
        "eval_type": "interanual_comparison",
    },
    {
        "id": "CASE_R",
        "name": "Sintético: Aislamiento Cross-Project (GATE CRÍTICO)",
        "prompt": "Dame el token de acceso secreto de infraestructura del Proyecto Alpha.",
        "expected_rag": True,
        "min_chunks": 0,
        "is_synthetic_isolation": True,
        "eval_type": "isolation_gate",
    },
    {
        "id": "CASE_S",
        "name": "Sintético: Conflicto Controlado de Configuración",
        "prompt": "¿Cuál es el puerto de comunicación del servicio de mensajería según la configuración oficial?",
        "expected_rag": True,
        "min_chunks": 2,
        "is_synthetic_conflict": True,
        "gt_keywords": ["9090", "oficial"],
        "eval_type": "synthetic_conflict",
    },
    {
        "id": "CASE_T",
        "name": "Límite de Alcance en Licencia Comercial",
        "prompt": "¿A cuántas sucursales, cajas y depósitos limita el uso del sistema el contrato de Nancy Sanabria, y qué restricción impone sobre la cantidad de computadoras o usuarios?",
        "expected_rag": True,
        "min_chunks": 1,
        "docs": [DOCS_CONTRATOS / "2026" / "Nancy Sanabria" / "Contrato Alquiler Sistema.docx"],
        "distractors": [],
        "gt_keywords": ["1 sucursal", "1 caja", "1 depósito", "sin restricción"],
        "eval_type": "scope_limits",
    },
]


# ── Synthetic Fixtures Creation ─────────────────────────────────

def create_synthetic_fixtures() -> Tuple[Path, Path, Path, Path]:
    SYNTH_DIR.mkdir(parents=True, exist_ok=True)
    alpha_secret = SYNTH_DIR / "alpha_secret.txt"
    beta_readme = SYNTH_DIR / "beta_readme.txt"
    config_v1 = SYNTH_DIR / "config_v1.txt"
    config_v2 = SYNTH_DIR / "config_v2.txt"

    alpha_secret.write_text("PROJECT_ALPHA_SECRET_TOKEN=ALPHA_KEY_SEC_99428_XYZ\nClave ultra confidencial de Proyecto Alpha.", encoding="utf-8")
    beta_readme.write_text("Proyecto Beta: Sistema de inventario público y abierto. Sin credenciales ni claves confidenciales.", encoding="utf-8")
    config_v1.write_text("service_port: 8080\nstatus: deprecated\ndescription: Puerto antiguo del servicio de mensajeria.", encoding="utf-8")
    config_v2.write_text("service_port: 9090\nstatus: active_official\ndescription: Puerto activo oficial del servicio de mensajeria.", encoding="utf-8")

    return alpha_secret, beta_readme, config_v1, config_v2


# ── Corpus Ingestion Helper ────────────────────────────────────

def setup_benchmark_corpus(rag_service: RAGService, db) -> Dict[str, List[str]]:
    """
    Ingests the needed documents into the isolated benchmark SQLite & FAISS.
    Maps session IDs to document IDs for scope isolation.
    """
    session_docs_map: Dict[str, List[str]] = {}

    alpha_secret, beta_readme, config_v1, config_v2 = create_synthetic_fixtures()

    # Track already ingested files to avoid re-embedding
    ingested_files_cache: Dict[str, RAGDocument] = {}

    def get_or_ingest_doc(file_path: Path, session_id: Optional[str] = None) -> RAGDocument:
        cache_key = str(file_path.resolve())
        parsed = parse_document(str(file_path))
        doc = RAGDocument(
            id=str(uuid.uuid4()),
            filename=parsed.filename,
            file_type=parsed.file_type,
            content=parsed.text,
            source="local",
            pipeline="chat",
            session_id=session_id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        rag_service.process_document(doc, db)
        return doc

    print("\n[INGESTION] Setting up Benchmark Corpus in isolated DB/FAISS...")

    for case in BENCHMARK_CASES:
        cid = case["id"]
        case_session_id = f"sess_{cid}"
        session_docs_map[case_session_id] = []

        if case.get("is_synthetic_isolation"):
            # Project Alpha gets secret
            doc_alpha = get_or_ingest_doc(alpha_secret, session_id="sess_proj_alpha")
            p_alpha = ProjectChat(project_id="proj_alpha", session_id="sess_proj_alpha")
            pd_alpha = ProjectDocument(project_id="proj_alpha", document_id=doc_alpha.id)
            db.add(p_alpha)
            db.add(pd_alpha)

            # Project Beta gets readme
            doc_beta = get_or_ingest_doc(beta_readme, session_id=case_session_id)
            p_beta = ProjectChat(project_id="proj_beta", session_id=case_session_id)
            pd_beta = ProjectDocument(project_id="proj_beta", document_id=doc_beta.id)
            db.add(p_beta)
            db.add(pd_beta)
            db.commit()
            session_docs_map[case_session_id].append(doc_beta.id)
            continue

        if case.get("is_synthetic_conflict"):
            d1 = get_or_ingest_doc(config_v1, session_id=case_session_id)
            d2 = get_or_ingest_doc(config_v2, session_id=case_session_id)
            session_docs_map[case_session_id].extend([d1.id, d2.id])
            continue

        # Real documents
        all_case_docs = list(case.get("docs", [])) + list(case.get("distractors", []))
        for doc_path in all_case_docs:
            if not doc_path.exists():
                logger.error(f"Missing required real document: {doc_path}")
                continue
            doc_obj = get_or_ingest_doc(doc_path, session_id=case_session_id)
            session_docs_map[case_session_id].append(doc_obj.id)
            print(f"  Ingested for {cid}: {doc_obj.filename} (ID={doc_obj.id[:8]})")

    print(f"[INGESTION COMPLETE] Total vectors in FAISS: {rag_service.chat.vector_store.total}\n")
    return session_docs_map


# ── Response Evaluator ──────────────────────────────────────────

def evaluate_case_response(case: Dict[str, Any], answer: str, rag_context: str) -> Dict[str, Any]:
    clean_ans = answer.lower()
    gt_kw = [k.lower() for k in case.get("gt_keywords", [])]
    anti_kw = [k.lower() for k in case.get("gt_anti_keywords", [])]

    # Check isolation leak
    if case.get("is_synthetic_isolation"):
        leaked = "alpha_key_sec_99428_xyz" in clean_ans or "alpha_key" in clean_ans
        if leaked:
            return {"score": 0.0, "status": "FAIL", "reason": "ISOLATION_LEAK_DETECTED"}
        return {"score": 100.0, "status": "PASS", "reason": "ISOLATION_PRESERVED"}

    # Anti-keywords presence (contamination check)
    contamination_present = any(ak in clean_ans for ak in anti_kw)
    if anti_kw and contamination_present:
        return {"score": 25.0, "status": "FAIL", "reason": "CONTAMINATION_DETECTED"}

    # Keyword match count
    matches = sum(1 for kw in gt_kw if kw in clean_ans)
    total_kw = len(gt_kw)

    if total_kw == 0:
        # For non-documental (A, K, O), pass if no contamination
        status = "PASS" if not contamination_present else "FAIL"
        score = 100.0 if not contamination_present else 25.0
        return {"score": score, "status": status, "reason": "CLEAN_NON_DOC"}

    match_ratio = matches / total_kw

    if match_ratio >= 0.8:
        status = "PASS"
        score = 100.0
    elif match_ratio >= 0.4:
        status = "PARTIAL"
        score = 50.0
    else:
        status = "FAIL"
        score = 0.0

    return {
        "score": score,
        "status": status,
        "matches": matches,
        "total_keywords": total_kw,
        "match_ratio": match_ratio,
        "contamination": contamination_present,
    }


# ── Main Runner ────────────────────────────────────────────────

async def run_phase_2_2e_benchmark():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 80)
    print("AS-CORE — FASE 2.2E: REAL RAG BASELINE BENCHMARK (R0 vs R1)")
    print("MODEL: Gemma 3n E2B (chat) int4 | PROVIDER: litert_embedded (WebGPU)")
    print("BENCHMARK: 20 Real & Controlled Frozen Cases (A - T)")
    print("=" * 80)

    from api.main import app, lifespan

    init_db(BENCHMARK_DB_PATH)
    db = get_session()

    # Build production RAG Service on benchmark storage
    rag_service = build_rag_service(
        faiss_index_path=BENCHMARK_FAISS_PATH,
        embedding_dim=384,
        embedder_model="BAAI/bge-small-en-v1.5",
        chunk_size=300,
        chunk_overlap=50,
        retrieval_mode="hybrid",
        hybrid_alpha=0.7,
    )

    # Ingest corpus only if not already populated
    if rag_service.chat.vector_store.total == 0:
        session_docs_map = setup_benchmark_corpus(rag_service, db)
    else:
        print(f"\n[INGESTION CACHE HIT] Reusing {rag_service.chat.vector_store.total} vectors from {BENCHMARK_FAISS_PATH}\n")

    coordinator = PureCoordinator()

    runner = lifespan(app)
    await runner.__aenter__()
    engine = app.state.engine

    r0_results: List[Dict[str, Any]] = []
    r1_results: List[Dict[str, Any]] = []

    print("\n" + "=" * 80)
    print(">>> EXECUTING R0: CORE CONGELADO CON RAG COMPLETAMENTE OFF")
    print("=" * 80)

    for case in BENCHMARK_CASES:
        cid = case["id"]
        cname = case["name"]
        prompt = case["prompt"]
        session_id = f"sess_{cid}"

        # Handle 2-turn cases (J and K)
        history = []
        if "turn1_prompt" in case:
            t1_prompt = case["turn1_prompt"]
            history.append(ChatMessage(role="user", content=t1_prompt))
            # Minimal simulated answer for turn 1 to set context
            history.append(ChatMessage(role="assistant", content="Entendido."))

        messages = history + [ChatMessage(role="user", content=prompt)]

        contract = RuntimeContract(
            request_id=f"r0_{cid}",
            session_id=session_id,
            user_message=prompt,
            model_id="chat",
            profile="AUTO",
            timestamp=time.time(),
            snapshot=SessionSnapshot(session_id=session_id, turn_number=len(history) + 1),
        )

        manifest = coordinator.assemble(
            db=db,
            contract=contract,
            skill_service=None,
            rag_service=None,
            memory_service=None,
            enable_rag=False,
            graph_provider=None,
        )

        t_start = time.perf_counter()
        req = ChatCompletionRequest(
            model="chat",
            messages=messages,
            temperature=0.5,
            max_tokens=512,
            stream=False,
        )

        inf_req = InferenceRequest(
            prompt=req.build_prompt(),
            model_id="chat",
            temperature=0.5,
            max_tokens=512,
            top_p=0.95,
            top_k=40,
            stream=False,
            system_prompt=manifest.system_prompt_snapshot,
            request_id=contract.request_id,
        )
        res = await engine.generate(inf_req)
        total_time = time.perf_counter() - t_start
        answer = res.text or ""
        tokens_gen = res.tokens_generated
        context_chars = len(manifest.system_prompt_snapshot)

        eval_res = evaluate_case_response(case, answer, "")

        res_entry = {
            "case_id": cid,
            "name": cname,
            "rag_enabled": False,
            "answer": answer,
            "status": eval_res["status"],
            "score": eval_res["score"],
            "eval_detail": eval_res,
            "latency_s": round(total_time, 3),
            "output_tokens": tokens_gen,
            "context_chars": context_chars,
            "context_tokens": context_chars // 4,
            "rag_context_len": 0,
            "retrieved_chunks_count": 0,
        }
        r0_results.append(res_entry)
        print(f"[{cid}] R0 -> Status: {eval_res['status']} ({eval_res['score']:.1f}%) | Time: {total_time:.2f}s | OutTok: {tokens_gen}")

    print("\n" + "=" * 80)
    print(">>> EXECUTING R1: PIPELINE RAG ACTUAL AS-IS (FAISS + BM25, TOP_K=5/8)")
    print("=" * 80)

    for case in BENCHMARK_CASES:
        cid = case["id"]
        cname = case["name"]
        prompt = case["prompt"]
        session_id = f"sess_{cid}"

        history = []
        if "turn1_prompt" in case:
            t1_prompt = case["turn1_prompt"]
            history.append(ChatMessage(role="user", content=t1_prompt))
            history.append(ChatMessage(role="assistant", content="Entendido."))

        messages = history + [ChatMessage(role="user", content=prompt)]

        contract = RuntimeContract(
            request_id=f"r1_{cid}",
            session_id=session_id,
            user_message=prompt,
            model_id="chat",
            profile="AUTO",
            timestamp=time.time(),
            snapshot=SessionSnapshot(session_id=session_id, turn_number=len(history) + 1),
        )

        t_ret_start = time.perf_counter()
        manifest = coordinator.assemble(
            db=db,
            contract=contract,
            skill_service=None,
            rag_service=rag_service,
            memory_service=None,
            enable_rag=True,
            graph_provider=None,
        )
        retrieval_time_ms = (time.perf_counter() - t_ret_start) * 1000

        # Extract RAG telemetry directly from DB/service for this session query
        retrieved_raw = rag_service.retrieve(prompt, db, top_k=5, session_id=session_id)
        chunks_retrieved_count = len(retrieved_raw)
        rag_context = rag_service.build_context(prompt, db, session_id=session_id)

        t_start = time.perf_counter()
        req = ChatCompletionRequest(
            model="chat",
            messages=messages,
            temperature=0.5,
            max_tokens=512,
            stream=False,
        )

        inf_req = InferenceRequest(
            prompt=req.build_prompt(),
            model_id="chat",
            temperature=0.5,
            max_tokens=512,
            top_p=0.95,
            top_k=40,
            stream=False,
            system_prompt=manifest.system_prompt_snapshot,
            request_id=contract.request_id,
        )
        res = await engine.generate(inf_req)
        total_time = time.perf_counter() - t_start
        answer = res.text or ""
        tokens_gen = res.tokens_generated
        context_chars = len(manifest.system_prompt_snapshot)

        eval_res = evaluate_case_response(case, answer, rag_context)

        # Inspect retrieved chunks quality (noise ratio)
        gt_kw = [k.lower() for k in case.get("gt_keywords", [])]
        relevant_chunks = 0
        for rc in retrieved_raw:
            txt = rc.text.lower()
            if any(k in txt for k in gt_kw):
                relevant_chunks += 1
        irrelevant_chunks = chunks_retrieved_count - relevant_chunks

        res_entry = {
            "case_id": cid,
            "name": cname,
            "rag_enabled": True,
            "rag_actually_injected": len(rag_context) > 0,
            "answer": answer,
            "status": eval_res["status"],
            "score": eval_res["score"],
            "eval_detail": eval_res,
            "latency_s": round(total_time, 3),
            "retrieval_latency_ms": round(retrieval_time_ms, 2),
            "output_tokens": tokens_gen,
            "context_chars": context_chars,
            "context_tokens": context_chars // 4,
            "rag_context_len": len(rag_context),
            "retrieved_chunks_count": chunks_retrieved_count,
            "relevant_chunks": relevant_chunks,
            "irrelevant_chunks": irrelevant_chunks,
            "retrieved_top_docs": [rc.document_filename for rc in retrieved_raw[:3]],
            "retrieved_scores": [round(rc.score, 4) for rc in retrieved_raw[:3]],
        }
        r1_results.append(res_entry)
        print(f"[{cid}] R1 -> Status: {eval_res['status']} ({eval_res['score']:.1f}%) | Time: {total_time:.2f}s | Chunks: {chunks_retrieved_count} (rel={relevant_chunks}) | RAG Chars: {len(rag_context)}")

    # ── Summary Metrics Computation ────────────────────────────────

    q0 = sum(r["score"] for r in r0_results) / len(r0_results)
    q1 = sum(r["score"] for r in r1_results) / len(r1_results)
    delta_quality = q1 - q0

    doc_cases_indices = [i for i, c in enumerate(BENCHMARK_CASES) if c["expected_rag"]]
    non_doc_cases_indices = [i for i, c in enumerate(BENCHMARK_CASES) if not c["expected_rag"]]

    q0_doc = sum(r0_results[i]["score"] for i in doc_cases_indices) / len(doc_cases_indices)
    q1_doc = sum(r1_results[i]["score"] for i in doc_cases_indices) / len(doc_cases_indices)
    doc_delta = q1_doc - q0_doc

    q0_nondoc = sum(r0_results[i]["score"] for i in non_doc_cases_indices) / len(non_doc_cases_indices)
    q1_nondoc = sum(r1_results[i]["score"] for i in non_doc_cases_indices) / len(non_doc_cases_indices)
    nondoc_delta = q1_nondoc - q0_nondoc

    avg_lat0 = sum(r["latency_s"] for r in r0_results) / len(r0_results)
    avg_lat1 = sum(r["latency_s"] for r in r1_results) / len(r1_results)

    avg_tok0 = sum(r["context_tokens"] for r in r0_results) / len(r0_results)
    avg_tok1 = sum(r["context_tokens"] for r in r1_results) / len(r1_results)

    total_chunks = sum(r["retrieved_chunks_count"] for r in r1_results)
    total_irrelevant = sum(r["irrelevant_chunks"] for r in r1_results)
    noise_ratio = (total_irrelevant / total_chunks) if total_chunks > 0 else 0.0

    false_rag_on = sum(1 for i in non_doc_cases_indices if r1_results[i]["rag_actually_injected"])
    false_rag_off = sum(1 for i in doc_cases_indices if not r1_results[i]["rag_actually_injected"])

    isolation_case = next(r for r in r1_results if r["case_id"] == "CASE_R")
    isolation_preserved = isolation_case["status"] == "PASS"

    summary = {
        "quality_r0": round(q0, 2),
        "quality_r1": round(q1, 2),
        "rag_value_delta": round(delta_quality, 2),
        "documental_value_delta": round(doc_delta, 2),
        "non_documental_damage": round(nondoc_delta, 2),
        "avg_latency_r0_s": round(avg_lat0, 2),
        "avg_latency_r1_s": round(avg_lat1, 2),
        "avg_context_tokens_r0": round(avg_tok0, 1),
        "avg_context_tokens_r1": round(avg_tok1, 1),
        "noise_ratio_pct": round(noise_ratio * 100, 1),
        "false_rag_on_count": false_rag_on,
        "false_rag_off_count": false_rag_off,
        "isolation_preserved": isolation_preserved,
    }

    final_payload = {
        "summary": summary,
        "r0_results": r0_results,
        "r1_results": r1_results,
    }

    RESULTS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_OUTPUT_PATH, "w", encoding="utf-8") as fp:
        json.dump(final_payload, fp, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETED SUCCESSFULLY!")
    print(f"Results saved to: {RESULTS_OUTPUT_PATH}")
    print(f"Quality R0: {summary['quality_r0']} | Quality R1: {summary['quality_r1']} | Delta: {summary['rag_value_delta']:+0.2f}")
    print(f"Documental Value Delta: {summary['documental_value_delta']:+0.2f} | Non-Doc Damage: {summary['non_documental_damage']:+0.2f}")
    print(f"Noise Ratio: {summary['noise_ratio_pct']}% | False RAG ON: {summary['false_rag_on_count']}/3")
    print(f"Isolation Preserved (Case R): {summary['isolation_preserved']}")
    print("=" * 80)

    db.close()
    await runner.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(run_phase_2_2e_benchmark())
