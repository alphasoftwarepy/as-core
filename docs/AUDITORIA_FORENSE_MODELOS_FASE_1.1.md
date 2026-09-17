# 🕵️ AS-CORE — FASE 1 / SUBFASE 1.1
# MODEL INTELLIGENCE FORENSIC AUDIT
## Capability Catalog + Current Model Policy Discovery

> **DOCUMENTATION STATUS:** AUDIT ONLY / DOCUMENTATION ONLY  
> **DATE:** 2026-09-16  
> **FROZEN CHECKPOINT:** `8825ca2` (Phase 0 Baseline)  
> **PRODUCTION CODE MODIFIED:** 0 files  

---

## 1. STATUS
**GREEN / AUDIT COMPLETE.**  
Auditoría forense finalizada con éxito en todo el repositorio. No se modificó código de producción ni se introdujeron componentes de routing, scoring o auto-swap prematuros.

---

## 2. CHECKPOINT
- **Baseline Congelado:** `8825ca2` (Fase 0: 0.2A, 0.2B, 0.2C, 0.2D GREEN / FREEZE).
- **Invariantes Activas Protegidas:** I1 a I10 (Monousuario estricto, Busy Guard sincrónico, Identidad Física Canónica, Serialización de Carga Atómica, Parada Idempotente sin Huérfanos).

---

## 3. AUDIT SCOPE
Se inspeccionó forensemente la totalidad del repositorio `as-core`:
- `core/` (`engine.py`, `hardware.py`, `moe/`)
- `providers/` (`base.py`, `registry.py`, `litert_embedded.py`, `litert_cli.py`, `litert_compiled.py`, `llamacpp_provider.py`)
- `router/` (`smart_router.py`, `rules.py`)
- `config/` (`settings.py`, `hardware_profiles.py`, `inference_profiles.py`, `config.yaml`, `.env`)
- `runtime/` (`coordinator/`, `capabilities/`, `graph/`, `memory/`, `projects/`, `skills/`)
- `api/` (`routes.py`, `main.py`, `capability_routes.py`, `models.py`, `streaming.py`)
- `benchmarks/` (`runner.py`)
- `moe_poc/` (`data/`, `bins/`, `models/`, `scripts/`)
- `ui/` (`index.html`, `app.js`, `capabilities_ui.js`, `skills_ui.js`)
- `dev-notes/` (`CONTRATOS.md`, `FASE_0_RUNTIME_LIFECYCLE_BASELINE.md`, `historico/`)
- `tests/` (`test_model_residency.py`, `test_model_transitions_contract.py`, `test_cross_provider_physical.py`, `test_lifecycle_hardening.py`, `test_p2_ui_model_validation.py`, `test_llamacpp_provider.py`, etc.)

---

## 4. MODEL INVENTORY
Inventario exhaustivo de modelos presentes en configuración, disco y código:

| Model ID | Display Name | Artifact Path | Format | Size | Provider | Logical Role | Context | Est. VRAM | Est. RAM | Quant | Residency Type | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`chat`** | Gemma 3n E2B (LiteRT) | `models/gemma/gemma-3n-E2B-it-int4.litertlm` | `.litertlm` | 2.0B | `litert_embedded` | `chat` | 2048 | 1500 MB | ~2000 MB | int4 | RESIDENT (FFI GPU) | **CONFIGURED / AVAILABLE / ACTIVE DEFAULT** |
| **`code`** | Gemma Code (LiteRT) | `models/gemma/gemma-3n-E2B-it-int4.litertlm` | `.litertlm` | 2.0B | `litert_embedded` | `code` | 2048 | 1500 MB | ~2000 MB | int4 | RESIDENT (Alias reuse) | **CONFIGURED / AVAILABLE / ACTIVE ALIAS** |
| **`reasoning`** | Gemma 4 E4B (LiteRT) | `models/gemma/gemma-4-E4B-it.litertlm` | `.litertlm` | 4.0B | `litert_cli` | `reasoning` | 2048 | 3660 MB | ~4500 MB | int4 | NON-RESIDENT (Subprocess) | **CONFIGURED / AVAILABLE / DEGRADED PROFILE** |
| **`moe_large`** | Qwen1.5-MoE-A2.7B | `moe_poc/models/qwen1.5-moe-a2.7b-q4_k_m.gguf` | `.gguf` | 14.3B/2.7B | `llamacpp` | `moe_large` | 2048 | 3893 MB | ~10 GB | q4_k_m | RESIDENT (Daemon CUDA) | **CONFIGURED / AVAILABLE** |
| **`olmoe`** | OLMoE-1B-7B-Instruct | `moe_poc/models/OLMoE-1B-7B-0924-Instruct-Q4_K_M.gguf` | `.gguf` | 6.9B/1.0B | `llamacpp` | `olmoe` | 2048 | 3900 MB | ~5 GB | q4_k_m | RESIDENT (Daemon CUDA) | **CONFIGURED / AVAILABLE** |
| **`gemma-3n-web`** | Gemma Web Legacy | `models/gemma/...` | `.litertlm` | 2.0B | `litert_cli` | `chat` | 2048 | 1500 MB | - | int4 | Non-resident | **LEGACY (Reemplazado por `chat`)** |
| **`gemma-3n-code`** | Gemma Code Legacy | `models/gemma/...` | `.litertlm` | 2.0B | `litert_cli` | `code` | 2048 | 1500 MB | - | int4 | Non-resident | **LEGACY (Reemplazado por `code`)** |

