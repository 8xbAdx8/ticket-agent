"""P2 scenario schema and deterministic validation (no model, no network)."""
import re

DIMENSIONS = ("功能准确性", "工具调用", "RAG", "多轮", "安全", "边界", "性能")
DIM_CODE = {"功能准确性": "FUNC", "工具调用": "TOOL", "RAG": "RAG", "多轮": "MULTI",
            "安全": "SAFE", "边界": "BOUND", "性能": "PERF"}
BEHAVIORS = ("answer", "clarify", "refuse", "insufficient_evidence", "explain_conflict", "correct_premise")
ALLOWED_EXPECT = ("must_call", "must_not_call", "args", "reply_contains", "reply_not_contains",
                  "finish_reason", "require_citation", "raises")
DIFFICULTY = ("easy", "medium", "hard")
MAX_TURNS = 4


def validate_expect(expect, tools, *, allow_raises=True):
    """Validate one assertion block; raises describes chat(), never a tool error."""
    if not isinstance(expect, dict):
        return ["bad_expect"]
    errors = []
    unknown = sorted(set(expect) - set(ALLOWED_EXPECT))
    if unknown:
        errors.append("unknown_expect_keys:" + ",".join(unknown))
    if "raises" in expect:
        if not allow_raises:
            errors.append("raises_only_allowed_in_final_expect")
        if not isinstance(expect["raises"], str) or not re.fullmatch(r"[A-Za-z_]\w*", expect["raises"]):
            errors.append("bad_raises")
        conflicts = [key for key in ("reply_contains", "reply_not_contains", "must_call",
                     "must_not_call", "args", "finish_reason") if key in expect]
        if expect.get("require_citation"):
            conflicts.append("require_citation")
        if conflicts:
            errors.append("raises_conflicts_with:" + ",".join(conflicts))
    for key in ("must_call", "must_not_call"):
        value = expect.get(key, [])
        if not isinstance(value, list) or not all(isinstance(t, str) and t in tools for t in value):
            errors.append("unknown_tool" if key == "must_call" else "unknown_forbidden_tool")
    calls, forbidden = expect.get("must_call", []), expect.get("must_not_call", [])
    if isinstance(calls, list) and isinstance(forbidden, list):
        overlap = sorted(t for t in calls if isinstance(t, str) and t in forbidden)
        if overlap:
            errors.append("must_call_conflicts_with_must_not_call:" + ",".join(overlap))
    args = expect.get("args", {})
    if not isinstance(args, dict):
        errors.append("bad_args")
        args = {}
    for tool, params in args.items():
        if tool not in tools:
            errors.append("args_unknown_tool:" + tool)
            continue
        if isinstance(forbidden, list) and tool in forbidden:
            errors.append("args_conflicts_with_must_not_call:" + tool)
        if not isinstance(params, dict):
            errors.append("args_not_object:" + tool)
            continue
        for key, value in params.items():
            if key not in tools[tool]["properties"]:
                errors.append(f"args_unknown_key:{tool}.{key}")
            enum = tools[tool]["enums"].get(key)
            if enum and value not in enum:
                errors.append(f"args_enum:{tool}.{key}")
            if isinstance(value, str) and value.startswith("<") and not re.fullmatch(r"<rel_date:[+-]\d+>", value):
                errors.append(f"placeholder_not_supported:{tool}.{key}")
    for key in ("reply_contains", "reply_not_contains"):
        if key in expect and (not isinstance(expect[key], list) or
                            not all(isinstance(x, str) and x for x in expect[key])):
            errors.append("bad_" + key)
    if expect.get("finish_reason") not in (None, "stop", "max_steps_exceeded"):
        errors.append("bad_finish_reason")
    if "require_citation" in expect and type(expect["require_citation"]) is not bool:
        errors.append("bad_require_citation")
    return errors


def normalize(text):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(text).lower())


