# ============================================================
# AS-CORE — FASE 1 / SUBFASE 1.4C
# SINGLE RESIDENT MODEL POLICY (SRMP)
# FINAL VALIDATION + FREEZE REPORT
# ============================================================

## 1. STATUS
**GREEN / FROZEN**

---

## 2. DATE
- **Date:** 2026-09-17
- **Timezone:** UTC-3 (America/Argentina/Buenos_Aires)

---

## 3. HEAD
- **Git Commit SHA:** `7b9191c534cac169f31681a8d38457bb43309986` (ahead of origin/main by 6 commits)

---

## 4. BASELINE
- **Phase 0 Contracts (0.2A–0.2D):** FROZEN & GREEN
  - 0.2A Model Residency: GREEN
  - 0.2B Physical Identity: GREEN
  - 0.2C Generic Physical Model Transition: GREEN
  - 0.2D Runtime Lifecycle & Multi-Provider: GREEN
- **Phase 1.1 Discovery & Audit:** GREEN / FROZEN (`docs/MODEL_CAPABILITY_DISCOVERY_FASE_1.1.md`)
- **Phase 1.2 Empirical Evidence:** GREEN / FROZEN (`docs/MODEL_CAPABILITY_EVIDENCE_FASE_1.2.md`)
- **Phase 1.3 Architectural Decision:** APPROVED (`docs/SINGLE_RESIDENT_MODEL_POLICY_FASE_1.3.md`)
- **Phase 1.4A Contractual RED Suite & Implementation Plan:** APPROVED (`docs/SINGLE_RESIDENT_MODEL_IMPLEMENTATION_PLAN_FASE_1.4.md`)
- **Phase 1.4B Surgical Implementation:** COMPLETED (All 18 RED converted to GREEN)

---

## 5. GIT STATUS BEFORE
```text
On branch main
Your branch is ahead of 'origin/main' by 6 commits.
Changes not staged for commit:
	modified:   api/main.py
	modified:   api/models.py
	modified:   api/routes.py
	modified:   router/rules.py
	modified:   router/smart_router.py
	modified:   runtime/coordinator/manager.py
	modified:   runtime/coordinator/models.py
	modified:   runtime/coordinator/prompts.py
	modified:   runtime/skills/models.py
	modified:   ui/app.js
	modified:   ui/index.html
Untracked files:
	benchmarks/phase_1_2_dataset.json
	benchmarks/phase_1_2_harness.py
	benchmarks/results/
	docs/MODEL_CAPABILITY_EVIDENCE_FASE_1.2.md
	docs/SINGLE_RESIDENT_MODEL_IMPLEMENTATION_PLAN_FASE_1.4.md
	docs/SINGLE_RESIDENT_MODEL_POLICY_FASE_1.3.md
	runtime/coordinator/profiles.py
	tests/test_single_resident_policy_contracts.py
```
- **Frozen Invariant Check:**
  - `core/engine.py`: **0 changes** (UNTOUCHED / FROZEN)
  - `providers/*`: **0 changes** (UNTOUCHED / FROZEN)

---

## 6. FILES INSPECTED
1. `core/engine.py` (Frozen EngineManager)
2. `providers/registry.py` (Frozen ProviderRegistry)
3. `providers/litert_provider.py` (Frozen LiteRT Provider)
4. `providers/litert_cli_provider.py` (Frozen LiteRT CLI Provider)
5. `providers/llamacpp_provider.py` (Frozen LlamaCPP Provider)
6. `runtime/coordinator/manager.py` (CoordinatorManager & Capability Gate)
7. `runtime/coordinator/profiles.py` (Pure Cognitive Profile Resolver)
8. `runtime/coordinator/prompts.py` (Profile prompt templates)
9. `runtime/skills/models.py` (SkillManifest & metadata compatibility)
10. `router/smart_router.py` (SmartRouter authority and routing rules)
11. `router/rules.py` (Routing rule keywords)
12. `api/main.py` (App state initialization: `selected_model`)
13. `api/models.py` (ChatCompletionRequest, StatusResponse)
14. `api/routes.py` (Routes, model select endpoint, status endpoint)
15. `ui/index.html` (Decoupled Model & Profile dropdowns)
16. `ui/app.js` (UI state management & telemetry polling)

---