---

## 5. LOGICAL ROLE MAP
1. **¿Qué son los roles?**  
   Son alias lógicos configurados como claves en `config.yaml` (`chat`, `code`, `reasoning`, `moe_large`, `olmoe`).
2. **Separación Contrato 0.2B:**  
   `Logical Role != Physical Model`.  
   `chat` y `code` son dos roles lógicos independientes que resuelven a la **misma identidad física canónica**:  
   `litert_embedded::D:\as-core\models\gemma\gemma-3n-E2B-it-int4.litertlm`.  
   `EngineManager._ensure_model_loaded` comprueba esta identidad y reutiliza el puntero GPU sin descargar ni recargar el modelo físico.
3. **Decisor de Roles:**  
   - Si la request trae `model="auto"` o no especifica modelo: `SmartRouter` (en `router/smart_router.py`) evalúa palabras clave.
   - Si la request trae un modelo explícito (`chat`, `code`, `moe_large`, etc.): se respeta directamente el override manual del usuario.
4. **Fallback:**  
   Si `SmartRouter` no detecta keywords de `code` ni de `reasoning`, el fallback estático es `chat`.

---

## 6. PROVIDER INVENTORY
AS-Core cuenta con 4 providers registrados en `ProviderRegistry`:

1. **`litert_embedded` (`LiteRTEmbeddedProvider`):**
   - **Backend:** Python FFI nativo (`litert_lm.Engine`) vía WebGPU/Dawn en GPU dedicada (DirectX).
   - **Residencia:** 100% residente en VRAM.
   - **Streaming:** Desacoplado vía cola concurrente thread-safe (`asyncio.Queue`).
   - **Cancelación:** `conv.cancel_process()`.
   - **Limitación Conocida:** Dawn/WebGPU en Windows no libera buffers inmediatamente dentro del mismo proceso; un intento de swap intra-proceso a otro modelo `.litertlm` (e.g. E4B) entra en `DEGRADED / MEMORY PRESSURE`.

2. **`litert_cli` (`LiteRTCLIProvider`):**
   - **Backend:** Subproceso `litert-lm run` con DirectX GPU shader compiler.
   - **Residencia:** No residente (se ejecuta bajo demanda por subproceso).
   - **Streaming:** Lectura carácter a carácter en stdout con buffer de sanitización y eliminación de logs de arranque.
   - **Cancelación:** `proc.terminate()`.
   - **Limitación Conocida:** Overhead de arranque en cada consulta; sin residencia en memoria.

3. **`llamacpp` (`LlamaCppProvider`):**
   - **Backend:** Daemon HTTP en subproceso (`llama-server.exe`) acelerado por CUDA.
   - **Residencia:** 100% residente en VRAM/RAM mientras el daemon esté activo.
   - **Streaming:** SSE HTTP nativo consumiendo `/v1/chat/completions`.
   - **Cancelación:** Aborto limpio de socket HTTP.
   - **Health Check:** Polling periódico a `/health`.
   - **Swap:** Limpieza total mediante terminación del subproceso (`proc.terminate()` + `proc.wait()`), drenando 100% la VRAM.

4. **`litert_compiled` (`LiteRTCompiledProvider`):**
   - **Backend:** Stub experimental de `ai_edge_litert.CompiledModel`.
   - **Estado:** Inactivo / No funcional.

---

## 7. HARDWARE KNOWLEDGE AUDIT
- **Módulo:** `core/hardware.py`
- **¿Qué detecta?**  
  - GPU: Nombre, VRAM total, VRAM libre, versión de driver (vía `nvidia-smi` CSV o fallback WMI).  
  - RAM: Total MB, libre MB, porcentaje de uso (vía `psutil` o `wmic FreePhysicalMemory`).  
  - CPU: Cores físicos, cores lógicos, soporte AVX/AVX2.  
  - Disco: Espacio total y libre en GB.  
  - Clasificación de Tier: `ULTRA_LIGHT` (<3GB VRAM o <12GB RAM), `BALANCED` (≥3GB VRAM y ≥12GB RAM), `PERFORMANCE` (≥8GB VRAM y ≥32GB RAM).
- **¿Cuándo lo detecta?**  
  Snapshot en startup durante el `lifespan()` de FastAPI en `api/main.py`.
- **¿Dónde se almacena?**  
  En `EngineManager.hardware`.
- **¿Es dinámico?**  
  Las funciones `get_vram_free_mb()` y `get_ram_available_mb()` consultan la máquina en tiempo real, pero el `tier` asignado al motor es estático desde el startup.
- **¿Quién lo utiliza?**  
  - `EngineManager._apply_hardware_profile()`: ajusta `max_vram_mb`, timeouts de descarga y umbral anti-OOM.
  - `EngineManager._check_resources()`: emite logs de advertencia de presión de memoria.
  - `GET /v1/status`: expone el estado al frontend.
  - **SmartRouter y PureCoordinator NO utilizan información de hardware.**

---

## 8. PERFORMANCE DATA INVENTORY
Clasificación estricta de métricas encontradas:

