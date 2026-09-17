# AS-CORE — FASE 1 / SUBFASE 1.2
# CAPABILITY CONTRACT + MODEL EVIDENCE MATRIX

> **Fecha:** 2026-09-16  
> **Naturaleza:** auditoría, medición local e instrumentación aislada  
> **Checkpoint congelado de Fase 0:** `8825ca2`  
> **HEAD auditado:** `7b9191c534cac169f31681a8d38457bb43309986`  
> **Código productivo modificado:** 0 archivos  
> **Verdict:** **GREEN / READY FOR 1.3**

---

## 1. STATUS

**GREEN / READY FOR 1.3.**

Existe evidencia objetiva suficiente para diseñar posteriormente una política mínima y explicable de suficiencia/recomendación sin usar tamaño, scoring arbitrario ni afirmaciones provenientes únicamente de `config.yaml`.

Este estado no significa que todos los modelos hayan pasado, ni que deba implementarse selección automática. Significa que:

- existe un contrato de capabilities pequeño y reproducible;
- se ejecutaron 36 evaluaciones actuales sobre tres identidades físicas seguras;
- Gemma E4B quedó explícitamente bloqueado por restricción operacional conocida, sin inventar evidencia cognitiva;
- se separaron hechos estáticos, resultados medidos actuales y resultados históricos;
- se midió el SmartRouter sin modificarlo;
- las invariantes I1-I10 continúan protegidas por 19/19 regresiones antes y después de la instrumentación.

No se implementó Fase 1.3.

---

## 2. BASELINE

### 2.1 Git

- Rama: `main`.
- HEAD: `7b9191c534cac169f31681a8d38457bb43309986`.
- `8825ca2` es ancestro de HEAD.
- Los commits posteriores al checkpoint son documentación de cierre de Fase 0 y auditoría 1.1.
- Working tree inicial: limpio; solo se observó el warning externo de Git por falta de acceso a `C:\Users\rva10\.config\git\ignore`.

### 2.2 Baseline congelado

- 0.2A Model Residency: GREEN / FREEZE.
- 0.2B Physical Identity & Alias Reuse: GREEN / FREEZE.
- 0.2C Transition Contract: GREEN / FREEZE.
- 0.2D Lifecycle Hardening: GREEN / FREEZE.
- Fase 1.1 Model Intelligence Forensic Audit: GREEN / FREEZE.

### 2.3 Invariantes I1-I10

| Invariante | Protección observada |
|---|---|
| I1: máximo una inferencia activa | Busy guard sincrónico en `generate` y `generate_stream` |
| I2: no unload durante inferencia | guards en load/unload loop |
| I3: misma identidad física implica reuse | canonical identity provider + realpath |
| I4: fallo de carga no deja destino activo | estado activo se limpia en excepción |
| I5: fallo de generación libera guard | `finally` no streaming |
| I6: cancelación libera guard | `finally` streaming |
| I7: shutdown sin huérfanos | terminate/wait/kill de llama.cpp |
| I8: active model refleja realidad física | consultas `is_model_loaded` y sincronización explícita |
| I9: multi-user fail-fast | `RuntimeError` en `EngineManager.__init__` |
| I10: cargas incompatibles serializadas | `_load_lock` + double-check |

La instrumentación de 1.2 usa únicamente APIs públicas existentes; no altera ninguno de estos mecanismos.

---

## 3. FILES INSPECTED

Principales archivos y artefactos inspeccionados:

- `dev-notes/FASE_0_RUNTIME_LIFECYCLE_BASELINE.md`
- `docs/AUDITORIA_FORENSE_MODELOS_FASE_1.1.md`
- `dev-notes/CONTRATOS.md`
- `config.yaml`
- `config/settings.py`
- `core/engine.py`
- `core/hardware.py`
- `providers/base.py`
- `providers/registry.py`
- `providers/litert_embedded.py`
- `providers/litert_cli.py`
- `providers/litert_compiled.py`
- `providers/llamacpp_provider.py`
- `router/smart_router.py`
- `router/rules.py`
- `runtime/coordinator/manager.py`
- `runtime/coordinator/agent.py`
- `runtime/coordinator/parser.py`
- `runtime/skills/models.py`
- `runtime/skills/temporary.py`
- `runtime/skills/loader.py`
- `runtime/skills/factory.py`
- `benchmarks/runner.py`
- `scratch/benchmark_inference.py`
- `moe_poc/scripts/run_p1_benchmark.py`
- `moe_poc/scripts/run_p2_ui_benchmark.py`
- `moe_poc/data/p1_benchmark_results.json`
- `moe_poc/data/p2_ui_model_benchmark.json`
- `tests/test_model_residency.py`
- `tests/test_model_transitions_contract.py`
- `tests/test_cross_provider_physical.py`
- `tests/test_lifecycle_hardening.py`
- `tests/test_agent_loop_hardening.py`
- `tests/test_p2_ui_model_validation.py`

