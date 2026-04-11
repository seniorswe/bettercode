import json

import pytest

from bettercode.router import selector


@pytest.fixture(autouse=True)
def _local_preprocess_enabled(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "tiny")


def test_selector_status_reports_missing_ollama(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector._ollama_command", lambda: None)

    status = selector.selector_status()

    assert status["installed"] is False
    assert status["running"] is False
    assert status["model_ready"] is False


def test_selector_status_keeps_local_model_choices_visible_when_off(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector._ollama_command", lambda: "/usr/bin/ollama")
    monkeypatch.setattr("bettercode.router.selector._ollama_running", lambda: False)
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "off")
    monkeypatch.setattr(
        "bettercode.router.selector.local_preprocess_candidates",
        lambda mode=None: [{"id": "qwen2.5-coder:1.5b", "label": "Low Mem (1.0 GB)", "installed": True}],
    )

    status = selector.selector_status()

    assert status["mode"] == "off"
    assert status["available_local_models"] == [{"id": "qwen2.5-coder:1.5b", "label": "Low Mem (1.0 GB)", "installed": True}]


def test_require_selector_runtime_raises_when_ollama_missing(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    try:
        selector.require_selector_runtime()
    except RuntimeError as exc:
        assert "requires Ollama" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_require_selector_runtime_returns_ready_status(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })

    status = selector.require_selector_runtime()

    assert status["running"] is True
    assert status["model_ready"] is True


def test_select_best_model_falls_back_without_local_runtime(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Debug a failing regression across multiple files.",
        ["codex/gpt-5.4@low", "codex/gpt-5.4@high"],
        "Changed files: app.py, router.py\nRecent history: failing tests",
    )

    assert selection["selected_model"] == "codex/gpt-5.4@high"
    assert selection["source"] == "heuristic"


def test_select_best_model_uses_low_tier_only_for_tiny_requests(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Summarize this function briefly.",
        ["codex/gpt-5.4@low", "codex/gpt-5.4@high"],
        "",
    )

    assert selection["selected_model"] == "codex/gpt-5.4@low"
    assert selection["source"] == "heuristic"


def test_select_best_model_prefers_balanced_tier_for_standard_work(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Implement the project add menu flow.",
        [
            {"id": "codex/gpt-5.4@low", "label": "gpt-5.4 / Low", "cost_tier": "low", "speed_tier": "high", "capability_tier": "medium", "reasoning_effort": "low"},
            {"id": "codex/gpt-5.4", "label": "gpt-5.4", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium"},
            {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "reasoning_effort": "high"},
        ],
        "Changed files: app.js, index.html",
    )

    assert selection["selected_model"] == "codex/gpt-5.4"
    assert selection["source"] == "heuristic"


def test_select_best_model_respects_cheaper_preference_for_standard_work(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })
    monkeypatch.setattr("bettercode.router.selector.get_auto_model_preference", lambda: "cheaper")

    selection = selector.select_best_model(
        "Implement the project add menu flow.",
        [
            {"id": "codex/gpt-5.4@low", "label": "gpt-5.4 / Low", "cost_tier": "low", "speed_tier": "high", "capability_tier": "medium", "reasoning_effort": "low"},
            {"id": "codex/gpt-5.4", "label": "gpt-5.4", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium"},
            {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "reasoning_effort": "high"},
        ],
        "Changed files: app.js, index.html",
    )

    assert selection["selected_model"] == "codex/gpt-5.4@low"
    assert selection["source"] == "heuristic"


def test_select_best_model_avoids_preview_when_stable_fit_is_similar(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Implement the settings form cleanup.",
        [
            {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "cost_tier": "low", "speed_tier": "high", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "low-latency reasoning"]},
            {"id": "gemini/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "preview", "suggested_uses": ["deep reasoning", "complex coding"]},
        ],
        "Changed files: app.js, styles.css",
    )

    assert selection["selected_model"] == "gemini/gemini-2.5-flash"
    assert selection["source"] == "heuristic"


def test_select_best_model_prefers_large_context_for_large_context_tasks(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    large_context = "Recent history:\n" + ("A" * 12000)
    selection = selector.select_best_model(
        "Review the current implementation and propose a safe refactor.",
        [
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "context_window": 2000, "stability": "stable", "suggested_uses": ["general coding", "balanced implementation"]},
            {"id": "claude/claude-opus-4-1", "label": "Claude Opus 4.1", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "context_window": 200000, "stability": "stable", "suggested_uses": ["advanced coding", "complex reasoning", "review"]},
        ],
        large_context,
    )

    assert selection["selected_model"] == "claude/claude-opus-4-1"
    assert selection["source"] == "heuristic"


def test_select_best_model_uses_history_to_prefer_better_outcome_model(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Implement the project add menu flow.",
        [
            {"id": "codex/gpt-5.4", "label": "gpt-5.4", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "codex/gpt-5.4@high", "label": "gpt-5.4 / High", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "stable", "suggested_uses": ["debugging", "multi-file edits", "reviews"]},
        ],
        "Changed files: app.js, index.html",
        routing_history={
            "workspace": {
                "by_model": {
                    "codex/gpt-5.4": {"attempts": 4, "successes": 4, "task_types": {"implementation": {"attempts": 4, "successes": 4}}},
                    "codex/gpt-5.4@high": {"attempts": 4, "successes": 1, "task_types": {"implementation": {"attempts": 4, "successes": 1}}},
                }
            },
            "global": {"by_model": {}},
        },
    )

    assert selection["selected_model"] == "codex/gpt-5.4"
    assert selection["source"] == "heuristic"


def test_select_best_model_prefers_claude_opus_for_review_work(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Review this PR and call out regressions or risky changes.",
        [
            {"id": "codex/gpt-5.2@medium", "label": "GPT 5.2 / Medium", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "provider": "anthropic", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "balanced implementation", "debugging", "review", "multi-file work"]},
            {"id": "claude/claude-opus-4-1", "label": "Claude Opus 4.1", "provider": "anthropic", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "stable", "suggested_uses": ["advanced coding", "complex reasoning", "architecture", "debugging", "review", "multi-file work"]},
        ],
        "Changed files: api.py, selector.py, tests/test_selector.py\nRecent history: regression concerns",
    )

    assert selection["selected_model"] == "claude/claude-opus-4-1"
    assert selection["source"] == "heuristic"


def test_select_best_model_prefers_gemini_pro_for_architecture_work(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Design the architecture for migrating this app to a job queue with retries and failure recovery.",
        [
            {"id": "codex/gpt-5.2@medium", "label": "GPT 5.2 / Medium", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "provider": "google", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "stable", "suggested_uses": ["deep reasoning", "complex coding", "architecture", "review", "multi-file work"]},
        ],
        "Changed files: jobs.py, worker.py, api.py, state.py",
    )

    assert selection["selected_model"] == "gemini/gemini-2.5-pro"
    assert selection["source"] == "heuristic"


def test_select_best_model_prefers_cursor_for_implementation_work(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Refactor the data flow across api.py, state.py, and the runtime adapters.",
        [
            {"id": "cursor/default", "label": "Cursor Default", "provider": "cursor", "runtime": "cursor", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation", "multi-file work"]},
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "provider": "anthropic", "runtime": "claude", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "balanced implementation", "review"]},
            {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "provider": "google", "runtime": "gemini", "cost_tier": "low", "speed_tier": "high", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "quick debugging"]},
        ],
        "Changed files: bettercode/web/api.py, bettercode/context/state.py, bettercode/router/selector.py",
    )

    assert selection["selected_model"] == "cursor/default"
    assert selection["source"] == "heuristic"


