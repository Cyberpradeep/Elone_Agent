"""
CLI Diagnostic Tool: Test LLM Provider Connectivity
===================================================
Run this script to test all configured LLM providers (Gemini, Mistral, Groq, Z.ai GLM, NVIDIA).

Usage:
  python backend/test_llm_providers.py
"""

import os
import sys
import time
from dotenv import load_dotenv

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT_DIR, ".env"))
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.llm_config import (
    ROLE_PROVIDER_MAP,
    _BUILDERS,
    print_active_models,
)


def test_provider(name: str, builder_key: str, default_model: str, env_vars: list[str]):
    print(f"\n--- Testing {name} ({default_model}) ---")
    
    # Check environment variable
    found_var = None
    for var in env_vars:
        if os.environ.get(var):
            found_var = var
            break
            
    if not found_var:
        print(f"  [SKIPPED] None of {env_vars} are set in .env")
        return False

    masked = os.environ[found_var][:6] + "..." + os.environ[found_var][-4:] if len(os.environ[found_var]) > 10 else "***"
    print(f"  Using key from: {found_var} ({masked})")

    try:
        builder = _BUILDERS[builder_key]
        client = builder(default_model, temperature=0.1)
        
        start = time.time()
        response = client.invoke("Respond with exactly: 'OK'")
        elapsed = time.time() - start
        
        reply_text = response.content if hasattr(response, "content") else str(response)
        if isinstance(reply_text, list):
            reply_text = " ".join(str(item) for item in reply_text)
            
        print(f"  [SUCCESS] Latency: {elapsed:.2f}s | Response: {reply_text.strip()[:60]}")
        return True
    except Exception as e:
        print(f"  [FAILED] Error: {e}")
        return False


def main():
    print_active_models()
    
    results = {}
    
    # 1. Groq
    groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    results["Groq"] = test_provider(
        name="Groq",
        builder_key="groq",
        default_model=groq_model,
        env_vars=["GROQ_API_KEY", "GROQ_API_KEY_SUMMARIZATION"],
    )
    
    # 2. Z.ai / GLM (glm-4.7-flash with auto-fallback to glm-4.5-flash)
    results["Z.ai (GLM)"] = test_provider(
        name="Z.ai (GLM)",
        builder_key="zai",
        default_model="glm-4.7-flash",
        env_vars=["ZAI_API_KEY", "GLM_API_KEY", "ZHIPUAI_API_KEY"],
    )
    
    # 3. Google Gemini
    results["Google Gemini"] = test_provider(
        name="Google Gemini",
        builder_key="gemini",
        default_model="gemini-2.5-flash",
        env_vars=["GOOGLE_API_KEY"],
    )
    
    # 4. Mistral AI
    results["Mistral AI"] = test_provider(
        name="Mistral AI",
        builder_key="mistral",
        default_model="mistral-small-latest",
        env_vars=["MISTRAL_API_KEY"],
    )

    print("\n" + "=" * 65)
    print("  PROVIDER TEST SUMMARY")
    print("=" * 65)
    for prov, status in results.items():
        state_str = "PASS / READY" if status else "NOT CONFIGURED / FAILED"
        print(f"  • {prov:20s}: {state_str}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