También se verificaron físicamente los artefactos bajo `models/gemma/`, `moe_poc/models/` y el binario `moe_poc/bins/llama-server.exe`.

---

## 4. PHYSICAL MODEL INVENTORY

Los parámetros y cuantizaciones indicados como **DECLARED** proceden de configuración/nombre del artefacto; no se reinterpretan como evidencia de calidad.

| Identidad física | Artefacto local | Bytes | Formato | Arquitectura/params | Provider configurado | Contexto efectivo actual | Estado local |
|---|---|---:|---|---|---|---:|---|
| Gemma E2B | `models/gemma/gemma-3n-E2B-it-int4.litertlm` | 3,655,827,456 | LiteRT-LM | 2.0B, int4 (**DECLARED**) | `litert_embedded` | 2048 | AVAILABLE / CURRENT_MEASURED |
| Gemma E4B | `models/gemma/gemma-4-E4B-it.litertlm` | 3,659,530,240 | LiteRT-LM | 4.0B, int4 (**DECLARED**) | `litert_cli` | min(runtime 2048, provider 4096) | AVAILABLE / DEGRADED HISTORICAL |
| OLMoE | `moe_poc/models/OLMoE-1B-7B-0924-Instruct-Q4_K_M.gguf` | 4,213,513,024 | GGUF | 6.9B/1.0B, MoE Q4_K_M (**DECLARED**) | `llamacpp` | 2048 | AVAILABLE / CURRENT_MEASURED |
| Qwen1.5 MoE | `moe_poc/models/qwen1.5-moe-a2.7b-q4_k_m.gguf` | 9,496,139,040 | GGUF | 14.3B/2.7B, MoE Q4_K_M (**DECLARED**) | `llamacpp` | 2048 | AVAILABLE / CURRENT_MEASURED / HIGH PRESSURE |

Hardware de la medición actual:

- GPU: NVIDIA GeForce GTX 1650 Ti.
- VRAM total: 4096 MB; libre al inicio de cada suite: 3935 MB.
- Driver: 595.71.
- RAM total observada durante auditoría de entorno: 16,221 MB.

No se detectaron otros artefactos de modelo productivos fuera de los ya inventariados. Los caches `.bin`/XNNPACK de Gemma no son identidades de modelo adicionales.

---

## 5. LOGICAL ROLE MAP

| Rol lógico | Identidad física | Provider | `model_type` | Consecuencia |
|---|---|---|---|---|
| `chat` | Gemma E2B | `litert_embedded` | `general` | capability gate off |
| `code` | Gemma E2B | `litert_embedded` | `coding` | gate `on_if_skill`; prompt family software |
| `reasoning` | Gemma E4B | `litert_cli` | `reasoning` | gate `on_if_skill`; costo/riesgo alto local |
| `moe_large` | Qwen1.5 MoE | `llamacpp` | `moe` | manual; gate `on_if_skill` |
| `olmoe` | OLMoE | `llamacpp` | `moe_research` | manual; gate `on_if_skill` |

Conclusiones:

1. `chat` y `code` comparten exactamente artefacto y provider. Su evidencia cognitiva física no debe duplicarse.
2. Los roles sí pueden cambiar system prompt, prompt family y capability gate. Por ello, el overlay lógico no debe confundirse con la identidad física ni eliminarse del contrato de ejecución.
3. Los IDs históricos `gemma-3n-web` y `gemma-3n-code` son legacy documentado, no modelos físicos adicionales.

---

## 6. EXISTING CAPABILITY AUDIT

| Fuente | Ejemplos | Clasificación | Consumo real | Hallazgo |
|---|---|---|---|---|
| `config.yaml.models.*.capabilities` | conversation, coding, reasoning, architecture | **DECLARED / UNVERIFIED / parcialmente LEGACY** | descartado por `api/main.py` al registrar modelos | no demuestra comportamiento |
| `model_type` | general, coding, reasoning, moe | **DECLARED + CONSUMED** | `PureCoordinator` decide prompt family y capability gate | es política operacional, no calidad cognitiva |
| `ProviderCapabilities` | GPU, streaming, context, quantization | **DECLARED + parcialmente CONSUMED** | registry/status; el engine no selecciona modelo por ellas | describe backend, no tarea |
| runtime tool capabilities | documents, rag, git, terminal | **MEASURED/OPERATIONAL** según `check()` | Agent Loop y SkillLoader | namespace distinto de model capabilities |
| `SkillSpec.requested_capabilities` / `required_scopes` | documents.read, etc. | **DECLARED + CONSUMED** | compatibilidad de skills | son permisos/scopes, no aptitud del modelo |
| `SkillSpec.recommended_model` | code, reasoning | **DECLARED / LEGACY-ADVISORY** | guardado y mostrado; no rutea | default `code` introduce sesgo histórico |
| SmartRouter keywords | coding/reasoning | **INFERRED + CONSUMED** | decisión AUTO | señal lexical, no evidencia de capacidad |