| Dato / Métrica | Valor / Rango | Tipo de Dato | Ubicación |
| :--- | :--- | :--- | :--- |
| **OLMoE Tok/s (Warm)** | 58.3 – 59.9 tok/s | MEASURED RUNTIME / BENCHMARK | `moe_poc/data/p2_ui_model_benchmark.json` |
| **OLMoE TTFT (Warm)** | 265 – 709 ms | MEASURED RUNTIME / BENCHMARK | `moe_poc/data/p2_ui_model_benchmark.json` |
| **OLMoE Cold Start** | 10.6s TTFT (11.2s total) | MEASURED RUNTIME / BENCHMARK | `moe_poc/data/p2_ui_model_benchmark.json` |
| **Qwen MoE Tok/s (Warm)** | 14.9 – 22.1 tok/s | MEASURED RUNTIME / BENCHMARK | `moe_poc/data/p1_benchmark_results.json` |
| **Qwen MoE Cold Start** | 52.0s TTFT (57.2s total) | MEASURED RUNTIME / BENCHMARK | `moe_poc/data/p2_ui_model_benchmark.json` |
| **Gemma E2B Tok/s** | ~15 – 25 tok/s | MEASURED RUNTIME | Logs de `LiteRTEmbeddedProvider` |
| **InferenceMetric Buffer** | Ring buffer (100 items) | DEAD CODE (Unused) | `utils/telemetry.py` (`TelemetryCollector`) |
| **Model Swap Time E2B $\to$ MoE**| ~4.1 s | MEASURED RUNTIME (Phase 0) | Logs de test `test_cross_provider_physical.py` |
| **Model Swap Time MoE $\to$ E2B**| ~3.8 s | MEASURED RUNTIME (Phase 0) | Logs de test `test_cross_provider_physical.py` |
| **Model Swap E2B $\to$ E4B** | ~180 s (Degraded) | MEASURED RUNTIME (Phase 0) | Logs de Subfase 0.2C.1 |

---

## 9. TRANSITION COST DATA
- **Estado Actual:** Los costos de transición física se miden únicamente durante la ejecución de tests o se emiten a los logs informativos (`time.time() - t0`).
- **Persistencia:** **NINGUNA.** Los costos de cambio no se guardan en base de datos ni en memoria compartida. Se pierden inmediatamente al terminar el proceso.

---

## 10. EXISTING CAPABILITIES
Se encontraron tres niveles no conectados de capacidades:

1. **Model Capabilities (Declaradas en `config.yaml`):**
   - `chat`: conversation, planning, analysis, brainstorming, explanations
   - `code`: coding, generation, implementation
   - `reasoning`: architecture, analysis, tradeoffs, reasoning
   - `moe_large`: conversation, coding, reasoning, architecture, analysis
   - `olmoe`: conversation, coding, reasoning, analysis  
   *Hallazgo forense:* Estas listas son decorativas en YAML. `api/main.py` y `EngineManager` las descartan al registrar el modelo.
2. **Provider Capabilities (`providers/base.py`):**
   - Flags técnicas del backend: `supports_gpu`, `supports_streaming`, `supports_speculative_decoding`, `supports_multi_model`, `max_context_length`.
3. **Runtime Tool Capabilities (`runtime/capabilities/`):**
   - Primitivas operativas del sistema: `documents`, `rag`, `git`, `terminal`.

---

## 11. TASK CLASSIFICATION AUDIT
Lógicas existentes de clasificación de tareas:
- **`router/rules.py`:**
  - `REASONING_KEYWORDS`: 51 términos fijos (`why`, `explain`, `analyze`, `architecture`, `design`, `tradeoff`, `plan`, `audit`, etc.).
  - `CODING_KEYWORDS`: 62 términos fijos (`code`, `implement`, `function`, `class`, `refactor`, `test`, `python`, `api`, `dockerfile`, etc.).
- **`router/smart_router.py`:**
  - Clasificación puramente determinista por conteo de intersección de palabras en O(1) con `frozenset`.
  - Si `reasoning_score > coding_score and reasoning_score > 0` $\to$ `reasoning`.
  - Si `coding_score >= reasoning_score and coding_score > 0` $\to$ `code`.
  - De lo contrario $\to$ `chat`.
- **`api/routes.py` (Preset Inference):**
  - Heurística de modo: `coding` (mode code) $\to$ PRECISE (temp 0.1); `sales` $\to$ BALANCED (temp 0.5); `chat`/`conversational` $\to$ CREATIVE (temp 0.8).
- **`runtime/graph/trigger.py`:**
  - Heurística regex determinista para clasificar si una consulta es documental (RAG) o relacional (Graph).

---

## 12. CURRENT ROUTING FLOW
Flujo real exacto de una petición en el runtime actual:

```text
[POST /v1/chat/completions]
          │
          ▼
    api/routes.py
          │
          ├── model_param = body.model != "auto" ? body.model : None
          │
          ▼
    router/smart_router.py :: route(user_message, model_param)
          │
          ├── Si model_param existe: retorna explicit_model (Override Manual)
          │
          └── Si model == "auto":
                    └── Cuenta keywords (REASONING vs CODING)
                              ├── reasoning > coding  ──► "reasoning" (Gemma E4B)
                              ├── coding >= reasoning ──► "code" (Gemma E2B)
                              └── ninguno             ──► "chat" (Gemma E2B)
          │
          ▼
    PureCoordinator.assemble(...) -> Inyecta contexto (RAG, Graph, Memory, Prompts)
          │
          ▼
    AgentControlRunner.run_inference_loop*(...)
          │
          ▼
    core/engine.py :: generate(InferenceRequest)
          │
          ├── 1. BUSY GUARD: ¿Otro modelo está generando? -> Error BUSY
          ├── 2. ¿El modelo ya está cargado en su provider? -> Rápido retorno
          ├── 3. Mutex _load_lock:
          │         ├── ¿Mismo physical identity residente? -> Reutiliza puntero (0 recarga)
          │         ├── Si tier != PERFORMANCE: Descarga modelos en otros providers
          │         └── provider.load_model(model_id, path)
          │
          ▼
    Active Provider :: generate() / generate_stream()
```