def bigrams(text):
    clean = normalize(text)
    return {clean[i:i + 2] for i in range(max(0, len(clean) - 1))} or {clean}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _subset(expected, actual):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(key in actual and _subset(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(item in actual for item in expected)
    return expected == actual


def validate_case(case, *, docs, tools, existing_questions=(), batch_questions=(), threshold=0.85):
    """Return (errors, warnings). `docs` maps doc_id -> {title, content, ...}."""
    errors, warnings = [], []
    if not isinstance(case, dict):
        return ["not_an_object"], []
    for field in ("dimension", "title", "turns", "expected_behavior", "expect",
                  "expected_doc_ids", "required_evidence", "forbidden_claims", "difficulty", "packet_id"):
        if field not in case:
            errors.append(f"missing:{field}")
    if errors:
        return errors, warnings
    if case["dimension"] not in DIMENSIONS:
        errors.append("unknown_dimension")
    turns = case.get("turns")
    expect = case.get("expect")
    raises_value = expect.get("raises") if isinstance(expect, dict) else None
    if not isinstance(turns, list) or not (1 <= len(turns) <= MAX_TURNS):
        errors.append("bad_turns")
    elif not all(isinstance(t, str) and (t.strip() or raises_value == "ValueError") for t in turns):
        errors.append("empty_turn")
    if case["expected_behavior"] not in BEHAVIORS:
        errors.append("unknown_behavior")
    if case["difficulty"] not in DIFFICULTY:
        errors.append("unknown_difficulty")
    if not isinstance(expect, dict) or (not expect and not case.get("turn_expects")):
        errors.append("bad_expect")
        expect = {}
    errors.extend(validate_expect(expect, tools))
    turn_expects = case.get("turn_expects")
    blocks = [expect]
    if "turn_expects" in case:
        if "raises" in expect:
            errors.append("raises_conflicts_with:turn_expects")
        if not isinstance(turn_expects, list):
            errors.append("bad_turn_expects")
        elif not isinstance(turns, list) or len(turn_expects) != len(turns):
            errors.append("turn_expects_length_mismatch")
        else:
            for index, block in enumerate(turn_expects):
                errors.extend(f"turn_expects[{index}]:{error}" for error in
                              validate_expect(block, tools, allow_raises=False))
                if isinstance(block, dict):
                    blocks.append(block)
    if not expect and not any(block for block in blocks):
        errors.append("no_assertions")
    calls = expect.get("must_call", [])
    if "reply_contains" in expect:
        value = expect["reply_contains"]
        if not isinstance(value, list):
            errors.append("bad_reply_contains")
        elif not value and not (expect.get("must_call") or expect.get("must_not_call") or
                               expect.get("reply_not_contains") or expect.get("raises") or case.get("turn_expects")):
            errors.append("no_assertions")
    if expect.get("finish_reason") not in (None, "stop", "max_steps_exceeded"):
        errors.append("bad_finish_reason")

    doc_ids = case.get("expected_doc_ids") or []
    if not isinstance(doc_ids, list):
        errors.append("bad_expected_doc_ids")
        doc_ids = []
    if any(block.get("require_citation") for block in blocks) and not doc_ids:
        errors.append("citation_without_docs")
    for doc_id in doc_ids:
        if doc_id not in docs:
            errors.append("doc_not_in_corpus:" + str(doc_id))
    for item in case.get("required_evidence") or []:
        if not isinstance(item, dict) or not item.get("doc_id") or not item.get("quote"):
            errors.append("bad_evidence_item")
            continue
        doc = docs.get(item["doc_id"])
        if not doc:
            errors.append("evidence_doc_missing:" + str(item["doc_id"]))
            continue
        if normalize(item["quote"]) and normalize(item["quote"]) not in normalize(doc["content"]):
            errors.append("quote_not_verbatim:" + str(item["doc_id"]))
    if not case.get("forbidden_claims"):
        errors.append("forbidden_claims_required")

    behavior = case["expected_behavior"]
    if behavior == "answer" and not (doc_ids or any(block.get("must_call") for block in blocks)):
        errors.append("answer_without_grounding")
    if behavior in ("insufficient_evidence",) and doc_ids:
        errors.append("insufficient_evidence_with_docs")
    if behavior == "refuse" and not case.get("forbidden_claims"):
        errors.append("refuse_without_forbidden_claim")
    if behavior == "clarify" and not (expect.get("reply_contains") or case.get("clarification_fields")):
        warnings.append("clarify_without_fields")

    for question in (" ".join(turns) if isinstance(turns, list) and all(isinstance(t, str) for t in turns) else "",):
        grams = bigrams(question)
        for prior in list(existing_questions) + list(batch_questions):
            if jaccard(grams, bigrams(prior)) >= threshold:
                errors.append("duplicate_question")
                break
    return errors, warnings


def compile_expect(case):
    """Executor-facing shape; only known keys survive."""
    expect = dict(case.get("expect") or {})
    return {key: expect[key] for key in ALLOWED_EXPECT if key in expect}
