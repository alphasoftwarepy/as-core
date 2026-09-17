# AS-CORE — FASE 2: COGNITIVE CORE VALUE, ABLATION & CONTEXT EFFICIENCY PROGRAM
## Tracking de Progreso y Estado de Fases

---

### PHASE 2.0 — PURE LLM BASELINE (B0)
- **STATUS**: COMPLETE
- **START**: 2026-09-17 09:03:21
- **END**: 2026-09-17 09:07:42
- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider)
- **CASES**: 24
- **COMPONENTS ENABLED**: Modelo residente puro (camino mínimo, Profile AUTO / BALANCED)
- **COMPONENTS DISABLED**: RAG, Graph, Memory, Documents, Skills, Tools, Web
- **PASS**: 9
- **PARTIAL**: 13
- **FAIL**: 2
- **SCORE**: 83.7/100
- **KEY FINDING**: B0 Baseline establecido con éxito. Modelo demuestra competencia básica en tareas lingüísticas y estructuración simple, pero sufre alucinación en conocimiento factual específico (Paraguay/trampas) y errores de lógica inversa.
- **NEXT**: WAITING HUMAN REVIEW (CHECKPOINT 2.0)

---

### PHASE 2.1 — MINIMAL COGNITIVE CORE
- **STATUS**: COMPLETE
- **START**: 2026-09-17 09:29:26
- **END**: 2026-09-17 09:31:08
- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider)
- **CASES**: 24
- **B0 SCORE**: 83.7/100
- **B1 SCORE**: 84.0/100
- **CORE VALUE DELTA**: +0.3 pts
- **IMPROVED / UNCHANGED / DEGRADED**: 1 / 23 / 0
- **AVG CONTEXT ADDED**: ~148 tokens
- **AVG LATENCY B0 -> B1**: 9.4s -> 11.18s
- **KEY FINDING**: Minimal Cognitive Core produce impacto diferenciado por perfil: estabilización y menor varianza sintáctica en CODE (PRECISE temp 0.1), neutralidad en tareas factuales y dispersión en CREATIVE (temp 0.8).
- **NEXT**: COMPLETE (Auditoría Forense en Fase 2.1R)

---

### PHASE 2.1R — COGNITIVE CORE REDUCTION AUDIT
- **STATUS**: COMPLETE (WAITING FOR HUMAN REVIEW)
- **DATE**: 2026-09-17
- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider)
- **REDUCTION SET CASES**: 11
- **B0 SCORE**: 83.7/100 (Reduction Set: 82.6/100)
- **B1 SCORE**: 83.3/100 auditado corregido (Reduction Set: 81.8/100)
- **BEST REDUCED SCORE**: 83.7/100 (V2) / 83.3/100 (V3)
- **CONTEXT REDUCTION**: -56.8% tokens inyectados (de ~148 a ~64 tokens)
- **LATENCY CHANGE**: -19.1% tiempo de respuesta (de 11.03s a 8.92s en Reduction Set)
- **COMPONENTS KEEP**: `resolve_cognitive_profile`, `PROFILE_TO_PRESET`, `PureCoordinator.assemble`
- **COMPONENTS SIMPLIFY**: `GENERAL_PROMPT`, `SOFTWARE_PROMPT`
- **COMPONENTS REMOVE CANDIDATE**: Language Anchor (`[LANG=ES]`), `analyze_intent` (heurísticas de keywords en chat estándar)
- **COMPONENTS KEEP ON-DEMAND**: `build_runtime_context_block` (inyección de estado/contexto solo cuando existan herramientas o habilidades reales activas)
- **BIZ-05 PRECHECK**: Degradación confirmada por falso positivo en `analyze_intent` ("desarrollo" -> programming). Corregido scoring del evaluador a 62.5%. En V3 (sin contexto espurio) el caso recuperó su comportamiento óptimo (correo formal en 15.1s).
- **DOC**: `docs/PHASE_2_1R_COGNITIVE_CORE_REDUCTION_AUDIT.md`
- **RESULTS ARTIFACT**: `benchmarks/results/phase_2_1r_reduction_results.json`
- **NEXT**: COMPLETE (Implementación Quirúrgica en Fase 2.1S)

---

### PHASE 2.1S — SURGICAL CORE SIMPLIFICATION
- **STATUS**: COMPLETE (CHECKPOINT FASE 2.1S)
- **DATE**: 2026-09-17
- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider)
- **HOT PATH**: API real `/v1/chat/completions` con `PureCoordinator` desacoplado
- **SURGICAL CHANGE**: Retirada la autoridad ejecutiva de `first_inferred` para definir `resolved_skill` en `PureCoordinator.assemble` (`manager.py`).
- **CONTRACT TESTS**: 15/15 PASSED (S1-S5 convertidos de RED a GREEN; S6-S15 invariantes GREEN)
- **REGRESSIONS**: 63/63 PASSED (SRMP, UI presets, Skills, Capability Gate, Workflow, RAG, Graph) + 9/9 PASSED (Residency & Transitions)
- **REDUCTION SET BENCHMARK (N=11)**:
  - **B0 Baseline**: 82.6 pts | 8.22s | 0 ctx tokens
  - **B1 Auditado**: 81.8 pts | 11.03s | 147.3 ctx tokens
  - **B1R (Mejor Variante V2/V3)**: 83.7 pts | 8.92s | 64.0 ctx tokens
  - **B1S (Producción Implementada)**: **83.3 pts | 9.35s | 64.0 ctx tokens**