---

## 13. FALLBACKS
- **Fallback de Hardware:** `LiteRTEmbeddedProvider` captura excepción al inicializar en GPU y reintenta en CPU (`Backend.CPU`).
- **Fallback de Router:** `SmartRouter` recurre al modelo por defecto (`chat`) si no hay keywords.
- **Fallback de Perfil:** `config/inference_profiles.py` devuelve perfil genérico si el ID no está registrado.
- **Fallback de Puertos:** `LlamaCppProvider._find_available_port` escanea hasta 25 puertos alternativos ante colisiones.
- **Falta Absoluta de Fallback Cognitivo:** No existe mecanismo para degradar de modelo si la inferencia es lenta, ni para escalar si la respuesta es insuficiente.

---

## 14. LEGACY / DEAD CODE AUDIT
Componentes que no participan en el pipeline productivo:

1. **`utils/telemetry.py` (`TelemetryCollector`):**
   - *Diagnóstico:* Clase de recolección de métricas no instanciada ni llamada en ningún archivo del repo.
   - *Acción:* `REMOVE LATER`.
2. **`config/hardware_profiles.py` (`PROFILES`):**
   - *Diagnóstico:* Dataclass estática ignorada por `EngineManager`, que aplica sus propios ajustes en `_apply_hardware_profile()`.
   - *Acción:* `SIMPLIFY / MERGE`.
3. **`config/inference_profiles.py` (`INFERENCE_PROFILES`):**
   - *Diagnóstico:* Solo contiene entradas para `chat` y `code`. Ignora `reasoning`, `moe_large` y `olmoe`.
   - *Acción:* `SIMPLIFY / MERGE`.
4. **`providers/litert_compiled.py`:**
   - *Diagnóstico:* Stub no funcional de `ai-edge-litert`.
   - *Acción:* `LEGACY BUT HARMLESS` (no eliminar para evitar romper registros opcionales).
5. **`benchmarks/runner.py`:**
   - *Diagnóstico:* Script de benchmark aislado sin invocadores en runtime ni tests.
   - *Acción:* `LEGACY BUT HARMLESS`.
6. **`SkillSpec.recommended_model`:**
   - *Diagnóstico:* Campo presente en `temporary.py`, `factory.py` y en la UI de skills, pero completamente ignorado por `api/routes.py` y `SmartRouter`.
   - *Acción:* `KEEP` (puede reutilizarse como input para Fase 1).

---

## 15. CONFIGURATION MAP
- **HARDCODED:**
  - Listas de keywords en `router/rules.py`.
  - Prompts de sistema estáticos en `router/rules.py` (`SYSTEM_PROMPTS`).
  - Opciones de modelos en `ui/index.html` (`<select id="quickModelSelect">`).
  - Presets semánticos en `api/routes.py` (`PRECISE`, `BALANCED`, `CREATIVE`).
- **CONFIGURED:**
  - Definición de modelos, providers y timeouts en `config.yaml`.
  - Variables de entorno `ASCODE_*` en `config/settings.py`.
- **DISCOVERED:**
  - Hardware, GPU, VRAM y RAM al inicio vía `core/hardware.py`.
  - Residencia física activa vía `provider.is_model_loaded()`.
  - Habilidades instaladas vía `SkillLoader`.
  - Primitivas del entorno vía `CapabilityRegistry`.
- **MEASURED:**
  - VRAM libre y RAM disponible vía `get_vram_free_mb()` y `get_ram_available_mb()`.
  - Tokens por segundo y latencia por chunk en cada proveedor.

---

## 16. TEST COVERAGE
Comportamientos protegidos por tests automatizados:
- **Residencia Física (0.2A):** Carga única $A \to A \to A$ verificada en `test_model_residency.py`.
- **Reutilización por Identidad Canónica (0.2B):** Reutilización de puntero FFI entre alias lógicos `chat` y `code` en `test_model_residency.py`.
- **Contrato de Transición Física (0.2C.2B):** Busy Guard, aislamiento de fallos al cargar destino y fail-fast en multiusuario en `test_model_transitions_contract.py`.
- **Ciclo Real Cross-Provider (0.2C.2B):** Transición física E2B $\to$ OLMoE $\to$ E2B en hardware en `test_cross_provider_physical.py`.
- **Hardening de Ciclo de Vida (0.2D):** Exclusión mutua monousuario, mutex de carga `_load_lock`, desbloqueo en excepciones/cancelaciones y parada limpia en `test_lifecycle_hardening.py`.
- **Validación UI y Modos (P2):** Selector de modelos AUTO vs MANUAL en `test_p2_ui_model_validation.py`.
- **Provider llama.cpp (P1):** Ciclo de vida de subproceso daemon CUDA en `test_llamacpp_provider.py`.

---

