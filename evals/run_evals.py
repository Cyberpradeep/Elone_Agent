import os
import json
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from graph import graph
from shared.tool_catalog import TOOL_CATALOG
from shared.llm_config import get_llm
from shared.tracing import setup_observability_tracing


def predict_l1_agent(inputs: dict) -> dict:
    """Target prediction wrapper for LangGraph workflow evaluation."""
    ticket_id = inputs.get("ticket_id") or "eval-1000"
    config = {"configurable": {"thread_id": f"eval-{ticket_id}"}}

    initial_state = {
        "ticket_id": inputs.get("ticket_id"),
        "customer_email": inputs.get("customer_email"),
        "category": inputs.get("category"),
        "ticket_raw": inputs["ticket_raw"],
        "entities": {"email": inputs.get("customer_email")},
        "tool_catalog": TOOL_CATALOG,
        "replan_attempts": 0,
        "sop_fetch_attempts": 0,
        "execution_retry_attempts": 0,
        "clarification_attempts": 0,
        "workflow_status": "pending",
        "audit_log": [],
    }

    final_state = graph.invoke(initial_state, config=config)

    entities = final_state.get("entities") or {}
    return {
        "intent": final_state.get("intent", ""),
        "category": final_state.get("category", ""),
        "hostname": entities.get("hostname", ""),
        "variables": final_state.get("variables") or {},
        "customer_reply": final_state.get("customer_ticket_reply") or "",
        "workflow_status": final_state.get("workflow_status", ""),
        "audit_log": final_state.get("audit_log", []),
    }


def run_langsmith_evals():
    """Runs LangSmith Automated Evaluator Suite."""
    setup_observability_tracing()
    api_key = os.environ.get("LANGCHAIN_API_KEY")

    eval_json_path = os.path.join(BASE_DIR, "evals", "eval_dataset.json")
    if not os.path.exists(eval_json_path):
        print(f"[Eval Error] Benchmark dataset not found at: {eval_json_path}")
        return

    with open(eval_json_path, "r", encoding="utf-8") as f:
        benchmark_cases = json.load(f)

    if api_key and api_key.strip():
        try:
            from langsmith import Client
            from langsmith.evaluation import evaluate

            client = Client()
            dataset_name = "L1_Support_Agent_Benchmark_Dataset"

            # Create or update dataset in LangSmith
            if not client.has_dataset(dataset_name=dataset_name):
                dataset = client.create_dataset(dataset_name=dataset_name, description="L1 Support Agent Ticket Benchmark Dataset")
                for case in benchmark_cases:
                    client.create_example(
                        inputs={"ticket_raw": case["ticket_raw"], "customer_email": case.get("customer_email"), "category": case.get("category")},
                        outputs={"expected_intent": case["expected_intent"], "expected_hostname": case["expected_hostname"]},
                        dataset_id=dataset.id,
                    )
                print(f"[LangSmith] Created benchmark dataset '{dataset_name}' with {len(benchmark_cases)} examples.")

            def eval_intent_accuracy(run, example):
                predicted = (run.outputs or {}).get("intent", "")
                expected = (example.outputs or {}).get("expected_intent", "")
                p_clean = predicted.lower().replace("_", " ").strip()
                e_clean = expected.lower().replace("_", " ").strip()
                score = 1.0 if (e_clean in p_clean or p_clean in e_clean) else 0.0
                return {"key": "intent_accuracy", "score": score}

            def eval_hostname_accuracy(run, example):
                predicted = (run.outputs or {}).get("hostname", "")
                expected = (example.outputs or {}).get("expected_hostname", "")
                score = 1.0 if (predicted.lower().strip() == expected.lower().strip()) else 0.0
                return {"key": "hostname_accuracy", "score": score}

            evaluators = [eval_intent_accuracy, eval_hostname_accuracy]

            print(f"[LangSmith] Running evaluation experiment on dataset '{dataset_name}'...")
            results = evaluate(
                predict_l1_agent,
                data=dataset_name,
                evaluators=evaluators,
                experiment_prefix="l1-agent-benchmark",
            )
            print("[PASS] LangSmith Evaluation Complete! View live scorecards at https://smith.langchain.com\n")
            return
        except Exception as e:
            print(f"[LangSmith Warning] Failed to run online LangSmith evals ({e}). Falling back to local evaluator.")

    # Local Evaluator Fallback (if offline or no API key set)
    run_local_eval_benchmark(benchmark_cases)


def run_local_eval_benchmark(benchmark_cases: list):
    """Local LLM-as-a-Judge benchmark evaluator fallback."""
    print("\n==================================================")
    print("--- [STARTING LOCAL LLM-AS-A-JUDGE EVALUATION] ---")
    print("==================================================")

    llm_judge = get_llm("triage", temperature=0)
    passed_count = 0
    total_count = len(benchmark_cases)

    for case in benchmark_cases:
        eval_id = case["eval_id"]
        ticket_raw = case["ticket_raw"]
        expected_intent = case["expected_intent"]
        expected_hostname = case["expected_hostname"]

        print(f"\n[Evaluating Case: {eval_id}] -> {ticket_raw[:60]}...")

        res = predict_l1_agent(case)
        matched_intent = res["intent"]
        hostname = res["hostname"]

        clean_matched = matched_intent.lower().replace("_", " ").strip()
        clean_expected = expected_intent.lower().replace("_", " ").strip()
        intent_match = (clean_expected in clean_matched) or (clean_matched in clean_expected)
        host_match = (hostname.lower() == expected_hostname.lower())

        judge_prompt = f"""You are an AI Eval Judge scoring an automated L1 Support System.
Evaluate:
- Ticket: {ticket_raw}
- Classified Intent: {matched_intent} (Expected: {expected_intent})
- Target Host: {hostname} (Expected: {expected_hostname})

Output valid JSON: {{"passed": true, "reasoning": "Explanation"}}
"""
        try:
            judge_res = llm_judge.invoke(judge_prompt)
            content = judge_res.content if hasattr(judge_res, "content") else str(judge_res)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            eval_res = json.loads(content)
        except Exception:
            eval_res = {"passed": intent_match and host_match, "reasoning": "Assertion check"}

        is_passed = eval_res.get("passed", False) or (intent_match and host_match)
        if is_passed:
            passed_count += 1
            print(f"  [PASS] Intent: '{matched_intent}' | Host: '{hostname}' | Score: 100%")
        else:
            print(f"  [FAIL] Intent: '{matched_intent}' (Expected: '{expected_intent}') | Host: '{hostname}' | Notes: {eval_res.get('reasoning')}")

    print("\n==================================================")
    print(f"BENCHMARK SCORE: {passed_count}/{total_count} PASSED ({(passed_count/total_count)*100:.1f}%)")
    print("==================================================\n")


if __name__ == "__main__":
    run_langsmith_evals()
