"""
Interactive Security Engine Tester
==================================
Run this script to interactively test and demonstrate:
1. Shell Command Injection Guard (enforce_entity_double_quotes)
2. Canonical v2 HMAC-SHA256 Playbook Integrity & Pre-Execution Verification
3. Data Loss Prevention (redact_sensitive_dlp)
4. SSRF Network Defense with Comprehensive CIDR Blocking
5. Fail-Closed Multimodal Image Security
"""

import os
import tempfile
import yaml

# Allow test-only dev key for demo execution
if not os.getenv("ELONE_PLAYBOOK_SIGNING_KEY"):
    os.environ["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"

# pyrefly: ignore [missing-import]
from core.security import (
    enforce_entity_double_quotes,
    compute_playbook_hmac,
    verify_playbook_hmac,
    verify_playbook_before_execution,
    redact_sensitive_dlp,
    is_safe_external_url,
    clean_unicode_and_zero_width,
    validate_and_sanitize_image_bytes,
)

def test_command_quotation_guard():
    print("\n" + "="*70)
    print(" 1. TESTING COMMAND INJECTION QUOTATION ENFORCEMENT")
    print("="*70)
    
    test_commands = [
        "taskkill /F /IM {{entities.application_name}}.exe",
        "Test-Connection -ComputerName {{entities.hostname}} -Count 2",
        'Get-Process -Name "{{entities.process_name}}"',  # Already quoted
        "Stop-Service -Name {{entities.service_name}} -Force",
        'reg query "HKLM\\Software\\{{entities.app_name}}" /v Debugger',
    ]

    for idx, cmd in enumerate(test_commands, 1):
        sanitized = enforce_entity_double_quotes(cmd)
        print(f"\n[Test Case {idx}]")
        print(f"  Raw Input Command:       {cmd}")
        print(f"  Sanitized Safe Command:  {sanitized}")
        
    print("\n[VULNERABILITY SIMULATION]")
    malicious_input = "calc.exe & del /q C:\\*"
    unquoted_cmd = f"taskkill /F /IM {malicious_input}"
    quoted_cmd = f'taskkill /F /IM "{malicious_input}"'
    print(f"  Attacker Input:          {malicious_input}")
    print(f"  If Unquoted (DANGEROUS): {unquoted_cmd}  --> (Executes two commands!)")
    print(f"  If Quoted (SAFE):        {quoted_cmd}  --> (Treated as 1 literal string!)")


def test_hmac_tampering_detection():
    print("\n" + "="*70)
    print(" 2. TESTING PLAYBOOK HMAC-SHA256 (CANONICAL v2 & PRE-EXECUTION HOOK)")
    print("="*70)

    # 1. Original approved playbook frontmatter
    approved_frontmatter = {
        "sop_id": "SOP-SEC-001",
        "title": "Application Killer",
        "platform": "system",
        "category": "software",
        "target_os": "windows",
        "steps": [
            {"step_number": 1, "command": 'tasklist | findstr "{{entities.application_name}}"'},
            {"step_number": 2, "command": 'taskkill /F /IM "{{entities.application_name}}.exe"'}
        ]
    }

    print("Step 1: AI generated and approved the canonical frontmatter:")
    print(f"  SOP ID: {approved_frontmatter['sop_id']} | OS: {approved_frontmatter['target_os']}")
    for s in approved_frontmatter["steps"]:
        print(f"  - Step {s['step_number']}: {s['command']}")

    # 2. Compute cryptographic digital signature over canonical frontmatter
    approved_frontmatter["integrity_version"] = "v2"
    digital_stamp = compute_playbook_hmac(approved_frontmatter)
    approved_frontmatter["integrity_hmac_sha256"] = digital_stamp

    print(f"\nStep 2: Stamped Canonical v2 HMAC-SHA256 signature:")
    print(f"  integrity_version:     v2")
    print(f"  integrity_hmac_sha256: {digital_stamp}")

    # 3. Save to a temporary markdown playbook file
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        yaml_content = yaml.dump(approved_frontmatter, sort_keys=False)
        f.write(f"---\n{yaml_content}---\n\n# Execution Steps\n...")
        tmp_playbook_path = f.name

    try:
        # 4. Pre-execution verification on authentic file
        is_valid, reason, _ = verify_playbook_before_execution(tmp_playbook_path)
        print(f"\nStep 3: Pre-Execution Verification on Authentic Playbook:")
        print(f"  Result: {'[PASSED] Playbook is authentic and untampered!' if is_valid else '[FAILED]'}")

        # 5. Simulate an attacker altering the playbook file on disk (inject backdoor command)
        print(f"\nStep 4: Attack Simulation — Unauthorized user alters Step 2 on disk:")
        with open(tmp_playbook_path, "r", encoding="utf-8") as f:
            tampered_content = f.read().replace('taskkill /F /IM', 'net user backdoor Pass123! /add && taskkill')
        with open(tmp_playbook_path, "w", encoding="utf-8") as f:
            f.write(tampered_content)

        # 6. Pre-execution verification must reject the tampered file
        is_valid_after_tamper, tamper_reason, _ = verify_playbook_before_execution(tmp_playbook_path)
        print(f"\nStep 5: Pre-Execution Verification on Tampered Playbook:")
        if not is_valid_after_tamper:
            print("  Result: [REJECTED] Security Alarm! Tampering Detected!")
            print(f"  Action: Execution aborted immediately! ({tamper_reason})")
        else:
            print("  Result: [FAILED] Tampering went undetected.")
    finally:
        if os.path.exists(tmp_playbook_path):
            os.remove(tmp_playbook_path)


def test_dlp_and_ssrf():
    print("\n" + "="*70)
    print(" 3. TESTING DLP (PASSWORDS & API KEYS) & EXPANDED SSRF DEFENSE")
    print("="*70)

    sample_sop_text = (
        "Default setup password: Welcome@2026! and OpenAI key sk-proj-1234567890abcdef1234567890.\n"
        "Contact engineer at john.smith@internalcorp.net or call +1-555-019-9921."
    )
    redacted_text, stats = redact_sensitive_dlp(sample_sop_text)
    print(f"Raw Text:\n{sample_sop_text}\n")
    print(f"DLP Masked Text:\n{redacted_text}\n")
    print(f"DLP Masking Stats: {stats}")

    print("\nTesting SSRF URL & IP Blocking:")
    urls = [
        ("http://169.254.169.254/latest/meta-data/", "Cloud Metadata IP"),
        ("http://127.0.0.1:8000/admin", "Loopback / Localhost"),
        ("http://192.168.1.1/router", "RFC1918 Private LAN"),
        ("http://100.64.0.1/status", "Carrier-Grade NAT (CGNAT)"),
        ("http://224.0.0.1/multicast", "Multicast IP Range"),
        ("http://198.18.0.1/bench", "Benchmarking Subnet"),
        ("https://learn.microsoft.com/en-us/powershell/", "Legitimate Public Website"),
    ]
    for u, label in urls:
        is_safe, err = is_safe_external_url(u)
        status = "[ALLOWED]" if is_safe else f"[BLOCKED] ({err})"
        print(f"  {u} ({label}) --> {status}")


def test_fail_closed_image_security():
    print("\n" + "="*70)
    print(" 4. TESTING FAIL-CLOSED MULTIMODAL IMAGE SECURITY")
    print("="*70)

    fake_bytes = b"MALFORMED_NON_IMAGE_BINARY_DATA_STREAM"
    is_valid, err, _, _ = validate_and_sanitize_image_bytes(fake_bytes, "image/png")
    print(f"  Test: Corrupted/Disguised Binary Stream")
    print(f"  Result: {'[BLOCKED - FAIL-CLOSED]' if not is_valid else '[FAILED - FAILED OPEN]'}")
    print(f"  Reason: {err}")


if __name__ == "__main__":
    test_command_quotation_guard()
    test_hmac_tampering_detection()
    test_dlp_and_ssrf()
    test_fail_closed_image_security()
    print("\n" + "="*70)
    print(" ALL INTERACTIVE DEMO TESTS COMPLETED SUCCESSFULLY!")
    print("="*70 + "\n")