## 17. OBSERVABILITY AUDIT
El endpoint `GET /v1/status` reporta:
- `active_model`: ID lógico activo.
- `active_physical_model`: Identidad canónica `{provider_id}::{realpath}`.
- `hardware_tier`: Clasificación de hardware.
- `gpu`: Nombre, VRAM total y VRAM libre instantánea.
- `ram_available_mb`: RAM libre en el sistema.
- `provider`: Métricas del provider activo (e.g. `process_pid`, `server_port`, `uptime_seconds`, `last_tok_s`, `last_ttft_ms`).
- `residency`: Estadísticas de tiempo ocioso y tiempo absoluto de vida por modelo.

**Gaps en Observabilidad:**
- No reporta historial de cambios de modelo ni tiempos requeridos para swapping.
- No reporta rendimiento medio histórico por modelo en la máquina local.
- No advierte si un modelo configurado se encuentra en estado `DEGRADED` (e.g. E4B).

---

## 18. RAG DEPENDENCIES
- RAG (`api/rag_service.py`, `api/embedder_service.py`) utiliza `BAAI/bge-small-en-v1.5` de forma local y desacoplada en CPU.
- RAG **no fuerza** ningún modelo de generación. El contexto RAG se inyecta como texto plano en el System Prompt independientemente de qué LLM esté activo.

---

## 19. GRAPH DEPENDENCIES
- El subsistema Knowledge Graph (`runtime/graph/`) es 100% determinista y no llama a ningún LLM.
- La ingesta y las consultas no imponen ningún modelo. El formateador relacional inyecta Markdown en el prompt para cualquier modelo que se encuentre en ejecución.

---

## 20. MEMORY DEPENDENCIES
- Working Memory (`runtime/memory/manager.py`) opera directamente contra SQLite (`data/rag.db`).
- Es agnóstica al modelo; inyecta variables, tareas y observaciones en el prompt sin requerir un LLM específico.

---

## 21. SKILLS DEPENDENCIES
- Las Skills oficiales y experimentales contienen un campo de metadatos `recommended_model` (por defecto `"code"`).
- Actualmente este campo es **informativo y pasivo**; no fuerza la selección del modelo en el pipeline. Si se cambia la política de selección, ninguna skill oficial se rompe.

---

## 22. AGENT LOOP DEPENDENCIES
- `AgentControlRunner` (`runtime/coordinator/agent.py`) evalúa `model_type` obtenido de `config.yaml` a través de `PureCoordinator.assemble`:
  - `model_type == "agent"` $\to$ `capability_gate_open = True`.
  - `model_type in ("coding", "reasoning", "moe", "moe_research")` $\to$ abre compuerta solo si la skill activa usa capacidades.
  - Otros $\to$ compuerta cerrada.
- Por tanto, cualquier nuevo modelo o rol debe declarar un `type` reconocido para no bloquear involuntariamente las herramientas del agente.

---

## 23. CURRENT MODEL POLICY
> **Hoy AS-Core decide qué modelo utilizar de esta manera:**
> 1. Si el usuario seleccionó un modelo en el dropdown de la UI (e.g. `chat`, `reasoning`, `olmoe`, `moe_large`), ese valor viaja en `body.model` y tiene **prioridad absoluta e inmediata**.
> 2. Si el valor es `"auto"`, `SmartRouter` inspecciona las palabras del mensaje del usuario y cuenta cuántas coinciden con dos listas estáticas de palabras clave (`REASONING_KEYWORDS` vs `CODING_KEYWORDS`). Si gana reasoning, elige `"reasoning"` (Gemma E4B); si gana coding, elige `"code"` (Gemma E2B); si hay empate o ninguna, elige `"chat"` (Gemma E2B).
> 3. Los modelos MoE (`olmoe` y `moe_large`) **nunca son seleccionados de forma automática**; solo pueden usarse por selección manual explícita del usuario.
> 4. `EngineManager` recibe la orden y, si el modelo pedido no está en memoria, expulsa de inmediato el modelo anterior y carga el nuevo, sin evaluar si el cambio cuesta 4 segundos o 3 minutos, ni si el hardware actual sufrirá congelamiento.

---

## 24. WHAT AS-CORE KNOWS
- Sabe qué modelo físico e identidad canónica están actualmente residentes en memoria.
- Sabe si el motor está generando activamente (`_is_generating`).
- Sabe cuánta VRAM y RAM total y libre tiene la máquina en el startup y mediante consultas ad-hoc.
- Sabe si un modelo solicitado comparte el artefacto físico con el modelo residente para no recargarlo.
- Sabe apagar procesos daemon de llama.cpp limpiamente liberando el 100% de la VRAM.

---

## 25. WHAT AS-CORE DOES NOT KNOW
- **No sabe el costo de transición:** Desconoce cuánto tiempo tardará en cargar cada modelo en la máquina local.
- **No sabe la viabilidad operativa local:** Trata a Gemma E4B como una opción válida de reasoning en modo "auto", a pesar de que en la GPU local de 4GB tarda 180 segundos en cargar y entra en presión crítica de memoria.
- **No sabe si el modelo actual es suficiente:** Si el usuario está conversando con Gemma E2B residente y hace una pregunta con la palabra "explain", el router intenta cambiar a E4B aunque E2B sea perfectamente capaz de responder.
- **No conoce el rendimiento histórico:** No recuerda si un modelo dio 59 tok/s o 1 tok/s en la última sesión.
- **No previene el vaivén (thrashing):** Si dos mensajes seguidos alternan entre una pregunta conceptual y una línea de código, el sistema descargará y cargará modelos alternadamente sin histeresis.