def test_select_best_model_keeps_balanced_model_for_standard_implementation(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    selection = selector.select_best_model(
        "Implement the new project add flow in the sidebar.",
        [
            {"id": "codex/gpt-5.2@medium", "label": "GPT 5.2 / Medium", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "claude/claude-opus-4-1", "label": "Claude Opus 4.1", "provider": "anthropic", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "stable", "suggested_uses": ["advanced coding", "complex reasoning", "architecture", "debugging", "review", "multi-file work"]},
        ],
        "Changed files: app.js, index.html",
    )

    assert selection["selected_model"] == "codex/gpt-5.2@medium"
    assert selection["source"] == "heuristic"


def test_top_candidates_preserve_cross_provider_mix():
    task = selector.analyze_routing_task(
        "Review the current implementation and propose a safe refactor.",
        "Changed files: api.py, selector.py, tests/test_selector.py",
    )

    candidates = selector._top_candidates(
        [
            {"id": "codex/gpt-5.2", "label": "GPT 5.2", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "codex/gpt-5.4", "label": "GPT 5.4", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "codex/gpt-5.4-mini", "label": "GPT 5.4 Mini", "provider": "openai", "cost_tier": "low", "speed_tier": "high", "capability_tier": "medium", "stability": "stable", "suggested_uses": ["small edits", "cheap fast-path"]},
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "provider": "anthropic", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "balanced implementation", "debugging", "review", "multi-file work"]},
            {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "provider": "google", "cost_tier": "high", "speed_tier": "medium", "capability_tier": "very_high", "stability": "stable", "suggested_uses": ["deep reasoning", "complex coding", "architecture", "review", "multi-file work"]},
        ],
        task,
        None,
    )

    candidate_ids = {candidate["id"] for candidate in candidates}
    assert "claude/claude-sonnet-4" in candidate_ids
    assert "gemini/gemini-2.5-pro" in candidate_ids