## 7. 1.4 CONTRACT RESULT
- **Execution Command:** `python -m pytest tests/test_single_resident_policy_contracts.py -v`
- **Result:** **20/20 PASSED** in 4.76s.
- **Contract Breakdown:**
  - `test_r01_default_model_remains_resident_across_profile_changes`: PASSED
  - `test_r02_balanced_to_code_causes_zero_physical_reload`: PASSED
  - `test_r03_code_to_creative_causes_zero_physical_reload`: PASSED
  - `test_r04_auto_profile_never_changes_physical_model`: PASSED
  - `test_r05_explicit_user_model_change_uses_existing_transition_contract`: PASSED
  - `test_r06_after_explicit_model_change_new_model_remains_selected_for_subsequent_profiles`: PASSED
  - `test_r07_core_never_automatically_reverts_to_default_because_of_prompt_skill_capability_or_router`: PASSED
  - `test_r08_physical_aliases_preserve_identity_and_do_not_reload`: PASSED
  - `test_r09_phase_0_invariants_remain_green`: PASSED
  - `test_r10_unknown_blocked_provider_unavailable_model_selection_fails_truthfully`: PASSED
  - `test_r11_explicit_profile_override_deterministically_dominates_auto`: PASSED
  - `test_r12_no_hidden_physical_model_recommendation_path_remains_active`: PASSED
  - `test_r13_selected_active_and_physical_state_are_not_collapsed`: PASSED
  - `test_r14_restart_initialization_returns_to_documented_default_for_process_scoped_policy`: PASSED
  - `test_r15_code_preserves_software_prompt_and_precise_without_physical_alias_code`: PASSED
  - `test_r16_structured_extraction_does_not_become_code_merely_because_json_requested`: PASSED
  - `test_r17_tools_controlled_by_skill_not_physical_model_identity`: PASSED
  - `test_r18_ui_api_contract_separates_model_selection_from_profile_selection`: PASSED
  - `test_r19_api_and_ui_share_the_same_profile_fallback_semantics`: PASSED
  - `test_r20_profile_change_during_active_inference_never_requests_physical_transition`: PASSED

---

## 8. PHASE 0 RESULT
- **Execution Command:** `python -m pytest tests/test_model_residency.py tests/test_model_transitions_contract.py tests/test_cross_provider_physical.py tests/test_lifecycle_hardening.py -v`
- **Result:** **19 PASSED, 0 FAILED** (49.56s)
  - `tests/test_model_residency.py`: 5 passed
  - `tests/test_model_transitions_contract.py`: 5 passed
  - `tests/test_cross_provider_physical.py`: 3 passed
  - `tests/test_lifecycle_hardening.py`: 6 passed
- **Verdict:** Phase 0 baseline remains 100% GREEN and uncompromised.

---

## 9. AGENT LOOP RESULT
- **Execution Command:** `python -m pytest tests/test_agent_loop_hardening.py tests/test_p2_ui_model_validation.py -v`
- **Result:** **10 PASSED, 3 SKIPPED, 0 FAILED** (12.93s)
  - `test_agent_loop_hardening.py`: 9/9 passed
  - `test_p2_ui_model_validation.py`: 1 passed, 3 skipped (pre-existing mock skips)

---

## 10. SKILLS RESULT
- **Execution Command:** `python -m pytest tests/test_skill_factory.py tests/test_skill_factory_api.py tests/test_skill_factory_lifecycle.py -v`
- **Result:** **25/25 PASSED, 0 FAILED** (3.44s)
  - `test_skill_factory.py`: 10 passed
  - `test_skill_factory_api.py`: 7 passed
  - `test_skill_factory_lifecycle.py`: 8 passed

---

## 11. TOOL SECURITY AUDIT (R17)
- **Chain of Authority:**
  ```text
  Skill active
      ↓
  uses_capabilities (True)
      ↓
  KNOWN_CAPABILITY_IDS / Whitelist
      ↓
  Requested Scopes
      ↓
  User / Policy Approval
      ↓
  Parser Validation (schema check)
      ↓
  AgentControlRunner
      ↓
  Tool Execution
  ```
- **Audited Security Invariants:**
  - **A. CODE Profile + NO Skill Authorized:**
    - Profile resolver outputs `CODE`.
    - `manager.py`: `capability_gate_open` is strictly `False` because `active_skill` is None.
    - Tools are **CLOSED**; any capability invocation is blocked.
  - **B. BALANCED + Skill Authorized:**
    - Only capabilities explicitly declared in `skill.manifest.capabilities` and in `KNOWN_CAPABILITY_IDS` can be invoked.
  - **C. Physical Model Change:**
    - Does NOT grant, widen, or alter tool capabilities. Tool access is strictly bound to active skill manifests.
  - **D. Cognitive Profile Change:**
    - Does NOT alter capability gate state.
  - **E. Approval Gates:**
    - Manual approval requirements remain strictly enforced by the Agent Control Runner.
  - **F. Unknown Capabilities:**
    - Unconditionally rejected by the parser and whitelist validation.