---

## 26. STATIC VS MEASURED
La futura inteligencia debe desacoplar claramente dos fuentes de verdad:

1. **Static Model Facts (Invariantes del Artefacto):**
   - Parámetros (billions), tipo de arquitectura (dense vs MoE), cuantización (`int4`, `q4_k_m`), longitud de contexto nativa, formato (`.litertlm`, `.gguf`), provider requerido.
2. **Measured Machine-Specific Facts (Realidad del Hardware Local):**
   - Tiempo de carga en frío (cold load time en segundos).
   - Tiempo de transición/swap entre pares específicos de modelos.
   - Rendimiento real medido (tok/s y TTFT en ms).
   - Presión real de VRAM y RAM observada.
   - Calificación de estado en este equipo: `HEALTHY`, `MARGINAL`, o `DEGRADED`.

---

## 27. MACHINE-SPECIFIC FINDINGS
- En una máquina con 4GB VRAM (como la GTX 1650 Ti auditada):
  - **Gemma E2B:** Carga rápida, ~1.5 GB VRAM, rendimiento fluido $\to$ `HEALTHY`.
  - **OLMoE (6.9B/1B MoE):** Swap en ~4s, ~3 GB VRAM, 59 tok/s $\to$ `HEALTHY / EXCELLENT`.
  - **Qwen MoE (14.3B/2.7B):** Carga pesada (~50s cold), ~4 GB VRAM, 15-20 tok/s $\to$ `FUNCTIONAL / HIGH LOAD`.
  - **Gemma E4B (DirectX CLI):** Carga de ~180s, memoria saturada $\to$ `DEGRADED / OPERATIONAL RISK`.
- En una máquina con 16GB o 24GB VRAM, esa misma Gemma E4B cargaría en 2 segundos y sería `HEALTHY`.
- **Conclusión fundamental:** Las políticas de recomendación **nunca deben hardcodear** qué modelo es "bueno" o "malo". Deben basarse en un perfil calibrado en la máquina del usuario.

---

## 28. MINIMUM INFORMATION REQUIRED
Para que AS-Core pueda razonar:
> *"El modelo actual probablemente es suficiente"*  
> o  
> *"Existe otro modelo más adecuado; cambiar tomará aproximadamente X segundos"*

Requiere únicamente **4 piezas mínimas de información**:
1. **Modelo Físico Residente Actual:** (Ya disponible en `EngineManager.active_model`).
2. **Requerimiento Mínimo de la Tarea:** Complejidad estimada (`low`, `medium`, `high`) y dominio (`general`, `code`, `reasoning`).
3. **Catálogo de Capacidades Relativas:** Qué modelos locales satisfacen ese requerimiento.
4. **Costo de Transición Estimado:** Tiempo en segundos de swap desde el modelo actual hacia el candidato.

---

## 29. SWITCH COST FINDINGS
- Si el modelo residente actual tiene capacidad suficiente para resolver la tarea con calidad aceptable, el costo de cambio siempre supera al beneficio:
  $$\text{Beneficio}(\Delta \text{Calidad}) < \text{Costo}(\text{Latencia de Swap})$$
- Ejemplo: Si el usuario pide resumir un párrafo estando en Gemma E2B, recomendar un swap a OLMoE (4s) o a E4B (180s) destruye la experiencia de usuario. Mantener E2B es la decisión correcta.

---

## 30. HYSTERESIS / COOLDOWN FINDINGS
- Actualmente **no existe cooldown ni histeresis** en el ruteo.
- Para evitar el fenómeno oscilatorio ($A \to B \to A \to B$), cualquier recomendación futura debe considerar:
  - Residencia mínima (e.g. no recomendar cambio si el modelo actual cargó hace menos de $N$ segundos o si la conversación mantiene el mismo hilo temático).
  - Inercia del modelo activo: el modelo residente debe tener una bonificación sustancial de estabilidad en cualquier evaluación.

---

## 31. PRE-MORTEM (Riesgos de Fase 1 Mal Diseñada)

| Riesgo | Probabilidad | Impacto | Detectabilidad | Principio de Mitigación |
| :--- | :---: | :---: | :---: | :--- |
| **1. Recomendación constante de cambio** | Alta | Alto | Inmediata (molestia visual al usuario) | Regla de Inercia: Solo sugerir si la brecha de capacidad es insalvable por el modelo actual. |
| **2. Sesgo de tamaño ("más grande = mejor")**| Alta | Medio | Alta (swaps lentos injustificados) | Basar decisiones en benchmarks locales (OLMoE 1B rinde más rápido que E4B). |
| **3. Recomendar modelos degradados** | Alta | Crítico | Alta (congelamiento de 3 minutos) | Blacklist/Filtro de hardware: Modelos `DEGRADED` en esta máquina no se sugieren en AUTO. |
| **4. Invasión de responsabilidades en EngineManager** | Media | Alto | Media (código acoplado en core) | EngineManager solo ejecuta órdenes físicas. El decisor reside en una capa superior pura. |
| **5. Subjetividad por números mágicos (scores 8/10)**| Alta | Medio | Baja (deuda técnica silenciosa) | Evitar scoring numérico arbitrario. Usar capacidades discretas y costos medidos. |
| **6. Auto-Swap compulsivo (ignorar al usuario)**| Media | Crítico | Inmediata (pérdida de control) | Human-in-the-Loop estricto: El runtime sugiere con badge/notificación; el usuario hace clic para autorizar el swap. |