def test_select_best_model_local_router_prompt_uses_task_fit_metadata(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "selected_model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })
    monkeypatch.setattr("bettercode.router.selector.heuristic_confidence", lambda *_args, **_kwargs: selector.HEURISTIC_CONFIDENCE_HIGH)
    captured = {}

    def fake_api_request(method, path, payload=None, timeout=5.0):
        captured["payload"] = payload
        candidates = json.loads(payload["messages"][1]["content"])["candidates"]
        chosen = next(
            (candidate["id"] for candidate in candidates if "review" in " ".join(candidate.get("suggested_uses") or []).lower()),
            candidates[0]["id"],
        )
        return {"message": {"content": json.dumps({"selected_model": chosen, "reasoning": "This option fits review work well."})}}

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    selection = selector.select_best_model(
        "Review the changes and find risky regressions.",
        [
            {"id": "codex/gpt-5.2", "label": "GPT 5.2", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "codex/gpt-5.4", "label": "GPT 5.4", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "standard implementation"]},
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "provider": "anthropic", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "stability": "stable", "suggested_uses": ["general coding", "balanced implementation", "debugging", "review", "multi-file work"]},
            {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "provider": "google", "cost_tier": "low", "speed_tier": "high", "capability_tier": "high", "stability": "stable", "suggested_uses": ["low-latency reasoning", "general coding", "high-volume tasks", "quick debugging"]},
        ],
        "Changed files: api.py, selector.py",
    )

    prompt = captured["payload"]["messages"][0]["content"]
    candidate_ids = {candidate["id"] for candidate in json.loads(captured["payload"]["messages"][1]["content"])["candidates"]}

    assert "model router" in prompt
    assert candidate_ids == {"codex/gpt-5.2", "codex/gpt-5.4", "claude/claude-sonnet-4", "gemini/gemini-2.5-flash"}
    assert selection["selected_model"] == "claude/claude-sonnet-4"
    assert selection["source"] == "local"