Hallazgo crítico: las listas YAML asignan distintas capabilities a `chat` y `code` aunque ambos sean el mismo E2B. La medición actual además verifica en E2B capacidades no declaradas en esas listas (structured extraction, grounded answering y tool protocol). Por tanto, el catálogo YAML actual no puede ser fuente de verdad.

---

## 7. PROPOSED MINIMUM CAPABILITY CONTRACT

### 7.1 Resultado de validar la hipótesis de seis dimensiones

Se mantiene el conjunto de seis, con semántica operacional estricta:

| Capability | Requisito observable mínimo | Razón para mantenerla separada |
|---|---|---|
| `summarization` | comprimir preservando hechos/restricciones y sin inventar | no equivale a conversación ni extracción literal |
| `structured_extraction` | producir estructura válida, campos y normalización solicitados | el schema puede fallar aunque el contenido sea conocido |
| `grounded_answering` | responder solo desde contexto suministrado con fidelidad | RAG/Graph son proveedores de contexto; el modelo debe consumirlo |
| `constraint_reasoning` | satisfacer simultáneamente relaciones/restricciones explícitas | no debe inferirse de tamaño o etiqueta `reasoning` |
| `code_generation` | producir artefacto sintáctico/contractualmente válido | capacidad específica, pero no centro del dataset |
| `tool_protocol` | emitir envelope parsable o abstenerse cuando faltan parámetros | requisito de seguridad del Agent Loop, distinto de JSON genérico |

### 7.2 Propiedades baseline, no triggers de swap

- `instruction_following`: requisito transversal. Se evalúa mediante límites, formato exacto, ausencia de prosa y abstención. No es útil como categoría de ruteo porque todas las tareas la requieren.
- `general_language_response`: baseline de usabilidad, no trigger. No justifica por sí solo abandonar el modelo residente.

### 7.3 Categorías eliminadas o combinadas

- `general conversation`: baseline, no capability selectiva.
- `RAG` y `Graph`: combinados como `grounded_answering`; la tarea relacional puede requerir además `constraint_reasoning`.
- `extraction` y `structured output`: combinados como `structured_extraction`.
- `document-grounded`: no se separa de grounded answering.
- `Agent`: no es una capability única; se descompone en tool protocol + instruction following + capability gate operativo.
- `planning`, `analysis`, `architecture`, `tradeoffs`, `brainstorming`, `explanations`: etiquetas demasiado amplias/subjetivas; sus requisitos concretos deben mapearse a reasoning, summarization u otra condición observable.

### 7.4 Restricciones que no son capabilities

Context window, provider availability, memoria, latencia y estado local son constraints operacionales. No deben aparecer como si fueran habilidades cognitivas.

---

## 8. EVALUATION DATASET

Dataset versionado: `benchmarks/phase_1_2_dataset.json`.

- 12 casos.
- 2 casos por capability.
- 8/12 casos son trabajo cotidiano/profesional/documental/estructurado; 2/12 código; 2/12 protocolo de herramientas.
- Temperatura 0.0, `top_k=1`, mismo prompt y condición por modelo.
- PASS: todas las condiciones objetivas.
- PARTIAL: al menos una condición pasa y ninguna condición fatal falla.
- FAIL: ninguna condición pasa o falla una condición fatal.
- BLOCKED: error técnico o ejecución no segura.

| ID | Capability | Condición central |
|---|---|---|
| SUM-01 | summarization | exactamente 3 viñetas + cuatro hechos |
| SUM-02 | summarization | ≤35 palabras + responsable, fecha, API y sin placeholders |
| EXT-01 | structured extraction | JSON válido + cinco campos exactos |
| EXT-02 | structured extraction | array JSON exacto y ordenado |
| GRD-01 | grounded answering | código exacto desde contexto |
| GRD-02 | grounded answering | cadena relacional exacta |
| REA-01 | constraint reasoning | orden único exacto |
| REA-02 | constraint reasoning | proveedor único bajo dos constraints |
| COD-01 | code generation | AST de función, sin imports, deduplicación ordenada, strip/lower |
| COD-02 | code generation | contrato SQL completo y solo consulta |
| TOL-01 | tool protocol | envelope JSON con capability/action/params exactos |
| TOL-02 | tool protocol | abstención exacta por parámetro faltante |