---

## 32. FIVE-STEP ANALYSIS

1. **Question Requirements:**  
   ¿Necesitamos un router neural o un clasificador LLM? No. Analizar la tarea con otro LLM añade latencia y consume VRAM. Se requiere análisis heurístico y determinista ligero.
2. **Delete:**  
   Eliminar `utils/telemetry.py` (código muerto). Dejar de pretender que `config/inference_profiles.py` gobierna la inferencia cuando solo tiene 2 modelos incompletos.
3. **Simplify:**  
   El contrato de recomendación debe ser binario y explicable:  
   `Recommendation = (keep_current | suggest_swap, candidate_model, estimated_swap_sec, reason)`.
4. **Accelerate:**  
   La decisión de recomendación debe tomar menos de 1 milisegundo (análisis léxico y consulta de tabla en memoria).
5. **Automate:**  
   Medir los tiempos de swap reales durante el uso y registrarlos en el perfil de hardware local, en lugar de configurar números a mano.

---

## 33. OPCIONES ARQUITECTÓNICAS (MÁXIMO 3)

### Opción A: Static Capability & Cost Catalog (Catálogo Estático Simple)
- **Concepto:** Se declaran en `config.yaml` las capacidades de cada modelo y un costo estimado estático de carga. Un evaluador puro compara la intención del prompt con el modelo activo.
- **Complejidad:** Muy Baja.
- **Mantenimiento:** Bajo.
- **Precisión:** Media (no se adapta si la máquina del usuario es lenta o rápida).
- **Riesgo:** Bajo.
- **Reutiliza:** Estructura existente de `config.yaml` y reglas de `router/rules.py`.

### Opción B: Static Capabilities + Measured Machine Profile (Empírico & Calibrado) — *(Recomendada)*
- **Concepto:** Las capacidades intrínsecas del modelo son estáticas (lo que sabe hacer la arquitectura), pero los costos operativos (tiempo de swap, tok/s, viabilidad de memoria) se leen de un perfil de máquina medido localmente (aprovechando los datos empíricos de benchmark que ya existen en el proyecto).
- **Complejidad:** Media.
- **Mantenimiento:** Bajo.
- **Precisión:** Muy Alta (evita recomendar E4B en la GPU local porque su perfil local está marcado como `DEGRADED`).
- **Riesgo:** Muy Bajo (preserva todas las invariantes de Fase 0 y mantiene el control en el usuario).
- **Reutiliza:** `core/hardware.py`, mediciones reales de Fase 0/P1/P2, `SmartRouter`, `PureCoordinator`.

### Opción C: Dynamic Telemetry & Benchmark-Driven Intelligence (Auto-tuning Complejo)
- **Concepto:** El sistema re-evalúa y re-calibra continuamente el rendimiento de cada modelo con micro-benchmarks en background y telemetría en tiempo real.
- **Complejidad:** Alta.
- **Mantenimiento:** Alto.
- **Precisión:** Alta pero variable.
- **Riesgo:** Alto (hilos de fondo pueden competir por VRAM y violar la exclusión mutua de inferencia).
- **Reutiliza:** `benchmarks/runner.py`, `utils/telemetry.py`.

---

## 34. PROPUESTA ARQUITECTÓNICA MÍNIMA RECOMENDADA
Se recomienda avanzar hacia la **Opción B** en las siguientes subfases de Fase 1:
1. **Catalogar capacidades declarativas verificables** para los modelos soportados (`chat/code` = E2B, `reasoning` = E4B, `moe` = OLMoE / Qwen).
2. **Definir un Machine Profile local** que contenga los tiempos medidos de carga y el estado operativo en este hardware (`HEALTHY` vs `DEGRADED`).
3. **Diseñar un Evaluador Puro de Recomendación** (`ModelAdvisor`) que resida en el Runtime Coordinator (fuera de `EngineManager`):
   - Input: `user_message`, `active_model`, `machine_profile`.
   - Output: `KeepCurrent` o `SuggestModel(target, swap_cost_sec, reason)`.
4. **Respetar la frontera Human-in-the-loop:** El backend expone la sugerencia en los metadatos de la respuesta; la UI muestra la recomendación; **el usuario decide si hace clic para cambiar de modelo**.

---

## 35. ARCHIVOS QUE PROBABLEMENTE CAMBIARÍAN EN SUBFASES POSTERIORES
*(Solo como proyección de diseño — Ninguno modificado en 1.1)*
- `config/settings.py` / `config.yaml`: Centralizar metadata de modelos y profile de hardware.
- `router/smart_router.py`: Evolucionar o desacoplar hacia recomendador puro.
- `runtime/coordinator/manager.py`: Integrar evaluación de recomendación sin efectos colaterales.
- `ui/app.js` / `ui/index.html`: Indicador de sugerencia de modelo no intrusivo con botón de confirmación.

---