- **BIZ-05 AUDIT VERIFICATION**: Correo formal breve generado (289 tokens en 15.02s con score 79.2). **Cero código Python. Cero bloques espurios.**
- **PHYSICAL MODEL RESIDENCY**: 100% verificado (exactamente 1 modelo físico `gemma-3n-E2B-it-int4`, cero swaps).
- **FILES MODIFIED**: Exclusivamente `runtime/coordinator/manager.py` (cero modificaciones en otros archivos de producción).
- **RESULTS ARTIFACT**: `benchmarks/results/phase_2_1s_reduction_results.json`
- **NEXT**: COMPLETE (Micro-Ablación e Implementación Quirúrgica en Fase 2.1T)

---

### PHASE 2.1T — LANGUAGE ANCHOR SURGICAL REMOVAL
- **STATUS**: COMPLETE (CHECKPOINT FASE 2.1T)
- **DATE**: 2026-09-17
- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider on GPU WebGPU)
- **HOT PATH**: Producción real `/v1/chat/completions` (streaming y no-streaming) y `PureCoordinator.assemble`
- **SURGICAL CHANGE**: Retirado el prefijo `[LANG={lang}]\n` en `runtime/coordinator/manager.py` (ensamblado orquestado) y `api/routes.py` (chat normal y fallback de streaming).
- **CONTRACT TESTS**: 5/5 PASSED (`tests/test_phase_2_1t_language_anchor.py`)
- **REGRESSIONS**: 120/120 PASSED (2.1S simplification, 2.1T anchor, Graph contracts, Deterministic continuity, Model residency, Skill factory, UIX profiles/presets)
- **REDUCTION SET BENCHMARK (N=11)**:
  - **Quality Score**: 83.71 pts (vs 83.33 en 2.1S, +0.38 pts)
  - **Avg Latency**: 8.67s (vs 9.35s en 2.1S, -7.3% speedup)
  - **Context Tokens**: 63.0 tok (vs 64.0 en 2.1S, -1.0 tok neto)
  - **Output Tokens**: 150.1 tok (vs 165.5 en 2.1S, -15.4 tok de verbosidad espuria)
  - **Language Drift**: 0/11 (0% deriva lingüística, español nativo 100%)
  - **Tag Leakage (`[LANG=ES]`)**: **0/11 (de 3 casos con eco parásito a 0, -100%)**
  - **Streaming Verification**: PASS (SSE streaming en español sin leaks de tags ni drift)
  - **Physical Model Residency**: 100% verificado (`gemma-3n-E2B-it-int4`, cero swaps).
- **FILES MODIFIED**: `runtime/coordinator/manager.py`, `api/routes.py`
- **RESULTS ARTIFACT**: `benchmarks/results/phase_2_1t_final_validation_results.json`
- **NEXT**: WAITING FOR HUMAN REVIEW (CHECKPOINT FASE 2.1T)

---

### PHASE 2.2 — RAG VALUE TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Medir valor exclusivo de RAG frente a baseline puro y core mínimo.

---

### PHASE 2.3 — GRAPH VALUE TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Medir valor de relaciones relacionales/multihop vs costo de contexto.

---

### PHASE 2.4 — MEMORY / CONTINUITY VALUE TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Determinar retención de contexto vs polución de memoria.

---

### PHASE 2.5 — SKILLS VALUE TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Determinar si Skills agregan capacidades reales o solo sobrecarga de prompt.

---

### PHASE 2.6 — TOOLS VALUE TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Evaluar capacidades deterministas externas y mitigación de invenciones.

---

### PHASE 2.7 — SELECTIVE ACTIVATION
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Evaluar precisión de activación (cuándo NO utilizar capas innecesarias).

---

### PHASE 2.8 — CONTEXT OVERLOAD TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Detectar degradación cognitiva por exceso de contexto.

---

### PHASE 2.9 — ABLATION TEST
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Retirar una capa a la vez de la configuración Full Core.

---

### PHASE 2.10 — COMBINATION INTERFERENCE
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Identificar colisiones de instrucciones y dilución de atención.

---

### PHASE 2.11 — FULL REAL-WORLD E2E
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Benchmark E2E real multi-persona vs Baseline B0.

---

### PHASE 2.12 — CORE REDUCTION AUDIT
- **STATUS**: NOT_STARTED
- **OBJECTIVE**: Clasificación final (KEEP, KEEP ON-DEMAND, SIMPLIFY, MERGE, REMOVE CANDIDATE).