Se corrigieron antes de congelar resultados dos defectos detectados al revisar evidencia: rechazo indebido de `HAVING total_paid` y aceptación de placeholders inventados. Las respuestas capturadas se revaluaron offline; no se repitió inferencia ni se alteró texto generado.

---

## 9. MODEL EVIDENCE MATRIX

Agregación por capability:

- PASS: ambos casos PASS.
- PARTIAL: existe al menos un PASS/PARTIAL pero no ambos PASS.
- FAIL: ambos casos FAIL.
- BLOCKED: no se ejecutó por restricción operacional.

| Capability | Gemma E2B | OLMoE | Qwen1.5 MoE | Gemma E4B |
|---|---|---|---|---|
| Summarization | **PARTIAL** | **FAIL** | **PARTIAL** | **BLOCKED** |
| Structured extraction | **PASS** | **PARTIAL** | **FAIL** | **BLOCKED** |
| Grounded answering | **PASS** | **FAIL** | **FAIL** | **BLOCKED** |
| Constraint reasoning | **PARTIAL** | **FAIL** | **FAIL** | **BLOCKED** |
| Code generation | **PASS** | **FAIL** | **PARTIAL** | **BLOCKED** |
| Tool protocol | **PASS** | **FAIL** | **FAIL** | **BLOCKED** |

Totales por caso:

| Modelo | PASS | PARTIAL | FAIL | BLOCKED |
|---|---:|---:|---:|---:|
| Gemma E2B | 10 | 1 | 1 | 0 |
| OLMoE | 1 | 0 | 11 | 0 |
| Qwen1.5 MoE | 1 | 1 | 10 | 0 |
| Gemma E4B | 0 | 0 | 0 | 12 |

Evidencia breve destacada:

- E2B produjo ambos JSON exactos, la cadena Graph, Python estructuralmente válido, SQL válido y envelope de herramienta. Falló REA-02 al repetir literalmente `PROVEEDOR X`; SUM-01 omitió/distor­sionó una condición factual.
- OLMoE pasó EXT-01. En otros casos añadió prosa, inventó datos, ignoró formatos exactos o respondió incorrectamente la relación Alba/Beta/Gamma.
- Qwen mostró repetición extensa de `You are a helpful assistant` bajo el provider/configuración local. COD-02 sí cumplió el contrato SQL; otros casos fallaron formato o contenido.
- E4B no recibió atribuciones cognitivas. `BLOCKED` significa ausencia de prueba segura actual, no incapacidad universal.

Los resultados están ligados a estos artefactos, providers, configuración, dataset y máquina. No son rankings universales.

---

## 10. OPERATIONAL EVIDENCE

### 10.1 CURRENT_MEASURED — 2026-09-16

TTFT es end-to-end desde `EngineManager.generate_stream`, por lo que el primer caso incluye carga/provider startup. Warm es la mediana de los 11 casos posteriores.

| Modelo/provider | Cold TTFT | Cold elapsed | Warm TTFT mediana (rango) | Warm elapsed mediana | Warm tok/s provider | VRAM máx. observada | RAM disponible mínima | Estado |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| E2B / LiteRT embedded | 8.107 s | 10.554 s | 0.533 s (0.486-0.576) | 1.654 s | no expuesto | 3610 MB | 7754 MB | HEALTHY RESIDENT; reclaim Dawn diferido |
| OLMoE / llama.cpp | 77.117 s | 82.512 s | 1.045 s (0.807-1.196) | 2.136 s | 28.25 mediana (15.70-37.75) | 2671 MB | 4122 MB | FUNCTIONAL; cold actual alto |
| Qwen / llama.cpp | 110.280 s | 115.996 s | 2.232 s (1.715-2.744) | 4.844 s | 12.40 mediana (5.52-15.34) | 3907 MB | 377 MB | DEGRADED / CRITICAL MEMORY PRESSURE |
| E4B / LiteRT CLI | no ejecutado | no ejecutado | no ejecutado | no ejecutado | no ejecutado | no ejecutado | no ejecutado | BLOCKED / OPERATIONAL CONSTRAINT |

Observaciones:

- E2B dejó 3610 MB reportados dentro del proceso después de `engine.stop()`, coherente con la limitación Dawn/WebGPU ya documentada. Al finalizar el proceso, la VRAM volvió a 0 MB.
- llama.cpp liberó VRAM al finalizar cada suite; no quedaron `llama-server.exe` huérfanos.
- Qwen llegó a 49 MB de VRAM libre y 377 MB de RAM disponible mínima. Aunque completó, no es un perfil seguro para recomendación automática.
- OLMoE tuvo mejor costo warm que Qwen, pero su calidad fue inferior en este dataset. **FAST != CAPABLE.**

