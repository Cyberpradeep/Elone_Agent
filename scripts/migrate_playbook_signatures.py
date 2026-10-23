"""
Playbook Signature Migration Script (v1 / Unsigned -> v2 Canonical Frontmatter)
================================================================================
Upgrades all trusted existing playbooks in knowledge_base/sops/ to the canonical
v2 HMAC-SHA256 digital signature format.

Usage:
    python scripts/migrate_playbook_signatures.py
"""

import os
import sys
import yaml

# Add repository root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Set test-only dev key flag if ELONE_PLAYBOOK_SIGNING_KEY not in environment
if not os.getenv("ELONE_PLAYBOOK_SIGNING_KEY"):
    os.environ["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"

from core.security import compute_playbook_hmac, verify_playbook_before_execution

SOPS_DIR = os.path.join(BASE_DIR, "knowledge_base", "sops")


def migrate_all_playbooks():
    print("=" * 70)
    print(" PLAYBOOK INTEGRITY MIGRATION: UPGRADING TO CANONICAL v2 HMAC SIGNATURES")
    print("=" * 70)

    count = 0
    updated = 0

    for root, _, files in os.walk(SOPS_DIR):
        for file in files:
            if file.endswith(".md") and file.lower() != "index.md":
                count += 1
                playbook_path = os.path.join(root, file)
                rel_path = os.path.relpath(playbook_path, BASE_DIR)

                with open(playbook_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.startswith("---"):
                    print(f"[-] Skipping non-frontmatter file: {rel_path}")
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    print(f"[-] Skipping malformed file: {rel_path}")
                    continue

                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except Exception as e:
                    print(f"[!] YAML parse error in {rel_path}: {e}")
                    continue

                sop_id = frontmatter.get("sop_id", os.path.splitext(file)[0])

                # Set v2 canonical integrity version and compute stamp
                frontmatter["integrity_version"] = "v2"
                new_hmac = compute_playbook_hmac(frontmatter)
                frontmatter["integrity_hmac_sha256"] = new_hmac

                # Render back to markdown
                new_yaml = yaml.dump(frontmatter, sort_keys=False)
                new_content = f"---\n{new_yaml}---{body}"

                with open(playbook_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # Verify immediately
                is_valid, reason, _ = verify_playbook_before_execution(playbook_path)
                if is_valid:
                    print(f"[+] Migrated and verified: {rel_path} (SOP ID: {sop_id}) -> HMAC: {new_hmac[:16]}...")
                    updated += 1
                else:
                    print(f"[!] Migration verification failed for {rel_path}: {reason}")

    print("\n" + "=" * 70)
    print(f" MIGRATION COMPLETE: {updated}/{count} playbooks upgraded to Canonical v2!")
    print("=" * 70)


if __name__ == "__main__":
    migrate_all_playbooks()