def test_local_preprocess_candidates_respect_tiny_budget(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector._installed_ollama_models", lambda: [
        {"name": "qwen2.5-coder:1.5b", "size": 1.5 * (1024 ** 3)},
        {"name": "qwen2.5-coder:3b", "size": 1.9 * (1024 ** 3)},
        {"name": "qwen3:4b", "size": 2.5 * (1024 ** 3)},
    ])

    candidates = selector.local_preprocess_candidates("tiny")
    candidate_map = {candidate["id"]: candidate for candidate in candidates}

    assert "qwen2.5-coder:1.5b" in candidate_map
    assert candidate_map["qwen2.5-coder:1.5b"]["installed"] is True
    assert candidate_map["qwen2.5-coder:1.5b"]["label"] == "Low Mem (1.0 GB)"
    assert "qwen2.5-coder:3b" in candidate_map
    assert candidate_map["qwen2.5-coder:3b"]["label"] == "High Mem (1.9 GB)"
    assert "qwen3:4b" not in candidate_map


def test_local_preprocess_candidates_include_curated_installable_models(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector._installed_ollama_models", lambda: [])

    candidates = selector.local_preprocess_candidates("tiny")
    candidate_ids = {candidate["id"] for candidate in candidates}

    assert "qwen2.5-coder:1.5b" in candidate_ids
    assert "qwen3:1.7b" in candidate_ids
    assert "ibm/granite3.3:2b" not in candidate_ids
    assert "qwen2.5-coder:7b" not in candidate_ids
    assert all(candidate["installed"] is False for candidate in candidates)


def test_resolve_local_preprocess_model_ignores_uninstalled_override(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_model", lambda: "qwen2.5-coder:7b")
    monkeypatch.setattr("bettercode.router.selector._installed_ollama_models", lambda: [
        {"name": "qwen2.5-coder:1.5b", "size": 1.1 * (1024 ** 3)},
    ])

    resolved = selector.resolve_local_preprocess_model("small")

    assert resolved == "qwen2.5-coder:1.5b"


def test_apply_local_preprocess_runtime_change_unloads_previous_and_warms_next(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "bettercode.router.selector.require_selector_runtime",
        lambda **kwargs: {
            "installed": True,
            "running": True,
            "mode": "small",
            "model": selector.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:3b",
            "model_ready": True,
        },
    )
    monkeypatch.setattr(
        "bettercode.router.selector.selector_status",
        lambda: {
            "installed": True,
            "running": True,
            "mode": "small",
            "model": selector.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:3b",
            "model_ready": True,
        },
    )

    def fake_api_request(method, path, payload, timeout=None):
        calls.append((method, path, payload, timeout))
        return {"ok": True}

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    status = selector.apply_local_preprocess_runtime_change(
        "qwen2.5-coder:1.5b",
        "small",
        "qwen2.5-coder:3b",
    )

    assert status["selected_model"] == "qwen2.5-coder:3b"
    assert calls[0][2]["model"] == "qwen2.5-coder:1.5b"
    assert calls[0][2]["keep_alive"] == 0
    assert calls[1][2]["model"] == "qwen2.5-coder:3b"
    assert calls[1][2]["keep_alive"] == selector.SELECTOR_KEEP_ALIVE


def test_local_preprocess_candidates_include_5gb_models_in_small_mode(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector._installed_ollama_models", lambda: [])

    candidates = selector.local_preprocess_candidates("small")
    candidate_ids = {candidate["id"] for candidate in candidates}

    assert "qwen3:4b" in candidate_ids
    assert "granite-code:8b" not in candidate_ids
    assert "qwen2.5-coder:7b" in candidate_ids
    assert "ibm/granite3.3:8b" not in candidate_ids
    candidate_map = {candidate["id"]: candidate for candidate in candidates}
    assert candidate_map["qwen3:4b"]["label"] == "Extra High Mem (2.5 GB)"
    assert candidate_map["qwen2.5-coder:7b"]["label"] == "Ludacris Mem (4.7 GB)"


def test_run_local_model_response_includes_human_language_instruction(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "bettercode.router.selector.require_selector_runtime",
        lambda **kwargs: {
            "installed": True,
            "running": True,
            "mode": "tiny",
            "model": selector.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:1.5b",
            "model_ready": True,
        },
    )

    def fake_api_request(method, path, payload, timeout=None):
        captured["payload"] = payload
        return {"message": {"content": "Bonjour"}}

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    result = selector.run_local_model_response("Say hello.", model_id="qwen2.5-coder:1.5b", human_language="fr")

    assert result["reply"] == "Bonjour"
    assert "French" in captured["payload"]["messages"][0]["content"]


def test_maybe_select_local_execution_accepts_safe_self_contained_request(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "tiny")
    monkeypatch.setattr(
        "bettercode.router.selector.ensure_selector_runtime",
        lambda **kwargs: {
            "installed": True,
            "running": True,
            "model": selector.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:1.5b",
            "model_ready": True,
            "mode": "tiny",
        },
    )
    monkeypatch.setattr(
        "bettercode.router.selector._api_request",
        lambda *_args, **_kwargs: {
            "message": {"content": json.dumps({"use_local": True, "confidence": 10, "reasoning": "The request is self-contained."})}
        },
    )

    selection = selector.maybe_select_local_execution("Write a Python function that slugifies a string.")

    assert selection is not None
    assert selection["selected_model"] == "local/qwen2.5-coder:1.5b"
    assert selection["source"] == "local_direct"


def test_maybe_select_local_execution_rejects_repo_edit_requests(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "tiny")
    monkeypatch.setattr(
        "bettercode.router.selector._api_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("repo edit requests should not hit the local gate")),
    )

    selection = selector.maybe_select_local_execution("Update app.js to fix the sidebar bug in this project.")

    assert selection is None


def test_maybe_select_local_execution_short_circuits_obvious_local_answers(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "tiny")
    monkeypatch.setattr(
        "bettercode.router.selector.ensure_selector_runtime",
        lambda **kwargs: {
            "installed": True,
            "running": True,
            "model": selector.SELECTOR_MODEL,
            "selected_model": "qwen2.5-coder:1.5b",
            "model_ready": True,
            "mode": "tiny",
        },
    )
    monkeypatch.setattr(
        "bettercode.router.selector._api_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("obvious local answers should not hit the local approval gate")),
    )

    selection = selector.maybe_select_local_execution("What is 2 + 2?")

    assert selection is not None
    assert selection["selected_model"] == "local/qwen2.5-coder:1.5b"
    assert selection["source"] == "local_direct"
    assert selection["confidence"] == 10


def test_select_best_model_uses_intent_gate_for_simple_requests(monkeypatch):
    monkeypatch.setattr(
        "bettercode.router.selector.ensure_selector_runtime",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("local preprocess should be skipped")),
    )

    selection = selector.select_best_model(
        "Rename the button label.",
        [
            {"id": "codex/gpt-5.4@low", "label": "gpt-5.4 / Low", "cost_tier": "low", "speed_tier": "high", "capability_tier": "medium", "reasoning_effort": "low"},
            {"id": "codex/gpt-5.4", "label": "gpt-5.4", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high", "reasoning_effort": "medium"},
        ],
        "",
    )

    assert selection["source"] == "heuristic"
    assert selection["selected_model"] == "codex/gpt-5.4@low"


def test_plan_subtasks_skips_local_breakdown_for_simple_requests(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr(
        "bettercode.router.selector.ensure_selector_runtime",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("planner should be skipped")),
    )

    plan = selector.plan_subtasks(
        "Update the button text.",
        ["codex/gpt-5.4", "claude/sonnet"],
        "",
    )

    assert plan["source"] == "intent_gate"
    assert [task["stage"] for task in plan["tasks"]] == ["edit"]
    assert plan["tasks"][0]["model_id"] in ("codex/gpt-5.4", "claude/sonnet")


def test_suggest_follow_up_recommendations_skips_cosmetic_changes(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    recommendations = selector.suggest_follow_up_recommendations(
        "Adjust spacing in the sidebar.",
        "Updated the CSS spacing.",
        [{"path": "bettercode/web/static/styles.css", "status": "modified"}],
    )

    assert recommendations == []


def test_suggest_follow_up_recommendations_uses_fallback_when_local_preprocess_off(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "off")
    monkeypatch.setattr(
        "bettercode.router.selector.ensure_selector_runtime",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("selector should stay off")),
    )

    recommendations = selector.suggest_follow_up_recommendations(
        "Fix the session resume logic for Codex.",
        "Updated the Codex resume command builder.",
        [{"path": "bettercode/web/api.py", "status": "modified"}],
    )

    assert recommendations == [selector.TEST_RECOMMENDATION]


def test_suggest_follow_up_recommendations_for_behavior_changes(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    recommendations = selector.suggest_follow_up_recommendations(
        "Fix the session resume logic for Codex.",
        "Updated the Codex resume command builder.",
        [{"path": "bettercode/web/api.py", "status": "modified"}],
    )

    assert recommendations == [selector.TEST_RECOMMENDATION]


def test_suggest_follow_up_recommendations_skips_selector_for_binary_questions(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })
    monkeypatch.setattr(
        "bettercode.router.selector._api_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("binary questions should not call the selector")),
    )

    recommendations = selector.suggest_follow_up_recommendations(
        "Warm up the midnight theme and add Sage.",
        "Updated midnight and added Sage. Want any color tweaks?",
        [],
    )

    assert recommendations == []


def test_suggest_follow_up_recommendations_filters_ui_instructions_for_questions(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })

    def fake_api_request(method, path, payload=None, timeout=5.0):
        return {
            "message": {
                "content": '{"recommendations":["Select the new light theme \\"Sage\\" from Settings > Theme."]}'
            }
        }

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    recommendations = selector.suggest_follow_up_recommendations(
        "Add another light theme option.",
        "I added Sage and Linen. Which one should be the default?",
        [],
    )

    assert recommendations == []


def test_suggest_follow_up_recommendations_uses_full_reply_and_allows_custom_prompt(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })
    captured = {}

    def fake_api_request(method, path, payload=None, timeout=5.0):
        captured["payload"] = payload
        return {
            "message": {
                "content": '{"recommendations":["Run the app and verify the queued instruction badge clears after the next turn."]}'
            }
        }

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)
    long_reply = "A" * 1600

    recommendations = selector.suggest_follow_up_recommendations(
        "Add instruction queue support.",
        long_reply,
        [{"path": "bettercode/web/static/app.js", "status": "modified"}],
    )

    assert recommendations == ["Run the app and verify the queued instruction badge clears after the next turn."]
    assert long_reply in captured["payload"]["messages"][1]["content"]