### 10.2 HISTORICAL_MEASURED

| Modelo | Evidencia histórica | Fuente |
|---|---|---|
| OLMoE | cold TTFT 10.6 s; warm 265-709 ms; 58.3-59.9 tok/s | `moe_poc/data/p2_ui_model_benchmark.json` |
| Qwen | cold TTFT 52.1 s; warm promedio 4.52 s; 14.9-22.1 tok/s en datasets previos | `p1_benchmark_results.json`, `p2_ui_model_benchmark.json` |
| E2B | ~15-25 tok/s | logs históricos citados por 1.1 |
| E4B | ~180 s y presión de memoria | forensics 0.2C.1 / auditoría 1.1 |

La diferencia grande entre OLMoE histórico y actual impide sobrescribir silenciosamente datos. Ambos quedan etiquetados por separado.

---

## 11. TRANSITION COST MATRIX

Solo se incluyen tiempos persistidos/documentados. La regresión física actual confirmó el ciclo, pero el test no imprime sus variables internas de tiempo, por lo que no se inventan tiempos nuevos.

| FROM → TO | Costo | Evidencia | Estado |
|---|---:|---|---|
| E2B → E2B (`chat`↔`code`) | no reload físico | I3 + tests de alias/residency | MEASURED CONTRACT |
| E2B → OLMoE | ~4.1 s | logs Phase 0 citados en auditoría 1.1 | HISTORICAL_MEASURED |
| OLMoE → E2B | ~3.8 s | logs Phase 0 citados en auditoría 1.1 | HISTORICAL_MEASURED |
| E2B → E4B | ~180 s | forensics 0.2C.1 | HISTORICAL_MEASURED / DEGRADED |
| E2B → Qwen | — | sin transición pareada persistida | UNVERIFIED |
| Qwen → E2B | — | sin transición pareada persistida | UNVERIFIED |
| OLMoE ↔ Qwen | — | no se ejecutó solo para completar tabla | UNVERIFIED |
| E4B ↔ OLMoE/Qwen | — | riesgo operacional sin beneficio para 1.2 | BLOCKED |

Los cold TTFT actuales no se convierten en costos de transición pareada; representan otra métrica.

---

## 12. SMART ROUTER ACCURACY AUDIT

Se ejecutaron los 12 prompts sin modificar keywords. `split()` literal hace que puntuación y signos impidan varias coincidencias; las listas son principalmente inglesas.

| Caso | Requirement real | Scores R/C | Resultado | Evaluación |
|---|---|---:|---|---|
| SUM-01 | summarization | 0/0 | chat | correct/neutral |
| SUM-02 | summarization | 1/1 (`plan`/`api`) | code | misleading: false coding |
| EXT-01 | structured extraction | 0/1 (`json`) | code | misleading: JSON ≠ coding |
| EXT-02 | structured extraction | 0/1 (`json`) | code | misleading: JSON ≠ coding |
| GRD-01 | grounded answering | 0/0 | chat | neutral; grounding viene del coordinator |
| GRD-02 | grounded + relational | 0/0 | chat | misleading: requisito relacional invisible |
| REA-01 | constraint reasoning | 0/0 | chat | misleading: false negative reasoning |
| REA-02 | constraint reasoning | 0/0 | chat | misleading: false negative reasoning |
| COD-01 | code generation | 0/1 (`python`) | code | correct |
| COD-02 | code generation | 0/0 | chat | misleading: `SQL.` no coincide |
| TOL-01 | tool protocol | 0/1 (`json`) | code | misleading: detecta formato, no necesidad tool |
| TOL-02 | abstención tool | 0/0 | chat | neutral/correct |

Resumen:

- 2 correctos claros, 2 neutrales, 8 misleading.
- 4 falsos `code` por palabras de formato/infraestructura.
- 3 falsos negativos relevantes (dos reasoning, un SQL).
- 0 rutas a `reasoning`/E4B en este dataset, no por suficiencia sino por ausencia de matches.
- `chat` y `code` son la misma identidad física, de modo que los falsos code no causan swap, pero sí cambian prompt family y capability gate.
- SmartRouter no puede seleccionar ni comparar OLMoE/Qwen y desconoce estado/costo.

Reutilizable: override manual, API `(model_id, system_prompt)` y fallback determinista. No reutilizable como fuente de capability verificada.

---

## 13. SKILL `recommended_model` ANALYSIS

Estado actual:

- `recommended_model` existe en `SkillSpec`, API y factory.
- Default: `code`.
- Se persiste, edita y muestra en propuestas.
- No existe consumidor que lo pase al SmartRouter/EngineManager para selección productiva.
- Por tanto es **DECLARED / ADVISORY-METADATA / CURRENTLY IGNORED FOR ROUTING**.