## 36. INVARIANTES DE FASE 0 QUE NO PUEDEN ROMPERSE
- **I1:** Máximo 1 inferencia física activa en el runtime.
- **I2:** Prohibido descargar un modelo físico mientras se encuentre generando.
- **I3:** Misma identidad física canónica $\implies$ reutilización obligatoria (0 recarga).
- **I4:** Fallo en la carga del modelo destino $\implies$ estado activo queda en `None`, nunca en un valor inconsistente.
- **I5 / I6:** Liberación incondicional de Busy Guards en bloques `finally` ante errores o cancelaciones.
- **I7:** Parada limpia y 0 procesos huérfanos.
- **I8:** El estado reportado en `active_model` refleja estrictamente la realidad física del provider.
- **I9:** Modo multiusuario reservado con fail-fast inmediato.
- **I10:** Cargas físicas concurrentes estrictamente serializadas por mutex.

---

## 37. CLAUDE REVIEW PACKAGE
*(Sección compacta autocontenida para revisión técnica externa)*

```markdown
=== CLAUDE REVIEW PACKAGE — AS-CORE PHASE 1 / SUBPHASE 1.1 ===

1. PROBLEMA:
AS-Core cuenta hoy con un runtime físico estable y endurecido (Fase 0 congelada en 8825ca2 con 10 invariantes), capaz de mantener modelos residentes (Gemma E2B) y alternar limpiamente con otros backends (OLMoE/Qwen MoE en llama.cpp). Sin embargo, carece de inteligencia de selección: el ruteo automático actual es un conteo rudimentario de palabras clave (coding vs reasoning) que desconoce el costo de cambio físico (e.g. 4s vs 180s) y el estado del hardware, derivando solicitudes a modelos degradados (E4B en 4GB VRAM) o ignorando modelos superiores disponibles (MoE).

2. ARQUITECTURA ACTUAL:
- EngineManager: Orquestador físico. Conoce identidad canónica ({provider}::{path}), maneja mutex _load_lock y Busy Guard. No sabe de semántica ni tareas.
- SmartRouter: Filtro léxico en router/smart_router.py. Solo conoce "chat", "code", "reasoning". Ignora MoE y desconoce si el modelo destino tardará 3 minutos en cargar.
- Providers activos: litert_embedded (FFI GPU residente), llamacpp (daemon CUDA residente), litert_cli (subprocess bajo demanda).
- UI: Selector manual que antepone la decisión del usuario (MANUAL > AUTO).

3. GAPS IDENTIFICADOS:
- Sin noción de costo de transición: El motor descarga y carga sin evaluar el impacto en latencia.
- Sin perfil de viabilidad de máquina: En 4GB VRAM, E4B tarda ~3 min y satura memoria, pero el router lo selecciona si el usuario escribe "explain".
- MoE inaccesible en AUTO: OLMoE (59 tok/s, swap en 4s) solo puede usarse si el usuario lo elige manualmente en el dropdown.
- Metadatos desconectados: config.yaml tiene listas de "capabilities" que el código descarta en el startup.

4. OPCIONES EVALUADAS:
- Opción A: Catálogo estático en YAML (Complejidad muy baja, pero no distingue diferencias entre máquinas).
- Opción B: Capacidades estáticas intrínsecas + Perfil de máquina medido localmente (Complejidad media, máxima fidelidad operativa en hardware real, previene seleccionar modelos degradados).
- Opción C: Auto-tuning dinámico con micro-benchmarks continuos en runtime (Complejidad alta, riesgo de violar invariantes de exclusión mutua de GPU).

5. PROPUESTA RECOMENDADA:
Opción B. Mantener EngineManager intacto (solo ejecuta cargas físicas). Construir un ModelAdvisor puro en la capa de coordinación que evalúe: (a) modelo residente actual, (b) requisitos de la tarea, (c) capacidades del catálogo y (d) perfil medido de la máquina. Si el modelo actual basta, se mantiene (Regla de Inercia). Si otro modelo conviene netamente, se genera una sugerencia con tiempo estimado de cambio, preservando el principio Human-in-the-Loop (el usuario confirma el swap).

6. RIESGOS PRINCIPALES:
- Thrashing (swaps continuos en prompts sucesivos) -> Mitigado con bonificación de inercia al modelo residente.
- Pérdida de control del usuario -> Mitigado manteniendo la decisión final en el usuario (sugerencia no bloqueante, nunca auto-swap agresivo).
- Violación de invariantes de Fase 0 -> Mitigado desacoplando el Advisor del EngineManager.

7. ARCHIVOS A TOCAR EN SUBFASES POSTERIORES:
config/settings.py, config.yaml, router/smart_router.py, runtime/coordinator/manager.py, ui/app.js. (0 archivos modificados en 1.1).

8. INVARIANTES INTOCABLES DE FASE 0:
I1 (Single inference max), I2 (No unload during inference), I3 (Physical identity reuse), I4 (Target failure safe state), I5-I6 (Guards release in finally), I7 (Zero orphan processes), I8 (State reflects physical reality), I9 (Single-user only / multi-user fail-fast), I10 (Load serialization lock).
=============================================================
```

---

## 38. FILES MODIFIED
- `docs/AUDITORIA_FORENSE_MODELOS_FASE_1.1.md` (DOCUMENTATION ONLY)
- **0 archivos de código de producción modificados.**

---

## 39. GIT STATUS
- Working tree limpio de cambios de código de producción.
- Rama `main`, baseline verificado en `8825ca2`.

---

## 40. FINAL VERDICT
**GREEN / AUDIT COMPLETE.**  
La auditoría forense de Fase 1 / Subfase 1.1 ha sido completada en su totalidad, cumpliendo todos los requerimientos de descubrimiento, mapeo y análisis sin alterar el código de producción ni reabrir los contratos congelados de Fase 0.
