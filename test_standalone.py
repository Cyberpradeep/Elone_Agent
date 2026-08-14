

import json
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_tool_catalog_loads():
    """Test that the dummy tool catalog loads and has the expected structure."""
    from config.tool_catalog import TOOL_CATALOG, PROVIDER_NAMES, get_tool_names, get_function_names, get_required_inputs

    print("\n[TEST] Tool Catalog Loads...")
    assert len(TOOL_CATALOG) == 4, f"Expected 4 tools, got {len(TOOL_CATALOG)}"
    assert "system" in PROVIDER_NAMES
    assert "auth0" in PROVIDER_NAMES
    assert "mock_support_platform" in PROVIDER_NAMES
    assert "airretailer" in PROVIDER_NAMES

    tool_names = get_tool_names(TOOL_CATALOG)
    assert "system_operations" in tool_names
    assert "auth0_user_management" in tool_names
    assert "l1_testing_platform_api" in tool_names
    assert "airretailer_vpn_rdp_tools" in tool_names

    # Test function lookup
    auth0_funcs = get_function_names(TOOL_CATALOG, "auth0")
    assert "unlock_user_account" in auth0_funcs
    assert "search_user" in auth0_funcs

    # Test required inputs
    req = get_required_inputs(TOOL_CATALOG, "auth0", "unlock_user_account")
    assert req == ["user_id"], f"Expected ['user_id'], got {req}"

    print("  [PASS] Tool catalog loaded with 3 providers and all functions verified.")


def test_tool_catalog_summary():
    """Test that the formatted tools summary generates correctly."""
    from config.tool_catalog import get_formatted_tools_summary

    print("\n[TEST] Tool Catalog Summary Generation...")
    summary = get_formatted_tools_summary()
    assert len(summary) > 100, "Summary too short"
    assert "unlock_user_account" in summary
    assert "send_email" in summary
    assert "search_users" in summary
    print(f"  [PASS] Generated {len(summary)} chars of tools summary.")


def test_document_parser_txt():
    """Test text file parsing and verify audit logging."""
    print("\n[TEST] Document Parser (TXT)...")
    from core.document_parser import extract_full_text

    sample_path = os.path.join(
        os.path.dirname(__file__),
        "knowledge_base", "_uploads", "sample_account_unlock.txt"
    )
    if not os.path.exists(sample_path):
        print("  [SKIP] Sample file not found.")
        return

    parser_type, text = extract_full_text(sample_path)
    assert parser_type in ("markitdown_parser", "txt_fallback"), f"Unexpected parser: {parser_type}"
    assert "unlock" in text.lower()
    assert "email" in text.lower()
    print(f"  [PASS] Parsed {len(text)} chars using '{parser_type}'.")

    # Verify parser audit log creation
    log_dir = os.path.join(os.path.dirname(__file__), "knowledge_base", "logs", "parser")
    assert os.path.isdir(log_dir), f"Missing parser log directory: {log_dir}"
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    assert len(log_files) > 0, "No parser audit log files found!"
    print(f"  [PASS] Verified {len(log_files)} parser audit log file(s) in knowledge_base/logs/parser/.")



def test_knowledge_base_structure():
    """Test that the knowledge_base directory structure exists."""
    print("\n[TEST] Knowledge Base Structure...")
    base = os.path.join(os.path.dirname(__file__), "knowledge_base")

    dirs = ["_uploads", "sops", "patterns", "logs"]
    for d in dirs:
        path = os.path.join(base, d)
        assert os.path.isdir(path), f"Missing directory: {path}"

    index_path = os.path.join(base, "sops", "index.md")
    assert os.path.isfile(index_path), f"Missing index: {index_path}"

    print(f"  [PASS] All knowledge_base directories exist.")