`requested_capabilities` ya significa scopes operacionales (`documents.read`, etc.). Reutilizar ese mismo nombre para capacidades cognitivas crearía colisión semántica.

Propuesta conceptual para 1.3, sin implementar:

- mantener scopes operacionales separados;
- reemplazar gradualmente el significado de `recommended_model` por una señal como `model_requirements: [structured_extraction, tool_protocol]`, o mapearla internamente sin cambiar schema todavía;
- tratar la señal de la skill como **advisory fuerte**, no authoritative;
- mantener authoritative solamente el override explícito del usuario y los límites de seguridad/provider;
- si la skill no declara requisitos, inferencia conservadora + inercia del residente;
- no permitir que una skill fuerce un modelo DEGRADED/BLOCKED.

La skill conoce mejor la semántica de la tarea que keywords superficiales, pero puede quedar desactualizada o ejecutarse en otra máquina; por eso no debe ser autoridad absoluta.

---

## 14. SUFFICIENCY CONTRACT PROPOSAL

### 14.1 Datos mínimos

1. `task_requirements`: subconjunto de las seis capabilities, más qualifiers objetivos.
2. `physical_model_evidence`: artifact + provider + dataset version + estado PASS/PARTIAL/FAIL/BLOCKED.
3. `operational_constraints`: contexto requerido, provider disponible, memoria y estado local.
4. `logical_role_overlay`: prompt family, model type, capability gate y skill scopes.
5. `current_residency`: identidad física activa y costo conocido de transición.

### 14.2 Regla mínima

`CURRENT_MODEL_SUFFICIENT` solo si se cumplen todas:

1. cada capability requerida está **PASS** para la identidad física/provider medidos; PARTIAL no se promociona silenciosamente a PASS;
2. el contexto requerido cabe en el límite efectivo configurado/medido;
3. el provider está disponible y su estado local no es BLOCKED/DEGRADED para la operación solicitada;
4. si hay herramientas, el rol lógico abre el capability gate bajo la skill y el modelo cumple `tool_protocol`;
5. no existe una restricción fatal conocida de memoria/lifecycle.

Si el actual es suficiente: **KEEP CURRENT**. La residencia produce inercia decisiva, no bonus numérico.

Si no es suficiente, solo existe candidato justificable cuando:

- cubre en PASS todas las capabilities faltantes;
- es operacionalmente viable en esta máquina;
- no viola gates/permissions;
- el costo de transición es medido o se declara explícitamente `UNKNOWN`;
- el usuario conserva la decisión final.

Si ningún candidato cumple, el resultado correcto es `NO VERIFIED CANDIDATE`, no recomendar el modelo más grande.

### 14.3 Aplicación al dataset actual

- E2B es suficiente para structured extraction, grounded answering, code generation y tool protocol bajo estos casos.
- E2B no queda verificado plenamente para summarization ni constraint reasoning; es PARTIAL.
- No existe otro modelo local actualmente verificado como PASS para cubrir esas brechas.
- Por tanto, los datos actuales favorecen residencia E2B y declaración explícita de limitación; no justifican swap automático.

---

## 15. STATIC VS MEASURED CONTRACT

Esquema conceptual mínimo:

```text
StaticModelFacts
  physical_artifact
  format
  architecture_family
  quantization_declared
  provider_required
  configured_context_limit

MeasuredModelProfile
  machine_fingerprint
  artifact + provider
  dataset_version
  capability -> PASS|PARTIAL|FAIL|BLOCKED
  cold/warm metrics
  memory observations
  operational_status
  timestamp
  evidence_source = CURRENT_MEASURED|HISTORICAL_MEASURED
```

Reglas:

- nunca almacenar `DEGRADED` como hecho universal del modelo;
- no mezclar providers al comparar métricas;
- invalidar/revisar evidencia si cambia artefacto, provider, configuración relevante o máquina;
- no inferir calidad desde tok/s, parámetros, MoE/dense o cuantización;
- conservar historical/current como series distintas.

---

## 16. AGENT LOOP COMPATIBILITY

Dependencias verificadas:

- `model_type` abre/cierra capability gate en `PureCoordinator`.
- `chat/general` tiene gate off.
- `coding`, `reasoning`, `moe`, `moe_research` usan `on_if_skill`.
- el parser acepta JSON raw o fenced `json_call/json`, valida capability/action/params y whitelist `documents|rag|git|terminal`.
- `AgentControlRunner` ejecuta máximo 3 pasos, respeta approval y detiene en pending/errores.

Implicaciones:

