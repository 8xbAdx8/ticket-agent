"""Offline P2 pipeline tests: packets, generator parsing, validation, executor."""
import json
import unittest

from target import p2_case, p2_generator, p2_packets
from target.p2_executor import run_case


def scenario(**overrides):
    case = {
        "dimension": "RAG",
        "title": "退票手续费阶梯",
        "turns": ["开车前三天退票，手续费是多少？"],
        "expected_behavior": "answer",
        "expect": {"must_call": ["search_policy"], "reply_contains": ["5%"],
                   "require_citation": True, "finish_reason": "stop"},
        "expected_doc_ids": ["P01"],
        "required_evidence": [{"doc_id": "P01", "quote": "开车前 48 小时以上退票，收取票价 5% 手续费"}],
        "forbidden_claims": ["真实退款已到账"],
        "difficulty": "easy",
        "packet_id": "ev-p01-0000",
    }
    case.update(overrides)
    return case


class PacketTests(unittest.TestCase):
    def test_every_dimension_has_docs_tools_and_entities(self):
        packets = p2_packets.build_all()
        self.assertEqual(set(packets), set(p2_case.DIMENSIONS))
        for dimension, packet in packets.items():
            self.assertTrue(packet["docs"], dimension)
            self.assertTrue(packet["tools"], dimension)
            self.assertTrue(packet["allowed_entities"], dimension)

    def test_packets_are_deterministic(self):
        a = p2_packets.build_all()
        b = p2_packets.build_all()
        self.assertEqual(a, b)


class GeneratorTests(unittest.TestCase):
    def test_parse_json_handles_fences_and_noise(self):
        self.assertEqual(p2_generator.parse_json('{"scenarios":[]}'), {"scenarios": []})
        self.assertEqual(p2_generator.parse_json('```json\n{"scenarios":[]}\n```'), {"scenarios": []})
        self.assertEqual(p2_generator.parse_json('前言 {"scenarios":[]} 后记'), {"scenarios": []})
        with self.assertRaises(ValueError):
            p2_generator.parse_json("not json")

    def test_generate_normalizes_and_retries_once(self):
        calls = {"n": 0}

        def fake(provider, settings, system, user, *, run_id, model_step):
            calls["n"] += 1
            if calls["n"] == 1:
                return "not json", {"prompt": 1, "completion": 1}, ["req-1"], []
            return json.dumps({"scenarios": [scenario()]}, ensure_ascii=False), {"prompt": 10, "completion": 20}, ["req-2"], []

        packet = p2_packets.build("RAG")
        result = p2_generator.generate("deepseek", None, "RAG", packet, 3, [], run_id="b1", call_fn=fake)
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["request_ids"], ["req-2"])
        rows = p2_generator.normalize(result["scenarios"], "RAG", "deepseek", "deepseek-flash",
                                      response_sha="x", request_id="req-2", prompt_sha256="y")
        self.assertEqual(rows[0]["case_id"], "P2-RAG-0001")
        self.assertEqual(rows[0]["provenance"]["origin"], "ai_generated")


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.docs = p2_packets.corpus_docs()
        self.tools = p2_packets.tool_specs()

    def test_valid_scenario_passes(self):
        errors, _ = p2_case.validate_case(scenario(), docs=self.docs, tools=self.tools)
        self.assertEqual(errors, [])

    def test_bad_quote_and_unknown_tool_rejected(self):
        errors, _ = p2_case.validate_case(
            scenario(required_evidence=[{"doc_id": "P01", "quote": "这句话不在文档里"}]),
            docs=self.docs, tools=self.tools)
        self.assertIn("quote_not_verbatim:P01", errors)
        errors, _ = p2_case.validate_case(
            scenario(expect={"must_call": ["refund_everything"]}), docs=self.docs, tools=self.tools)
        self.assertIn("unknown_tool", errors)

    def test_duplicate_question_rejected(self):
        errors, _ = p2_case.validate_case(scenario(), docs=self.docs, tools=self.tools,
                                          existing_questions=["开车前三天退票，手续费是多少？"])
        self.assertIn("duplicate_question", errors)


class ExecutorTests(unittest.TestCase):
    def test_runs_in_sandbox_and_evaluates_assertions(self):
        case = scenario(expect={"must_call": ["query_tickets"], "finish_reason": "stop"},
                        expected_doc_ids=[], required_evidence=[])
        row = run_case(case)
        self.assertIn(row["status"], ("passed", "failed"))
        self.assertTrue(row["checks"])
        self.assertEqual(row["id"], None)  # no case_id in this fixture


if __name__ == "__main__":
    unittest.main()