---

## 12. recommended_model AUDIT
- **Audited File:** `runtime/skills/models.py`
- **Findings:**
  1. Historical skills containing `recommended_model` continue to load cleanly without parsing errors.
  2. Pydantic serialization/deserialization remains backward compatible.
  3. SkillLab and runtime APIs read skill manifests without disruption.
  4. Metadata is retained without crashing any consumer.
  5. **Physical Authority = ZERO:** `recommended_model` has zero authority over `InferenceRequest.model_id` or EngineManager residency.

---

## 13. SMARTROUTER AUTHORITY AUDIT
- **Call Sites:** Exactly 1 production call site in `api/routes.py:97`.
- **Authority Flow:**
  ```text
  HTTP Request (model, profile)
      ↓
  api/routes.py: resolve resident_model = app.state.selected_model
      ↓
  SmartRouter.route(prompt, resident_model=resident_model)
      ↓
  SmartRouter Output (routed_model == resident_model)
      ↓
  EngineManager (ZERO physical transition)
  ```
- **Physical Authority:** **NO (ZERO PHYSICAL AUTHORITY)**.
- **Classification:** Kept temporarily for task/profile hints; does not control model residency.

---

## 14. MODEL / PROFILE / PRESET / TASK CONTRACT
- **MODEL:** Physical artifact, provider, physical identity, and residency in VRAM/RAM.
- **PROFILE:** Cognitive working style (`AUTO`, `BALANCED`, `CREATIVE`, `CODE`) determining prompts and sampling hints.
- **PRESET:** Generation hyperparameters (temperature, top_p, max_tokens).
- **TASK PREPARATION:** Prompts, RAG, Graph, Memory, Skills, Tools, and constraints.
- **Contract Proof:** Changing PROFILE never changes MODEL.

---

## 15. SELECTED / ACTIVE / PHYSICAL CONTRACT
- **`selected_model`:** Control-plane preference set by user/operator (`"chat"`, `"olmoe"`, etc.).
- **`active_model`:** Logical model identifier currently held in EngineManager.
- **`active_physical_model`:** Canonical filesystem path / provider descriptor reported by `engine.active_physical_model`.
- **Contract Proof:** Neither API nor UI fabricates or collapses these distinct states.

---

## 16. PROVIDER TRUTH AUDIT
- **Initial Observation:** UI displayed `litert_cli` while E2B ran on `litert_embedded`.
- **Audit Classification:** **A. UI DISPLAY BUG**.
- **Root Cause:**
  - `ui/app.js` line 388 contained a hardcoded fallback: `data.provider || 'litert_cli'`.
  - Server SSE chunks did not include a `provider` field, triggering the fallback.
- **Minimal Surgical Fix Applied:**
  - Added `active_provider: Optional[str]` to `StatusResponse` in `api/models.py`.
  - Injected `status["active_provider"] = engine.registry.active_provider_id` in `api/routes.py:get_status`.
  - Updated `ui/app.js` to poll and render `data.active_provider`.
  - Provider implementation and EngineManager were **100% UNTOUCHED**.

---

## 17. E2B PHYSICAL TEST
- **Runtime Execution:** Tested via clean harness with physical residency tracking provider.
- **Logical Model:** `chat` (Gemma 3n E2B int4).
- **Physical Identity:** `physical_spy::D:\as-core\models\gemma\gemma-3n-E2B-it-int4.litertlm`.
- **Initial Load Count:** 1 load, 0 unloads.

---

## 18. BALANCED RESULT
- **Profile:** `BALANCED`
- **Resolved Profile:** `BALANCED`
- **Loads:** 0 | **Unloads:** 0 | **Transitions:** 0
- **Physical Identity:** Unchanged (`gemma-3n-E2B-it-int4.litertlm`).

---

## 19. CODE RESULT
- **Profile:** `CODE`
- **Resolved Profile:** `CODE`
- **Prompt Applied:** `SOFTWARE_PROMPT`
- **Loads:** 0 | **Unloads:** 0 | **Transitions:** 0
- **Physical Identity:** Unchanged (`gemma-3n-E2B-it-int4.litertlm`).

---

## 20. CREATIVE RESULT
- **Profile:** `CREATIVE`
- **Resolved Profile:** `CREATIVE`
- **Prompt Applied:** `CREATIVE_PROMPT`
- **Loads:** 0 | **Unloads:** 0 | **Transitions:** 0
- **Physical Identity:** Unchanged (`gemma-3n-E2B-it-int4.litertlm`).