1. `tool_protocol PASS` físico no basta: el rol y la skill deben abrir el gate.
2. `chat` y `code` comparten E2B, pero no son intercambiables operacionalmente para tools.
3. Las nuevas capabilities cognitivas no deben reutilizar IDs de runtime tools.
4. Una futura política no debe ejecutar herramientas, abrir gates ni modificar mensajes; solo podría producir una recomendación explicable.
5. No se modificó Agent Loop.

---

## 17. PRE-MORTEM

| Riesgo | Manifestación probable | Mitigación contractual |
|---|---|---|
| Capability explosion | una etiqueta por cada prompt | seis dimensiones + qualifiers; exigir decisión útil |
| Etiquetas subjetivas | “deep”, “excellent”, “smart” | solo propiedades observables |
| Benchmark overfitting | prompts memorizados/optimizados | pocos casos reales, versionados; ampliar solo por gap concreto |
| Prompts artificiales | formato sin relación con uso real | documentos, PyME, extracción, constraints y tool envelope real |
| Bigger = better | E4B/Qwen recomendados por tamaño | matriz conductual + estado local |
| MoE = better | inferir capacidad de arquitectura | OLMoE/Qwen muestran que no se sostiene localmente |
| Swaps innecesarios | salir de E2B aunque ya pasa | KEEP si requisitos ⊆ PASS y operación viable |
| Ignorar residencia | thrashing | inercia como regla, no score |
| Logical = physical | duplicar chat/code | evidencia por identidad física + overlay lógico |
| Static = measured | llamar universal a presión local | perfiles separados y fingerprint de máquina |
| Una máquina = verdad universal | publicar FAIL universal | lenguaje “en perfil medido” |
| Scoring prematuro | números sin calibración | estados discretos con evidencia |
| Romper Agent Loop | advisor abre tools/cambia loop | frontera estricta: recomendación pura |
| Segundo runtime paralelo | catálogo carga/ejecuta modelos | EngineManager sigue único ejecutor |
| Evaluador defectuoso | false PASS/FAIL | revisar outputs, reglas versionadas; correcciones trazables |
| Datos históricos obsoletos | asumir OLMoE cold 10.6 s | current e historical separados |

---

## 18. FIVE-STEP ANALYSIS

### 18.1 QUESTION REQUIREMENTS

La pregunta útil es si los requisitos observables de una tarea están cubiertos por evidencia del modelo físico bajo el provider/máquina actuales, no cuál modelo “es mejor”.

### 18.2 DELETE

- eliminar del contrato de decisión etiquetas amplias sin test (`planning`, `architecture`, `analysis`);
- no usar parámetros, tok/s o MoE como proxy;
- no duplicar chat/code;
- no exigir matriz completa de transiciones peligrosas.

### 18.3 SIMPLIFY

- seis capabilities;
- PASS/PARTIAL/FAIL/BLOCKED;
- constraints operacionales aparte;
- decisión futura binaria: suficiente/no suficiente, y candidato solo si existe evidencia.

### 18.4 ACCELERATE

- reutilizar evidencia versionada por artifact/provider/machine;
- no benchmarkear en cada request;
- no cargar un modelo para clasificar el prompt;
- consultar tabla en memoria en una fase posterior.

### 18.5 AUTOMATE

Automatizable en fases futuras: ingestión de resultados auditados y registro de transiciones observadas. No automatizar ahora benchmarking de fondo, swaps ni scoring.

---

## 19. GAPS / UNVERIFIED AREAS

- E4B no tiene evidencia cognitiva actual; 12 celdas BLOCKED por constraint operacional.
- Solo hay dos casos por capability; suficiente para contrato mínimo, no para afirmación amplia de calidad.
- No se midió long-context; contexto es constraint, pero faltan pruebas cerca de 2048 tokens.
- No se evaluaron idiomas múltiples.
- No se evaluó conversación abierta porque no es trigger; baseline general queda sin matriz específica.
- No hay costos pareados actuales para Qwen ni transiciones OLMoE↔Qwen.
- La semántica SQL depende del dialecto; el caso acepta tanto `HAVING SUM(amount)` como alias `total_paid`.
- La validación Python es AST/contrato estático; no ejecuta código generado por seguridad.
- Las salidas repetitivas de Qwen pueden involucrar interacción artifact/template/provider. Se registran como comportamiento local end-to-end, no como propiedad universal.
- No existe fingerprint persistido de procesos externos concurrentes; memoria es snapshot local.

Estos gaps no bloquean diseñar una política mínima conservadora. Sí bloquean recomendaciones positivas hacia E4B/Qwen y generalizaciones universales.

---

## 20. PHASE 0 REGRESSION RESULT

Python usado únicamente para tests:

```text
C:\Users\rva10\AppData\Local\Python\pythoncore-3.14-64\python.exe
```