def test_plan_subtasks_fallback_includes_stage_metadata(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": False,
        "running": False,
        "model": selector.SELECTOR_MODEL,
        "model_ready": False,
    })

    plan = selector.plan_subtasks(
        "Build the feature.",
        ["codex/gpt-5.4", "claude/sonnet"],
        "Changed files: app.js",
    )

    assert plan["source"] == "fallback"
    assert [task["stage"] for task in plan["tasks"]] == ["edit"]
    assert all(task["track_key"].startswith("model:") for task in plan["tasks"])
    assert "main code-writing step" in plan["tasks"][0]["selection_reason"]


def test_plan_subtasks_normalizes_local_router_stage_and_model(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })

    def fake_api_request(method, path, payload=None, timeout=5.0):
        return {
            "message": {
                "content": json.dumps([
                    {
                        "id": "add-panel",
                        "title": "Add task panel component",
                        "detail": "Implement the new live task panel component.",
                        "depends_on": [],
                        "execution": "sync",
                        "stage": "edit",
                        "model_id": "codex/gpt-5.4",
                    },
                    {
                        "id": "wire-ui",
                        "title": "Wire the UI",
                        "detail": "Connect the panel to the main layout.",
                        "depends_on": ["add-panel"],
                        "execution": "sync",
                        "stage": "edit",
                        "model_id": "missing/model",
                    },
                ])
            }
        }

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    plan = selector.plan_subtasks(
        "Implement the task panel.",
        [
            {"id": "codex/gpt-5.4", "label": "gpt-5.4"},
            {"id": "claude/sonnet", "label": "Claude Sonnet"},
        ],
        "Changed files: app.js, styles.css",
    )

    assert plan["source"] == "local"
    assert plan["tasks"][0]["stage"] == "edit"
    assert plan["tasks"][0]["model_id"] == "codex/gpt-5.4"
    assert plan["tasks"][0]["model_label"] == "gpt-5.4"
    assert "main code-writing step" in plan["tasks"][0]["selection_reason"]
    assert plan["tasks"][1]["stage"] == "edit"
    assert plan["tasks"][1]["model_id"] in ("codex/gpt-5.4", "claude/sonnet")
    assert plan["tasks"][1]["track_key"].startswith("model:")
    assert "main code-writing step" in plan["tasks"][1]["selection_reason"]