---

## 21. AUTO RESULT
- Tested queries under `PROFILE = AUTO`:
  - A. General question: 0 transitions
  - B. Coding task: 0 transitions
  - C. JSON extraction: 0 transitions (NO physical code routing)
  - D. Reasoning task: 0 transitions (NEVER loads E4B)
- **Physical Model:** Remained `chat` across all queries.

---

## 22. E2B RESIDENCY PROOF
- **Sequence:** `BALANCED` → `CODE` → `CREATIVE` → `AUTO` (4 queries).
- **Loads Before:** 1 | **Loads After:** 1
- **Unloads Before:** 0 | **Unloads After:** 0
- **Physical Transitions:** Exactly 0.
- **Physical Identity:** Constant throughout.

---

## 23. EXPLICIT TRANSITION TEST
- **Trigger:** `POST /v1/models/select` with `{"model": "olmoe"}`
- **Selected Model Before:** `chat` | **After:** `olmoe`
- **Active Model Before:** `chat` | **After:** `olmoe`
- **Physical Transition Count:** Exactly 1 (1 unload of `chat`, 1 load of `olmoe`).
- **Physical Identity:** `physical_spy::D:\as-core\models\olmoe\olmoe-1b-7b.gguf`.

---

## 24. OLMOE RESIDENCY PROOF
- **Profile Sequence on OLMoE:** `BALANCED` → `CODE` → `CREATIVE` → `AUTO`
- **Reloads:** 0 | **Unloads:** 0 | **Transitions:** 0
- **Reversion to E2B:** NONE. OLMoE remains 100% resident across all profile changes.
- **Conclusion:** Single Resident Model Policy is model-agnostic.

---

## 25. INVALID MODEL TEST
- **Trigger:** `POST /v1/models/select` with `{"model": "completely_unregistered_model_xyz"}`
- **HTTP Response:** Truthful `404 Not Found`.
- **State Integrity:** `selected_model` unchanged, `active_model` unchanged, physical model unchanged.

---

## 26. BUSY CONTRACT
- Concurrency test: An explicit transition request submitted while inference is in progress is safely rejected by Busy Guard (`finish_reason='busy'`).
- The running generation completes safely on the resident model.
- EngineManager transition contract is preserved.

---

## 27. RESTART CONTRACT
- `selected_model` is process-scoped.
- On process start / restart, `app.state.selected_model` defaults to documented default `"chat"`.
- No hidden persistence layer was added.

---

## 28. BROADER REGRESSION
- **Suite Command:** `python -m pytest tests/test_single_resident_policy_contracts.py tests/test_deterministic_continuity.py tests/test_project_system.py tests/test_graph_runtime_integration.py tests/test_graph_contracts.py tests/test_skill_factory.py tests/test_skill_factory_api.py tests/test_skill_factory_lifecycle.py tests/test_agent_loop_hardening.py tests/test_p2_ui_model_validation.py -v`
- **Result:** **107 PASSED, 3 SKIPPED, 0 FAILED** (16.57s).
- **Classification:**
  - 107 PASSED: 100% functional integrity.
  - 3 SKIPPED: Pre-existing mock skips in `test_p2_ui_model_validation.py`.
  - 0 REGRESSIONS.

---

## 29. QUALITY OBSERVATIONS
- **Cognitive Quality Observation:** Observed that factual multi-turn knowledge (e.g. Paraguay capital follow-ups) depends on context window management and grounding, not on physical residency.
- **Classification:** Non-SRMP cognitive evaluation item.

---

## 30. BUGS FOUND
1. **Provider Truth UI Display Bug:** `ui/app.js` defaulted to hardcoded `'litert_cli'` when SSE chunks lacked provider metadata, contradicting the real embedded provider.

---

## 31. MINIMAL FIXES APPLIED
1. **Truthful Provider Display:**
   - Updated `api/models.py` (`StatusResponse.active_provider`).
   - Updated `api/routes.py` (`status["active_provider"] = engine.registry.active_provider_id`).
   - Updated `ui/app.js` to poll and render truthful `active_provider`.

---

## 32. FILES MODIFIED
- `api/main.py`
- `api/models.py`
- `api/routes.py`
- `router/rules.py`
- `router/smart_router.py`
- `runtime/coordinator/manager.py`
- `runtime/coordinator/models.py`
- `runtime/coordinator/prompts.py`
- `runtime/skills/models.py`
- `ui/app.js`
- `ui/index.html`

---