def test_plan_validator_layer1_empty_steps():
    """Test that Layer 1 catches empty steps."""
    print("\n[TEST] Plan Validator Layer 1 (Empty Steps)...")
    from core.plan_validator import validate_plan_faithfulness_and_linkage

    is_valid, errors = validate_plan_faithfulness_and_linkage("some raw text", {"steps": []})
    assert is_valid is False
    assert any("zero execution steps" in e.lower() for e in errors)
    print(f"  [PASS] Empty steps correctly rejected: {errors[0]}")


def test_plan_validator_layer1_valid_command_step():
    """Test that Layer 1 passes a valid command step."""
    print("\n[TEST] Plan Validator Layer 1 (Valid Command Step)...")
    from core.plan_validator import validate_plan_faithfulness_and_linkage

    plan = {
        "steps": [
            {
                "step_number": 1,
                "step_type": "command",
                "command": "ipconfig /all",
                "output_parse_instruction": "Check if output contains adapter info",
            }
        ]
    }
    # Use short raw text to skip Layer 2 LLM call
    is_valid, errors = validate_plan_faithfulness_and_linkage("short", plan)
    assert is_valid is True
    assert len(errors) == 0
    print(f"  [PASS] Valid command step accepted.")


def test_plan_validator_layer1_missing_command():
    """Test that Layer 1 catches a command step with no command."""
    print("\n[TEST] Plan Validator Layer 1 (Missing Command)...")
    from core.plan_validator import validate_plan_faithfulness_and_linkage

    plan = {
        "steps": [
            {
                "step_number": 1,
                "step_type": "command",
                "command": None,
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("short", plan)
    assert is_valid is False
    assert any("command is empty" in e.lower() for e in errors)
    print(f"  [PASS] Missing command correctly caught: {errors[0]}")


def test_url_extraction_and_scraping():
    """Test URL extraction regex and web content scraping."""
    print("\n[TEST] Link Scraper & URL Extraction...")
    from core.link_scraper import extract_urls_from_markdown, fetch_and_convert_url

    sample_md = """
    Check the [Auth0 Docs](https://auth0.com/docs/api/management/v2) for details.
    Also view http://example.com/guide and ignore https://example.com/image.png
    """
    urls = extract_urls_from_markdown(sample_md)
    assert "https://auth0.com/docs/api/management/v2" in urls
    assert "http://example.com/guide" in urls
    assert not any(u.endswith(".png") for u in urls)
    print(f"  [PASS] Extracted {len(urls)} valid URLs and filtered image asset.")

    # Test HTTP fetch & caching using a reliable domain
    success, text, cache_path = fetch_and_convert_url("http://example.com")
    assert success is True
    assert "Example Domain" in text or "example" in text.lower()
    assert "web_cache" in cache_path
    print(f"  [PASS] Scraped web content cleanly and verified local web cache: {cache_path}.")


def test_prompt_brace_formatting():
    """Test Bug #1 fix: verify prompt .format() yields clean single-braced JSON schema."""
    print("\n[TEST] Prompt Brace Formatting (Bug #1 Fix)...")
    from core.jit_converter import JIT_COT_CONVERTER_PROMPT

    formatted_prompt = JIT_COT_CONVERTER_PROMPT.format(
        available_tools_summary="dummy summary",
        raw_sop_text="dummy text"
    )
    # Assert JSON schema contains single brace '{' and not malformed double brace '{{'
    assert '{\n    "reasoning_chain":' in formatted_prompt
    assert '{{\n    "reasoning_chain":' not in formatted_prompt
    assert '"comm_inputs": {' in formatted_prompt
    assert '"comm_inputs": {{' not in formatted_prompt
    print("  [PASS] Prompt format() produces clean single-braced JSON object schema.")


def test_text_quality_inspector():
    """Test Bug #4 fix: verify text quality inspector catches unreadable binary junk."""
    print("\n[TEST] Text Quality Inspector (Bug #4 Fix)...")
    from core.document_parser import _is_valid_text_quality

    good_text = "SOP: Account Unlock Procedure\nStep 1: Search for user email in support platform."
    bad_binary = "PK\x03\x04\x14\x00\x00\x00\x00\x00W\x11XZ\x09\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0b\x00\x00\x00word/PK"

    assert _is_valid_text_quality(good_text) is True
    assert _is_valid_text_quality(bad_binary) is False
    print("  [PASS] Quality inspector passed valid text and rejected binary junk.")


def test_validation_blocks_disk_write():
    """Test Bug #3 fix: verify convert_raw_sop_to_okf blocks disk write if validation fails."""
    print("\n[TEST] Validation Disk Write Blocking (Bug #3 Fix)...")
    from core.jit_converter import convert_raw_sop_to_okf

    # Create a dummy invalid SOP file where plan validator will fail
    dummy_invalid = os.path.join(os.path.dirname(__file__), "knowledge_base", "_uploads", "dummy_invalid_sop.txt")
    with open(dummy_invalid, "w", encoding="utf-8") as f:
        f.write("Just a random header line with no procedure steps.")

    try:
        try:
            convert_raw_sop_to_okf(dummy_invalid)
            assert False, "Expected convert_raw_sop_to_okf to fail validation and block disk write!"
        except ValueError as val_err:
            assert "validation" in str(val_err).lower() or "blocked" in str(val_err).lower()
            print(f"  [PASS] Disk write successfully blocked on invalid SOP: {val_err}")
    finally:
        if os.path.exists(dummy_invalid):
            os.remove(dummy_invalid)


def test_vlm_inspector_module():
    """Test that VLM inspector helpers operate correctly."""
    from core.vlm_inspector import guess_mime_type, process_sop_images

    print("\n[TEST] VLM Inspector Module...")
    assert guess_mime_type("sample.png") == "image/png"
    assert guess_mime_type("sample.jpg") == "image/jpeg"
    assert guess_mime_type("sample.webp") == "image/webp"

    # Test process_sop_images on non-existent file
    res = process_sop_images("non_existent_file.pdf", "TEST-SLUG")
    assert res == {"summary_text": "", "image_refs": []}
    print("  [PASS] VLM Inspector helper and fallback logic verified.")


def test_okf_pydantic_schema():
    """Test Pydantic schema validation for OKF Playbooks."""
    from core.okf_schema import OKFPlaybookModel, OKFStepModel

    print("\n[TEST] OKF Pydantic Schema Validation...")
    valid_payload = {
        "sop_id": "SOP-TEST-001",
        "title": "Test Playbook",
        "category": "test",
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Run diagnostic ping",
                "step_type": "command",
                "command": "ping 127.0.0.1"
            }
        ]
    }
    model = OKFPlaybookModel.model_validate(valid_payload)
    assert model.sop_id == "SOP-TEST-001"
    assert len(model.steps) == 1
    assert model.steps[0].step_type == "command"

    # Test invalid step_type
    invalid_payload = valid_payload.copy()
    invalid_payload["steps"] = [{"step_number": 1, "sop_step_description": "test", "step_type": "invalid_type"}]
    try:
        OKFPlaybookModel.model_validate(invalid_payload)
        assert False, "Should have raised Pydantic ValidationError"
    except Exception as e:
        assert "Invalid step_type" in str(e)
    print("  [PASS] Pydantic schema model validation verified.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    """Run all tests and print summary."""
    tests = [
        test_tool_catalog_loads,
        test_tool_catalog_summary,
        test_document_parser_txt,
        test_knowledge_base_structure,
        test_plan_validator_layer1_empty_steps,
        test_plan_validator_layer1_valid_command_step,
        test_plan_validator_layer1_missing_command,
        test_url_extraction_and_scraping,
        test_prompt_brace_formatting,
        test_text_quality_inspector,
        test_validation_blocks_disk_write,
        test_vlm_inspector_module,
        test_okf_pydantic_schema,
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  SOP Ingestion Pipeline — Standalone Tests")
    print("=" * 60)

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