def test_plan_subtasks_distributes_tracks_across_multiple_models(monkeypatch):
    monkeypatch.setattr("bettercode.router.selector.get_local_preprocess_mode", lambda: "small")
    monkeypatch.setattr("bettercode.router.selector.ensure_selector_runtime", lambda **kwargs: {
        "installed": True,
        "running": True,
        "model": selector.SELECTOR_MODEL,
        "model_ready": True,
    })

    def fake_api_request(method, path, payload=None, timeout=5.0):
        return {
            "message": {
                "content": json.dumps([
                    {
                        "id": "inspect-code",
                        "title": "Inspect the current code",
                        "detail": "Read the current files and note the existing flow.",
                        "depends_on": [],
                        "execution": "async",
                        "stage": "inspect",
                        "model_id": "",
                    },
                    {
                        "id": "implement-flow",
                        "title": "Implement the execution flow",
                        "detail": "Add the main behavior changes across the relevant files.",
                        "depends_on": ["inspect-code"],
                        "execution": "sync",
                        "stage": "edit",
                        "model_id": "",
                    },
                    {
                        "id": "validate-output",
                        "title": "Validate the result",
                        "detail": "Review the result and look for regressions.",
                        "depends_on": ["implement-flow"],
                        "execution": "async",
                        "stage": "validate",
                        "model_id": "",
                    },
                ])
            }
        }

    monkeypatch.setattr("bettercode.router.selector._api_request", fake_api_request)

    plan = selector.plan_subtasks(
        "Inspect the current flow, implement the tracker, and validate the result.",
        [
            {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "runtime": "gemini", "provider": "google", "cost_tier": "low", "speed_tier": "high", "capability_tier": "high"},
            {"id": "codex/gpt-5.4", "label": "GPT-5.4", "runtime": "codex", "provider": "openai", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high"},
            {"id": "claude/claude-sonnet-4", "label": "Claude Sonnet 4", "runtime": "claude", "provider": "anthropic", "cost_tier": "medium", "speed_tier": "medium", "capability_tier": "high"},
        ],
        "Changed files: app.js, styles.css, api.py",
    )

    assert plan["source"] == "local"
    assert {task["model_id"] for task in plan["tasks"]} == {
        "gemini/gemini-2.5-flash",
        "codex/gpt-5.4",
        "claude/claude-sonnet-4",
    }
    assert [task["track_key"] for task in plan["tasks"]] == [
        "model:gemini/gemini-2.5-flash",
        "model:codex/gpt-5.4",
        "model:claude/claude-sonnet-4",
    ]
    assert "read-heavy inspection step" in plan["tasks"][0]["selection_reason"]
    assert "main code-writing step" in plan["tasks"][1]["selection_reason"]
    assert "validation and review step" in plan["tasks"][2]["selection_reason"]