## 33. FILES NOT MODIFIED (FROZEN)
- `core/engine.py` (**FROZEN**)
- `providers/registry.py` (**FROZEN**)
- `providers/litert_provider.py` (**FROZEN**)
- `providers/litert_cli_provider.py` (**FROZEN**)
- `providers/llamacpp_provider.py` (**FROZEN**)
- `runtime/graph/*` (**FROZEN**)
- `runtime/memory/*` (**FROZEN**)
- `runtime/rag/*` (**FROZEN**)

---

## 34. FINAL SRMP INVARIANTS
- **SRMP-I1:** Only explicit user/control-plane action may request physical model change.
- **SRMP-I2:** Profile changes never request physical transition.
- **SRMP-I3:** AUTO selects behavior, never physical model.
- **SRMP-I4:** `selected_model` is not physical truth.
- **SRMP-I5:** `active_physical_model` comes from runtime truth.
- **SRMP-I6:** SmartRouter has zero physical authority.
- **SRMP-I7:** Skills have zero physical model authority.
- **SRMP-I8:** `recommended_model` metadata cannot cause swap.
- **SRMP-I9:** Tool authorization is independent from physical model identity.
- **SRMP-I10:** Tool whitelist, scopes, approval, parser, and agent guards remain strictly enforced.
- **SRMP-I11:** Runtime remains multi-model capable.
- **SRMP-I12:** EngineManager transition contract remains unchanged.
- **SRMP-I13:** Manual model selection remains reversible.
- **SRMP-I14:** Selected model remains resident across `BALANCED` / `CODE` / `CREATIVE` / `AUTO`.
- **SRMP-I15:** Restart returns process-scoped selection to documented default.

---

## 35. REMAINING LIMITATIONS
1. Physical model transition requires explicit synchronous unload/load through EngineManager.
2. Selection preference is process-scoped and resets on process restart.

---

## 36. DEFERRED ITEMS
- ModelAdvisor
- Auto model recommendation
- Auto swap
- Model scoring
- Hysteresis & cooldown
- Multi-user scheduler
- Persistent model preference store
- SmartRouter complete deprecation/cleanup
- SkillSpec migration
- Context quality and grounding enhancements
- Cline integration

---

## 37. GIT DIFF SUMMARY
- **API:** Clean separation of model selection (`POST /v1/models/select`) and request profile parameter. Truthful provider status.
- **Router:** Removed `"json"` from coding trigger words. SmartRouter respects `resident_model` on AUTO. Zero physical authority.
- **Coordinator:** Pure deterministic profile resolution (`AUTO`, `BALANCED`, `CREATIVE`, `CODE`). Capability gate decoupled from model identity and coupled strictly to active skill manifest.
- **UI:** Visual and functional decoupling of Model selection from Cognitive Profile selection. Truthful telemetry display.

---

## 38. GIT STATUS AFTER
```text
On branch main
Your branch is ahead of 'origin/main' by 6 commits.
Changes not staged for commit:
	modified:   api/main.py
	modified:   api/models.py
	modified:   api/routes.py
	modified:   router/rules.py
	modified:   router/smart_router.py
	modified:   runtime/coordinator/manager.py
	modified:   runtime/coordinator/models.py
	modified:   runtime/coordinator/prompts.py
	runtime/skills/models.py
	ui/app.js
	ui/index.html
Untracked files:
	benchmarks/phase_1_2_dataset.json
	benchmarks/phase_1_2_harness.py
	benchmarks/results/
	docs/MODEL_CAPABILITY_EVIDENCE_FASE_1.2.md
	docs/SINGLE_RESIDENT_MODEL_IMPLEMENTATION_PLAN_FASE_1.4.md
	docs/SINGLE_RESIDENT_MODEL_POLICY_FASE_1.3.md
	docs/SINGLE_RESIDENT_MODEL_POLICY_FREEZE_FASE_1.4C.md
	runtime/coordinator/profiles.py
	tests/test_single_resident_policy_contracts.py
```

---

## 39. FINAL VERDICT
**GREEN — SRMP VALIDATED / FROZEN**

---

## 40. FREEZE DECLARATION
The Single Resident Model Policy (SRMP) implementation in AS-Core has satisfied all 20 contractual tests, 19 Phase 0 regression tests, all Agent Loop and Skill security tests, and 100% of physical residency validation checks.

Zero physical reloads occur across `BALANCED`, `CODE`, `CREATIVE`, and `AUTO` profiles. Tool capability gating remains strictly enforced through skill manifests without dependence on model identity. The runtime provider state is truthful.

**SINGLE RESIDENT MODEL POLICY IS HEREBY DECLARED FROZEN.**