Runtime productivo preservado:

```text
D:\as-core\venv\Scripts\python.exe
```

Comando antes y después de instrumentación:

```powershell
C:\Users\rva10\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pytest tests/test_model_residency.py tests/test_model_transitions_contract.py tests/test_cross_provider_physical.py tests/test_lifecycle_hardening.py -q
```

| Momento | Resultado | Duración | Clasificación |
|---|---|---:|---|
| Antes | 19 passed, 1 warning | 49.10 s | PASS |
| Después | 19 passed, 1 warning | 51.92 s | PASS |

Warning en ambos: `PytestConfigWarning: Unknown config option: asyncio_mode`, porque el PythonCore tiene pytest pero no carga el plugin opcional. No causó skips/fallos y no fue introducido por 1.2.

Resultado: **0 regresiones atribuibles a Fase 1.2**.

---

## 21. FILES MODIFIED

Todos son audit-only:

| Archivo | Propósito | Producción |
|---|---|---|
| `benchmarks/phase_1_2_dataset.json` | dataset de 12 casos y condiciones objetivas | NO |
| `benchmarks/phase_1_2_harness.py` | runner aislado, evaluadores, métricas y audit de SmartRouter | NO |
| `benchmarks/results/phase_1_2_e2b.json` | evidencia raw/current E2B | NO |
| `benchmarks/results/phase_1_2_olmoe.json` | evidencia raw/current OLMoE | NO |
| `benchmarks/results/phase_1_2_qwen.json` | evidencia raw/current Qwen | NO |
| `docs/MODEL_CAPABILITY_EVIDENCE_FASE_1.2.md` | informe principal | NO |

Archivos productivos modificados: **0**.

Comandos de medición:

```powershell
C:\Users\rva10\AppData\Local\Python\pythoncore-3.14-64\python.exe benchmarks\phase_1_2_harness.py --model e2b --output benchmarks\results\phase_1_2_e2b.json
C:\Users\rva10\AppData\Local\Python\pythoncore-3.14-64\python.exe benchmarks\phase_1_2_harness.py --model olmoe --output benchmarks\results\phase_1_2_olmoe.json
C:\Users\rva10\AppData\Local\Python\pythoncore-3.14-64\python.exe benchmarks\phase_1_2_harness.py --model qwen --output benchmarks\results\phase_1_2_qwen.json
```

Validaciones de instrumentación: `json.tool`, `py_compile` y revisión de resultados/respuestas.

---

## 22. GIT STATUS

Al cierre esperado, el working tree contiene únicamente los seis archivos audit-only enumerados arriba como nuevos/no trackeados. No existen cambios en EngineManager, providers, SmartRouter, coordinator, Agent Loop, Skills productivas, RAG, Graph, Memory ni UI.

El warning de acceso a `C:\Users\rva10\.config\git\ignore` es externo al repositorio y no impide inspeccionar el estado.

---

## 23. FINAL VERDICT

**GREEN / READY FOR 1.3.**

Fundamento:

1. contrato mínimo discreto y explicable;
2. dataset reproducible con condiciones objetivas;
3. evidencia actual de tres modelos seguros y bloqueo honesto de E4B;
4. evidencia suficiente para concluir que E2B residente cubre hoy más requisitos verificados que los candidatos medidos;
5. costos/estados operacionales separados de calidad;
6. router actual cuantificado y no apto como fuente de requirements;
7. contrato de suficiencia propuesto sin scoring;
8. 19/19 regresiones antes y después.

GREEN no autoriza auto-swap ni implica que E2B sea universalmente superior. Autoriza diseñar una política conservadora basada en evidencia.

---

## 24. RECOMMENDATION FOR PHASE 1.3

Para revisión humana, la siguiente fase debería limitarse a diseñar —no necesariamente integrar— una política pura con estas entradas/salidas:

```text
Input:
  task_requirements
  current_physical_identity
  current_logical_role
  verified_evidence_profile
  operational_machine_status
  known_transition_cost

Output:
  CURRENT_MODEL_SUFFICIENT
  or
  NO_VERIFIED_CANDIDATE(reason)
  or
  SUGGEST_CANDIDATE(target, reason, measured_cost|UNKNOWN)
```

Prioridades:

1. preservar `KEEP CURRENT` cuando el residente cubre requisitos;
2. separar requisitos cognitivos de tool scopes y model type;
3. introducir evidencia por identidad física con overlay lógico;
4. excluir candidatos BLOCKED/DEGRADED;
5. mantener override manual y human-in-the-loop;
6. no agregar scoring, auto-swap, ML classifier, scheduler ni background benchmark.

**STOP. No iniciar Fase 1.3 automáticamente.**
