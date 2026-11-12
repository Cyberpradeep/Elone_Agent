"""
Comprehensive Security, Authentication, Lean 4-Role RBAC, Tenant/Clearance Isolation,
Cookie/CSRF, OIDC & CORS Verification Suite (P1-1 / C2).
"""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from auth.config import (  # noqa: E402
    AuthConfigurationError,
    get_jwt_secret,
    parse_allowed_origins,
    reset_dev_ephemeral_secret_for_tests,
)
from auth.models import (  # noqa: E402
    AuthPrincipal,
    ROLE_ADMIN,
    ROLE_AGENT,
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
    ROLE_SET,
    compute_capabilities,
)
from auth.passwords import hash_password, verify_dummy_password, verify_password  # noqa: E402
from auth.tokens import (  # noqa: E402
    TokenValidationError,
    create_access_token,
    decode_access_token,
    decode_local_token,
    revocation_store,
)
from auth.user_store import UserStore  # noqa: E402


class TestAuthCoreUnits(unittest.TestCase):
    def test_01_fail_closed_jwt_secret_and_cors_allowlist(self):
        reset_dev_ephemeral_secret_for_tests()
        clean_env = dict(os.environ)
        clean_env.pop("ELONE_JWT_SECRET", None)
        clean_env.pop("ELONE_ALLOW_INSECURE_DEV_KEY", None)

        with patch.dict(os.environ, clean_env, clear=True):
            with self.assertRaises(AuthConfigurationError):
                get_jwt_secret()

        with patch.dict(os.environ, {**clean_env, "ELONE_JWT_SECRET": "too_short"}, clear=True):
            with self.assertRaises(AuthConfigurationError):
                get_jwt_secret()

        gen_secret = secrets.token_urlsafe(32)
        with patch.dict(os.environ, {**clean_env, "ELONE_JWT_SECRET": gen_secret}, clear=True):
            self.assertEqual(get_jwt_secret(), gen_secret)

        for bad_origins in ("*", "http://localhost:8000, *", "", "   "):
            with self.assertRaises(AuthConfigurationError):
                parse_allowed_origins(bad_origins)

        self.assertEqual(
            parse_allowed_origins(" https://app.example.com/ , http://127.0.0.1:8000/ "),
            ["https://app.example.com", "http://127.0.0.1:8000"],
        )

    def test_02_scrypt_password_hashing_and_constant_time_verify(self):
        pw_a = secrets.token_urlsafe(16)
        pw_b = secrets.token_urlsafe(16)
        h1 = hash_password(pw_a)
        h2 = hash_password(pw_a)
        self.assertTrue(h1.startswith("scrypt$16384$8$1$"))
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password(pw_a, h1))
        self.assertFalse(verify_password(pw_b, h1))
        self.assertFalse(verify_password(pw_a, "not-a-valid-hash"))
        verify_dummy_password(pw_b)

    def test_03_principal_invariants_and_lean_4_role_model(self):
        self.assertEqual(
            ROLE_SET,
            frozenset({ROLE_PROCESS_OWNER, ROLE_SECURITY_REVIEWER, ROLE_ADMIN, ROLE_AGENT}),
        )

        # Agent cannot coexist with human roles
        with self.assertRaises(ValueError):
            AuthPrincipal(
                sub="usr_mix",
                identity="mix@corp.example",
                display_name="Mix",
                roles=["agent", "process_owner"],
                tenant_id="tn_northwind",
                clearance="L1",
                actor_type="human",
            )

        # Path traversal tenant rejected
        with self.assertRaises(ValueError):
            AuthPrincipal(
                sub="usr_trav",
                identity="trav@corp.example",
                display_name="Trav",
                roles=["process_owner"],
                tenant_id="../etc",
                clearance="L1",
                actor_type="human",
            )

        # Persona default clearance cannot be exceeded
        with self.assertRaises(ValueError):
            AuthPrincipal(
                sub="agt_over",
                identity="svc_over",
                display_name="svc_over",
                roles=["agent"],
                tenant_id="tn_northwind",
                clearance="L3",
                actor_type="agent",
                agent_id="svc_over",
                agent_persona="service_desk_agent",
            )

        po_caps = compute_capabilities(["process_owner"], "L1", "human")
        self.assertTrue(po_caps["can_delete_sop"])
        self.assertTrue(po_caps["can_upload"])
        self.assertFalse(po_caps["can_manage_config"])
        self.assertFalse(po_caps["can_view_logs"])
        self.assertFalse(po_caps["can_view_incidents"])
        self.assertFalse(po_caps["can_review_l2_l3"])

        sec_caps = compute_capabilities(["security_reviewer"], "L2", "human")
        self.assertFalse(sec_caps["can_delete_sop"])
        self.assertTrue(sec_caps["can_view_logs"])
        self.assertTrue(sec_caps["can_view_telemetry"])
        self.assertTrue(sec_caps["can_view_incidents"])
        self.assertTrue(sec_caps["can_review_l2_l3"])
        self.assertFalse(sec_caps["can_manage_config"])

        adm_caps = compute_capabilities(["admin"], "L3", "human")
        self.assertTrue(adm_caps["can_manage_config"])
        self.assertTrue(adm_caps["can_manage_users"])
        self.assertTrue(adm_caps["can_delete_sop"])
        self.assertTrue(adm_caps["can_review_l2_l3"])

        agt_caps = compute_capabilities(["agent"], "L2", "agent")
        self.assertFalse(agt_caps["can_upload"])
        self.assertFalse(agt_caps["can_delete_sop"])
        self.assertFalse(agt_caps["can_review_l0_l1"])
        self.assertTrue(agt_caps["can_search_downstream"])

    def test_04_jwt_tampering_wrong_claims_expiration_and_revocation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_a = secrets.token_urlsafe(32)
            secret_b = secrets.token_urlsafe(32)
            rev_path = os.path.join(tmpdir, "_auth", "revoked_tokens.json")
            env_patch = {
                "ELONE_AUTH_MODE": "local",
                "ELONE_JWT_SECRET": secret_a,
                "ELONE_REVOKED_TOKENS_PATH": rev_path,
                "ELONE_JWT_ISSUER": "elone-governance-hub",
                "ELONE_JWT_AUDIENCE": "elone-api",
            }
            with patch.dict(os.environ, env_patch):
                p = AuthPrincipal(
                    sub="usr_tok",
                    identity="alice@northwind.example",
                    display_name="Alice",
                    roles=["process_owner"],
                    tenant_id="tn_northwind",
                    clearance="L1",
                    actor_type="human",
                )
                tok, jti, _ = create_access_token(p, ttl_seconds=120)
                decoded = decode_access_token(tok)
                self.assertEqual(decoded.identity, "alice@northwind.example")
                self.assertEqual(decoded.jti, jti)

                # Wrong signature
                with self.assertRaises(TokenValidationError):
                    decode_local_token(tok, secret=secret_b)

                # Expired token
                now = int(time.time())
                expired_tok = jwt.encode(
                    {
                        "sub": p.sub,
                        "identity": p.identity,
                        "roles": ["process_owner"],
                        "tenant_id": "tn_northwind",
                        "clearance": "L1",
                        "actor_type": "human",
                        "jti": "tok_exp",
                        "iss": "elone-governance-hub",
                        "aud": "elone-api",
                        "iat": now - 120,
                        "exp": now - 10,
                    },
                    secret_a,
                    algorithm="HS256",
                )
                with self.assertRaises(TokenValidationError) as ctx_exp:
                    decode_access_token(expired_tok)
                self.assertEqual(ctx_exp.exception.error_code, "token_expired")

                # Wrong audience & wrong issuer
                bad_aud = jwt.encode(
                    {
                        "sub": p.sub,
                        "identity": p.identity,
                        "roles": ["process_owner"],
                        "tenant_id": "tn_northwind",
                        "clearance": "L1",
                        "actor_type": "human",
                        "jti": "tok_aud",
                        "iss": "elone-governance-hub",
                        "aud": "wrong-aud",
                        "iat": now,
                        "exp": now + 60,
                    },
                    secret_a,
                    algorithm="HS256",
                )
                with self.assertRaises(TokenValidationError):
                    decode_access_token(bad_aud)

                # Revocation persistence
                revocation_store.revoke(jti, now + 120)
                with self.assertRaises(TokenValidationError) as ctx_rev:
                    decode_access_token(tok)
                self.assertEqual(ctx_rev.exception.error_code, "token_revoked")

    def test_05_oidc_rs256_jwks_mapping_and_hybrid_mode(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        class _FakeSigningKey:
            key = public_key

        class _FakeJWKClient:
            def get_signing_key_from_jwt(self, _tok):
                return _FakeSigningKey()

        now = int(time.time())
        oidc_claims = {
            "sub": "idp_usr_99",
            "email": "sso.reviewer@acme.example",
            "name": "SSO Sec Reviewer",
            "groups": ["elone-sec-group"],
            "org_tenant": "tn_acme",
            "clearance": "L2",
            "iss": "https://idp.acme.example",
            "aud": "elone-api",
            "iat": now,
            "exp": now + 300,
        }
        oidc_token = jwt.encode(oidc_claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})
        local_secret = secrets.token_urlsafe(32)

        with tempfile.TemporaryDirectory() as tmpdir:
            env_patch = {
                "ELONE_AUTH_MODE": "hybrid",
                "ELONE_JWT_SECRET": local_secret,
                "ELONE_JWT_ISSUER": "elone-governance-hub",
                "ELONE_JWT_AUDIENCE": "elone-api",
                "ELONE_OIDC_JWKS_URL": "https://idp.acme.example/.well-known/jwks.json",
                "ELONE_OIDC_ISSUER": "https://idp.acme.example",
                "ELONE_OIDC_AUDIENCE": "elone-api",
                "ELONE_OIDC_TENANT_CLAIM": "org_tenant",
                "ELONE_OIDC_ROLES_CLAIM": "groups",
                "ELONE_OIDC_ROLE_MAP": json.dumps({"elone-sec-group": "security_reviewer"}),
                "ELONE_REVOKED_TOKENS_PATH": os.path.join(tmpdir, "revoked.json"),
            }
            with patch.dict(os.environ, env_patch):
                with patch("auth.tokens._get_jwk_client", return_value=_FakeJWKClient()):
                    principal = decode_access_token(oidc_token)
                    self.assertEqual(principal.identity, "sso.reviewer@acme.example")
                    self.assertEqual(principal.roles, ["security_reviewer"])
                    self.assertEqual(principal.tenant_id, "tn_acme")
                    self.assertEqual(principal.clearance, "L2")
                    self.assertEqual(principal.actor_type, "human")

                    # Hybrid mode must simultaneously accept local HS256 agent tokens
                    agent_p = AuthPrincipal(
                        sub="agt_hyb_1",
                        identity="hyb_bot",
                        display_name="Hybrid Bot",
                        roles=["agent"],
                        tenant_id="tn_acme",
                        clearance="L1",
                        actor_type="agent",
                        agent_id="hyb_bot",
                    )
                    agent_tok, _, _ = create_access_token(agent_p, ttl_seconds=120)
                    decoded_agent = decode_access_token(agent_tok)
                    self.assertEqual(decoded_agent.actor_type, "agent")
                    self.assertEqual(decoded_agent.roles, ["agent"])

    def test_06_auth_cli_and_user_store_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            synth_pw = f"TestPw-{secrets.token_urlsafe(12)}!"
            env = {
                **os.environ,
                "ELONE_KB_DIR": tmpdir,
                "ELONE_JWT_SECRET": secrets.token_urlsafe(32),
            }
            c_proc = subprocess.run(
                [
                    sys.executable, "-m", "auth.cli", "create-user",
                    "--username", "cli_alice",
                    "--identity", "cli.alice@northwind.example",
                    "--role", "process_owner",
                    "--tenant", "tn_northwind",
                    "--clearance", "L1",
                    "--password", synth_pw,
                ],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(c_proc.returncode, 0, msg=c_proc.stderr)
            created = json.loads(c_proc.stdout)
            self.assertNotIn("password_hash", created)
            self.assertEqual(created["roles"], ["process_owner"])

            l_proc = subprocess.run(
                [sys.executable, "-m", "auth.cli", "list-users", "--tenant", "tn_northwind"],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(l_proc.returncode, 0, msg=l_proc.stderr)
            users = json.loads(l_proc.stdout)
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["identity"], "cli.alice@northwind.example")

            t_proc = subprocess.run(
                [
                    sys.executable, "-m", "auth.cli", "issue-agent-token",
                    "--tenant", "tn_northwind",
                    "--clearance", "L1",
                    "--agent-id", "desk_bot_1",
                    "--persona", "service_desk_agent",
                ],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(t_proc.returncode, 0, msg=t_proc.stderr)
            tok_info = json.loads(t_proc.stdout)
            with patch.dict(os.environ, {"ELONE_JWT_SECRET": env["ELONE_JWT_SECRET"], "ELONE_KB_DIR": tmpdir}):
                dec = decode_access_token(tok_info["access_token"])
                self.assertEqual(dec.roles, ["agent"])
                self.assertEqual(dec.actor_type, "agent")
                self.assertEqual(dec.agent_persona, "service_desk_agent")
                self.assertEqual(dec.tenant_id, "tn_northwind")

            d_proc = subprocess.run(
                [sys.executable, "-m", "auth.cli", "disable-user", "--username", "cli_alice"],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(d_proc.returncode, 0, msg=d_proc.stderr)
            self.assertTrue(json.loads(d_proc.stdout)["disabled"])


_SUBPROCESS_SECURITY_DRIVER = r'''
import os
import sys
import json
import secrets
from unittest.mock import patch
from starlette.testclient import TestClient

backend_dir = os.environ["ELONE_BACKEND_DIR"]
kb_dir = os.environ["ELONE_KB_DIR"]
sys.path.insert(0, backend_dir)

import config.settings as cfg_mod
cfg_mod.SETTINGS_JSON_PATH = os.path.join(kb_dir, "settings.json")
cfg_mod.CONFIG_FILE_PATH = os.path.join(kb_dir, "pipeline_config.json")

import server
import api.context as ctx
import api.routes_ingestion as routes_ingestion
from auth.user_store import user_store, login_rate_limiter
from auth.tokens import create_access_token

app = server.app
client = TestClient(app)

def mk_pw():
    return f"SecPw-{secrets.token_urlsafe(10)}!9"

# ---------------------------------------------------------------------------
# 1. Public vs Unauthenticated 401 checks
# ---------------------------------------------------------------------------
h = client.get("/api/health")
assert h.status_code == 200, h.text
hj = h.json()
assert hj["status"] == "healthy" and hj["auth_enabled"] is True
assert "jwt" not in json.dumps(hj).lower()

protected_calls = [
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/users"),
    ("POST", "/api/auth/users"),
    ("GET", "/api/overview"),
    ("GET", "/api/scheduler"),
    ("GET", "/api/tools"),
    ("GET", "/api/telemetry"),
    ("GET", "/api/logs"),
    ("GET", "/api/logs/sample.log"),
    ("POST", "/api/security/test"),
    ("GET", "/api/uploads"),
    ("POST", "/api/uploads/upload"),
    ("POST", "/api/uploads/ingest"),
    ("POST", "/api/uploads/ingest/cancel"),
    ("POST", "/api/uploads/scan"),
    ("POST", "/api/plan-preview"),
    ("GET", "/api/governance/jobs"),
    ("GET", "/api/governance/jobs/job_1"),
    ("GET", "/api/governance/review-tasks"),
    ("POST", "/api/governance/review-tasks/RT-1/decision"),
    ("POST", "/api/governance/sops/SOP-1/publish"),
    ("GET", "/api/governance/sops/SOP-1/canonical"),
    ("PUT", "/api/governance/sops/SOP-1/canonical"),
    ("POST", "/api/governance/sops/SOP-1/sync-playbook"),
    ("GET", "/api/governance/drafts/SOP-1"),
    ("PUT", "/api/governance/drafts/SOP-1/steps"),
    ("PUT", "/api/governance/drafts/SOP-1/canonical"),
    ("POST", "/api/governance/downstream/search"),
    ("GET", "/api/governance/downstream/stats"),
    ("GET", "/api/governance/incidents"),
    ("GET", "/api/config"),
    ("POST", "/api/config"),
    ("PUT", "/api/config"),
    ("GET", "/api/sops"),
    ("GET", "/api/sops/SOP-1"),
    ("DELETE", "/api/sops/SOP-1"),
    ("POST", "/api/sops/SOP-1/verify"),
]
for method, path in protected_calls:
    r = client.request(method, path)
    assert r.status_code == 401, f"Expected 401 on {method} {path}, got {r.status_code}: {r.text}"
    assert r.json().get("error_code") == "auth_required", r.json()

# ---------------------------------------------------------------------------
# 2. CORS Lockdown checks
# ---------------------------------------------------------------------------
ok_cors = client.options(
    "/api/auth/login",
    headers={
        "Origin": "http://127.0.0.1:8000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token",
    },
)
assert ok_cors.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000", dict(ok_cors.headers)
assert ok_cors.headers.get("access-control-allow-credentials") == "true"

bad_cors = client.options(
    "/api/auth/login",
    headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
    },
)
assert "access-control-allow-origin" not in bad_cors.headers, dict(bad_cors.headers)

# ---------------------------------------------------------------------------
# 3. Provision Multi-Tenant Accounts (Lean 4-Role Model)
# ---------------------------------------------------------------------------
accounts = {
    "admin_a": (mk_pw(), ["admin"], "tn_northwind", "L3"),
    "alice_a": (mk_pw(), ["process_owner"], "tn_northwind", "L1"),
    "bob_a": (mk_pw(), ["process_owner"], "tn_northwind", "L1"),
    "po_l2_a": (mk_pw(), ["process_owner"], "tn_northwind", "L2"),
    "sec_a": (mk_pw(), ["security_reviewer"], "tn_northwind", "L2"),
    "agent_a_l1": (None, ["agent"], "tn_northwind", "L1"),
    "agent_a_l2": (None, ["agent"], "tn_northwind", "L2"),
    "admin_b": (mk_pw(), ["admin"], "tn_globex", "L3"),
    "carol_b": (mk_pw(), ["process_owner"], "tn_globex", "L2"),
    "sec_b": (mk_pw(), ["security_reviewer"], "tn_globex", "L3"),
    "agent_b_l3": (None, ["agent"], "tn_globex", "L3"),
}
recs = {}
tokens = {}
hdrs = {}
for uname, (pw, roles, tenant, clr) in accounts.items():
    ident = f"{uname}@{tenant}.example" if roles != ["agent"] else uname
    rec = user_store.create_user(
        username=uname,
        password=pw,
        roles=roles,
        tenant_id=tenant,
        clearance=clr,
        identity=ident,
        display_name=uname,
        agent_persona="service_desk_agent" if uname == "agent_a_l1" else None,
    )
    recs[uname] = rec
    tok, _, _ = create_access_token(rec, ttl_seconds=600)
    tokens[uname] = tok
    hdrs[uname] = {"Authorization": f"Bearer {tok}"}

# ---------------------------------------------------------------------------
# 4. Login Lockout (429), Cookie + CSRF Double-Submit, Logout Revocation
# ---------------------------------------------------------------------------
bad_pw = mk_pw()
for _ in range(5):
    rf = client.post("/api/auth/login", json={"username": "alice_a", "password": bad_pw})
    assert rf.status_code == 401
r429 = client.post("/api/auth/login", json={"username": "alice_a", "password": bad_pw})
assert r429.status_code == 429, f"Expected 429 lockout, got {r429.status_code}"
assert int(r429.headers.get("retry-after", "0")) >= 1
login_rate_limiter.reset_all_for_tests()

# Timing-safe unknown user login still 401
assert client.post("/api/auth/login", json={"username": "no_such_user", "password": bad_pw}).status_code == 401

# Browser cookie login + CSRF test using separate TestClient session
cookie_client = TestClient(app)
r_login = cookie_client.post("/api/auth/login", json={"username": "alice_a", "password": accounts["alice_a"][0]})
assert r_login.status_code == 200, r_login.text
csrf_tok = r_login.json()["csrf_token"]
assert r_login.cookies.get("elone_csrf") == csrf_tok
assert "elone_session" in r_login.cookies

# Read works with cookie
r_me = cookie_client.get("/api/auth/me")
assert r_me.status_code == 200
assert r_me.json()["user"]["identity"] == "alice_a@tn_northwind.example"

# Cookie POST WITHOUT X-CSRF-Token -> 403 csrf_invalid
r_nocsrf = cookie_client.post("/api/security/test", json={"payload": "Get-Process", "type": "ast"})
assert r_nocsrf.status_code == 403 and r_nocsrf.json()["error_code"] == "csrf_invalid", r_nocsrf.text

# Cookie POST WITH matching X-CSRF-Token -> 200
r_csrf = cookie_client.post(
    "/api/security/test",
    headers={"X-CSRF-Token": csrf_tok},
    json={"payload": "Get-Process", "type": "ast"},
)
assert r_csrf.status_code == 200

# Logout with cookie + CSRF revokes token jti
saved_cookie_jwt = cookie_client.cookies.get("elone_session")
r_out = cookie_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_tok})
assert r_out.status_code == 200
assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {saved_cookie_jwt}"}).status_code == 401
assert cookie_client.get("/api/auth/me").status_code == 401

# Disabled user rejected immediately even with previously minted JWT
temp_pw = mk_pw()
temp_u = user_store.create_user(username="temp_dis", password=temp_pw, roles=["process_owner"], tenant_id="tn_northwind", clearance="L1")
temp_tok, _, _ = create_access_token(temp_u, ttl_seconds=300)
user_store.update_user(temp_u.sub, disabled=True)
r_dis = client.get("/api/auth/me", headers={"Authorization": f"Bearer {temp_tok}"})
assert r_dis.status_code == 401 and r_dis.json()["error_code"] == "account_disabled", r_dis.text

# ---------------------------------------------------------------------------
# 5. Admin-only /api/config & /api/auth/users*
# ---------------------------------------------------------------------------
for who in ("alice_a", "sec_a", "agent_a_l1"):
    assert client.get("/api/config", headers=hdrs[who]).status_code == 403
    assert client.post("/api/config", headers=hdrs[who], json={"execution_mode": "auto"}).status_code == 403
    assert client.put("/api/config", headers=hdrs[who], json={"execution_mode": "auto"}).status_code == 403
    assert client.get("/api/auth/users", headers=hdrs[who]).status_code == 403

assert client.get("/api/config", headers=hdrs["admin_a"]).status_code == 200
cfg_up = client.put("/api/config", headers=hdrs["admin_a"], json={"file_upload": {"max_file_size_mb": 12.0}})
assert cfg_up.status_code == 200 and cfg_up.json()["updated_by"] == "admin_a@tn_northwind.example"

# Admin cannot create/move across tenants or self-disable/de-admin
assert client.post(
    "/api/auth/users",
    headers=hdrs["admin_a"],
    json={"username": "x_cross", "password": mk_pw(), "roles": ["process_owner"], "tenant_id": "tn_globex", "clearance": "L1"},
).status_code == 403
assert client.patch(
    f"/api/auth/users/{recs['admin_a'].sub}",
    headers=hdrs["admin_a"],
    json={"disabled": True},
).status_code == 400
assert client.patch(
    f"/api/auth/users/{recs['admin_a'].sub}",
    headers=hdrs["admin_a"],
    json={"roles": ["process_owner"]},
).status_code == 400
assert client.patch(
    f"/api/auth/users/{recs['carol_b'].sub}",
    headers=hdrs["admin_a"],
    json={"clearance": "L0"},
).status_code == 403

# Admin mints bounded token for agent_a_l1 via HTTP
mint_res = client.post(
    f"/api/auth/users/{recs['agent_a_l1'].sub}/token",
    headers=hdrs["admin_a"],
    json={"ttl_minutes": 15},
)
assert mint_res.status_code == 200, mint_res.text
assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {mint_res.json()['access_token']}"}).status_code == 200

# ---------------------------------------------------------------------------
# 6. Process Owner vs Security Reviewer Telemetry/Logs/Overview & Agent Blocks
# ---------------------------------------------------------------------------
assert client.get("/api/telemetry", headers=hdrs["alice_a"]).status_code == 403
assert client.get("/api/logs", headers=hdrs["alice_a"]).status_code == 403
assert client.get("/api/governance/incidents", headers=hdrs["alice_a"]).status_code == 403
ov_po = client.get("/api/overview", headers=hdrs["alice_a"])
assert ov_po.status_code == 200 and ov_po.json()["telemetry"] is None and ov_po.json()["models"] == {}

assert client.get("/api/telemetry", headers=hdrs["sec_a"]).status_code == 200
assert client.get("/api/logs", headers=hdrs["sec_a"]).status_code == 200
assert client.get("/api/governance/incidents", headers=hdrs["sec_a"]).status_code == 200
ov_sec = client.get("/api/overview", headers=hdrs["sec_a"])
assert ov_sec.status_code == 200 and ov_sec.json()["telemetry"] is not None

for m_meth, m_path in (
    ("GET", "/api/overview"),
    ("GET", "/api/scheduler"),
    ("GET", "/api/tools"),
    ("GET", "/api/telemetry"),
    ("GET", "/api/logs"),
    ("POST", "/api/security/test"),
    ("GET", "/api/uploads"),
    ("POST", "/api/uploads/scan"),
    ("POST", "/api/uploads/ingest"),
    ("POST", "/api/plan-preview"),
    ("GET", "/api/governance/jobs"),
    ("GET", "/api/governance/review-tasks"),
    ("GET", "/api/governance/incidents"),
):
    assert client.request(m_meth, m_path, headers=hdrs["agent_a_l1"]).status_code == 403, f"agent allowed on {m_meth} {m_path}"

# ---------------------------------------------------------------------------
# 7. Multi-Tenant Uploads, Legacy Flat Uploads & Ingestion Lifecycle + Spoof Blocks
# ---------------------------------------------------------------------------
# Drop a legacy flat file visible ONLY to tn_northwind (ELONE_DEFAULT_TENANT)
with open(os.path.join(ctx.UPLOADS_DIR, "legacy_nw.txt"), "w", encoding="utf-8") as lf:
    lf.write("Legacy SOP\n1. Check disk\n")

assert any(f["filename"] == "legacy_nw.txt" for f in client.get("/api/uploads", headers=hdrs["alice_a"]).json()["files"])
assert not any(f["filename"] == "legacy_nw.txt" for f in client.get("/api/uploads", headers=hdrs["carol_b"]).json()["files"])
assert client.post("/api/plan-preview", headers=hdrs["carol_b"], json={"filename": "legacy_nw.txt"}).status_code == 404

# Same filename uploaded by Tenant A and Tenant B
content_a = b"Title: Northwind DNS Flush\n1. Run ipconfig /flushdns\n"
content_b = b"Title: Globex Proxy Reset\n1. Reset proxy config\n"
up_a = client.post("/api/uploads/upload", headers=hdrs["alice_a"], files={"file": ("shared_vpn.txt", content_a, "text/plain")})
up_b = client.post("/api/uploads/upload", headers=hdrs["carol_b"], files={"file": ("shared_vpn.txt", content_b, "text/plain")})
assert up_a.status_code == 200 and up_b.status_code == 200
assert os.path.isfile(os.path.join(ctx.tenant_uploads_dir("tn_northwind"), "shared_vpn.txt"))
assert os.path.isfile(os.path.join(ctx.tenant_uploads_dir("tn_globex"), "shared_vpn.txt"))
with open(os.path.join(ctx.tenant_uploads_dir("tn_northwind"), "shared_vpn.txt"), "rb") as fa:
    assert fa.read() == content_a

# Upload second Tenant A doc for L2 security-reviewer gating + admin SoD + secret quarantine
client.post("/api/uploads/upload", headers=hdrs["alice_a"], files={"file": ("vault_l2.txt", b"Strictly Confidential Breakglass SOP\nHosts: 10.10.1.1, 10.10.1.2, 192.168.10.5, vpn.northwind.corp\nContacts: sec1@northwind.example, sec2@northwind.example, sec3@northwind.example\n1. Rotate breakglass key\n", "text/plain")})
client.post("/api/uploads/upload", headers=hdrs["admin_a"], files={"file": ("admin_doc.txt", b"Admin Maint\n1. Check disk health\n", "text/plain")})
client.post("/api/uploads/upload", headers=hdrs["alice_a"], files={"file": ("secret_a.txt", b"password = \"VerySecret123!\"\napi_key = \"sk_live_abc1234567890\"\n", "text/plain")})

def make_plan_factory():
    def _plan(filepath, override_sop_id=None, feedback_override=None, pre_extracted_text=None):
        sid = override_sop_id or "SOP-FAKE"
        base = os.path.basename(filepath)
        txt = pre_extracted_text or ""
        if base == "vault_l2.txt":
            return {
                "sop_id": sid,
                "is_executable": True,
                "confidence_score": 0.95,
                "confidence_level": "High",
                "raw_text": txt,
                "vlm_reports": [],
                "frontmatter": {
                    "sop_id": sid,
                    "title": "Breakglass Vault Key Rotation confidential SSN HIPAA",
                    "category": "security",
                    "platform": "system",
                    "description": "Contains credit card PAN and restricted confidential secret key policy.",
                    "is_executable": True,
                    "steps": [
                        {"step_number": 1, "step_type": "command", "sop_step_description": "Rotate breakglass key", "command": "Get-Date", "source_quote": "Rotate breakglass key"},
                    ],
                },
            }
        if base == "admin_doc.txt":
            return {
                "sop_id": sid,
                "is_executable": True,
                "confidence_score": 0.95,
                "confidence_level": "High",
                "raw_text": txt,
                "vlm_reports": [],
                "frontmatter": {
                    "sop_id": sid,
                    "title": "Admin Maintenance SOP",
                    "category": "system",
                    "platform": "system",
                    "description": "Routine health check.",
                    "is_executable": True,
                    "steps": [
                        {"step_number": 1, "step_type": "command", "sop_step_description": "Check disk health", "command": "Get-Volume", "source_quote": "Check disk health"},
                    ],
                },
            }
        if "Globex" in txt:
            return {
                "sop_id": sid,
                "is_executable": True,
                "confidence_score": 0.95,
                "confidence_level": "High",
                "raw_text": txt,
                "vlm_reports": [],
                "frontmatter": {
                    "sop_id": sid,
                    "title": "Globex Unique Proxy Reset SOP",
                    "category": "network",
                    "platform": "system",
                    "description": "Globex proxy procedure.",
                    "is_executable": True,
                    "steps": [
                        {"step_number": 1, "step_type": "command", "sop_step_description": "Reset proxy config", "command": "netsh winhttp reset proxy", "source_quote": "Reset proxy config"},
                    ],
                },
            }
        return {
            "sop_id": sid,
            "is_executable": True,
            "confidence_score": 0.95,
            "confidence_level": "High",
            "raw_text": txt,
            "vlm_reports": [],
            "frontmatter": {
                "sop_id": sid,
                "title": "Northwind DNS Cache Flush",
                "category": "network",
                "platform": "system",
                "description": "Northwind L1 SOP.",
                "is_executable": True,
                "steps": [
                    {"step_number": 1, "step_type": "command", "sop_step_description": "Run ipconfig /flushdns", "command": "ipconfig /flushdns", "source_quote": "Run ipconfig /flushdns"},
                ],
            },
        }
    return _plan

import agents.a2_structuring.canonical_builder as canonical_builder_mod
from agents.a3_security.confidentiality_engine import compute_confidentiality_score as _real_conf_score

def _conf_wrapper(text, dlp_stats=None, is_ocr=False, ai_advisory=None):
    if ai_advisory is None and "Breakglass" in (text or ""):
        ai_advisory = {"security_controls": True, "proprietary_process": True}
    return _real_conf_score(text, dlp_stats=dlp_stats, is_ocr=is_ocr, ai_advisory=ai_advisory)

with patch.object(routes_ingestion.jit_converter, "plan_okf_from_raw", side_effect=make_plan_factory()), \
     patch.object(canonical_builder_mod, "compute_confidentiality_score", side_effect=_conf_wrapper):
    # Alice ingests shared_vpn.txt while trying to spoof uploaded_by & tenant_id
    ing_a = client.post(
        "/api/uploads/ingest",
        headers=hdrs["alice_a"],
        json={"filename": "shared_vpn.txt", "sop_id": "SOP-NW-L1", "uploaded_by": "spoof@evil.example", "tenant_id": "tn_globex"},
    )
    assert ing_a.status_code == 200, ing_a.text
    ja = ing_a.json()
    assert ja["tenant_id"] == "tn_northwind"
    assert ja["uploaded_by"] == "alice_a@tn_northwind.example"
    task_nw = ja["task_id"]
    job_nw = ja["job_id"]

    # Carol (tn_globex) ingests same filename -> separate tenant job/SOP
    ing_b = client.post("/api/uploads/ingest", headers=hdrs["carol_b"], json={"filename": "shared_vpn.txt", "sop_id": "SOP-GLX-L1"})
    assert ing_b.status_code == 200, ing_b.text
    assert ing_b.json()["tenant_id"] == "tn_globex"
    task_glx = ing_b.json()["task_id"]

    # Agent CANNOT read unapproved draft canonical JSON
    assert client.get("/api/governance/sops/SOP-NW-L1/canonical", headers=hdrs["agent_a_l1"]).status_code == 403

    # Cross-tenant isolation on jobs, tasks, drafts, decisions, logs
    assert client.get(f"/api/governance/jobs/{job_nw}", headers=hdrs["carol_b"]).status_code == 403
    assert not any(t["task_id"] == task_nw for t in client.get("/api/governance/review-tasks", headers=hdrs["carol_b"]).json()["tasks"])
    assert client.get("/api/governance/drafts/SOP-NW-L1", headers=hdrs["carol_b"]).status_code == 403
    assert client.put("/api/governance/drafts/SOP-NW-L1/steps", headers=hdrs["carol_b"], json={"steps": [{"ref": 1, "sop_step_description": "x", "command": "ipconfig /flushdns"}]}).status_code == 403
    assert client.post(f"/api/governance/review-tasks/{task_nw}/decision", headers=hdrs["carol_b"], json={"decision": "approve"}).status_code == 403

    # Check debug log attribution: sec_a sees Tenant A logs, sec_b does NOT
    nw_logs = client.get("/api/logs", headers=hdrs["sec_a"]).json()["logs"]
    glx_logs = client.get("/api/logs", headers=hdrs["sec_b"]).json()["logs"]
    assert len(nw_logs) >= 1 and len(glx_logs) >= 1
    assert all(l["tenant_id"] == "tn_northwind" for l in nw_logs)
    nw_log_name = nw_logs[0]["filename"]
    assert client.get(f"/api/logs/{nw_log_name}", headers=hdrs["sec_a"]).status_code == 200
    assert client.get(f"/api/logs/{nw_log_name}", headers=hdrs["sec_b"]).status_code == 403

    # Agent CANNOT decide review task even spoofing actor_type=human
    r_agt_dec = client.post(
        f"/api/governance/review-tasks/{task_nw}/decision",
        headers=hdrs["agent_a_l1"],
        json={"decision": "approve", "actor_type": "human", "reviewer": "bob_a@tn_northwind.example"},
    )
    assert r_agt_dec.status_code == 403 and r_agt_dec.json()["error_code"] == "not_human", r_agt_dec.text

    # SoD 1: Uploader Alice cannot self-approve even spoofing reviewer=bob
    r_alice_sod = client.post(
        f"/api/governance/review-tasks/{task_nw}/decision",
        headers=hdrs["alice_a"],
        json={"decision": "approve", "reviewer": "bob_a@tn_northwind.example"},
    )
    assert r_alice_sod.status_code == 403 and r_alice_sod.json()["error_code"] == "separation_of_duties"

    # SoD 2: Bob edits draft steps (even spoofing actor) -> last_editor=bob -> Bob blocked from self-approving!
    ed = client.put(
        "/api/governance/drafts/SOP-NW-L1/steps",
        headers=hdrs["bob_a"],
        json={"actor": "someone_else", "steps": [{"ref": 1, "sop_step_description": "Run ipconfig /flushdns (verified)", "command": "ipconfig /flushdns", "source_quote": "Run ipconfig /flushdns"}]},
    )
    assert ed.status_code == 200 and ed.json()["last_editor"] == "bob_a@tn_northwind.example", ed.text
    r_bob_sod = client.post(
        f"/api/governance/review-tasks/{task_nw}/decision",
        headers=hdrs["bob_a"],
        json={"decision": "approve"},
    )
    assert r_bob_sod.status_code == 403 and r_bob_sod.json()["error_code"] == "separation_of_duties"

    # Sec reviewer (L2) approves & publishes L1 Northwind SOP (not uploader/editor)
    assert client.post(f"/api/governance/review-tasks/{task_nw}/decision", headers=hdrs["sec_a"], json={"decision": "approve"}).status_code == 200
    # Cross-tenant publish blocked
    assert client.post("/api/governance/sops/SOP-NW-L1/publish", headers=hdrs["admin_b"], json={}).status_code == 403
    assert client.post("/api/governance/sops/SOP-NW-L1/publish", headers=hdrs["sec_a"], json={}).status_code == 200

    # Admin_b approves & publishes Tenant B L1 SOP
    assert client.post(f"/api/governance/review-tasks/{task_glx}/decision", headers=hdrs["admin_b"], json={"decision": "approve"}).status_code == 200
    assert client.post("/api/governance/sops/SOP-GLX-L1/publish", headers=hdrs["admin_b"], json={}).status_code == 200

    # SoD 3: Admin CANNOT self-approve their own uploaded SOP
    ing_adm = client.post("/api/uploads/ingest", headers=hdrs["admin_a"], json={"filename": "admin_doc.txt", "sop_id": "SOP-ADM-L1"})
    assert ing_adm.status_code == 200
    task_adm = ing_adm.json()["task_id"]
    r_adm_sod = client.post(f"/api/governance/review-tasks/{task_adm}/decision", headers=hdrs["admin_a"], json={"decision": "approve"})
    assert r_adm_sod.status_code == 403 and r_adm_sod.json()["error_code"] == "separation_of_duties"

    # Clearance & assigned_role routing: vault_l2 triggers L2/Security reviewer task
    ing_l2 = client.post("/api/uploads/ingest", headers=hdrs["alice_a"], json={"filename": "vault_l2.txt", "sop_id": "SOP-NW-L2"})
    assert ing_l2.status_code == 200
    jl2 = ing_l2.json()
    task_l2 = jl2["task_id"]
    assert jl2["confidentiality"]["level"] == "L2", jl2
    assert jl2["assigned_role"] == "Security reviewer", jl2
    # L1 process_owner blocked by clearance & doesn't see L2 task in /review-tasks
    assert not any(t["task_id"] == task_l2 for t in client.get("/api/governance/review-tasks", headers=hdrs["bob_a"]).json()["tasks"])
    assert client.post(f"/api/governance/review-tasks/{task_l2}/decision", headers=hdrs["bob_a"], json={"decision": "approve"}).status_code == 403
    # Even L2 process_owner without security_reviewer/admin role is blocked from Security reviewer task!
    assert client.post(f"/api/governance/review-tasks/{task_l2}/decision", headers=hdrs["po_l2_a"], json={"decision": "approve"}).status_code == 403
    # Security reviewer approves & publishes (note clearance L3 >= L2/L3; ensure L3 SOP uses admin_a or promote sec_a if tier is L3)
    if jl2["confidentiality"]["level"] == "L3":
        assert client.post(f"/api/governance/review-tasks/{task_l2}/decision", headers=hdrs["sec_a"], json={"decision": "approve"}).status_code == 403
        assert client.post(f"/api/governance/review-tasks/{task_l2}/decision", headers=hdrs["admin_a"], json={"decision": "approve"}).status_code == 200
        assert client.post("/api/governance/sops/SOP-NW-L2/publish", headers=hdrs["admin_a"], json={}).status_code == 200
    else:
        assert client.post(f"/api/governance/review-tasks/{task_l2}/decision", headers=hdrs["sec_a"], json={"decision": "approve"}).status_code == 200
        assert client.post("/api/governance/sops/SOP-NW-L2/publish", headers=hdrs["sec_a"], json={}).status_code == 200

    # Secret quarantine -> tenant-isolated incidents
    r_q = client.post("/api/uploads/ingest", headers=hdrs["alice_a"], json={"filename": "secret_a.txt"})
    assert r_q.status_code == 403 and r_q.json()["status"] == "quarantined"
    assert client.get("/api/governance/incidents", headers=hdrs["sec_a"]).json()["count"] == 1
    assert client.get("/api/governance/incidents", headers=hdrs["sec_b"]).json()["count"] == 0

# ---------------------------------------------------------------------------
# 8. Playbooks Visibility, Verify, Search Spoofing Block & DELETE RBAC
# ---------------------------------------------------------------------------
# Tenant A L1 agent sees SOP-NW-L1, NOT SOP-NW-L2, NOT Tenant B SOP-GLX-L1
sops_a_l1 = {s["sop_id"] for s in client.get("/api/sops", headers=hdrs["agent_a_l1"]).json()["playbooks"]}
assert "SOP-NW-L1" in sops_a_l1
assert "SOP-NW-L2" not in sops_a_l1
assert "SOP-GLX-L1" not in sops_a_l1

assert client.get("/api/sops/SOP-NW-L1", headers=hdrs["agent_a_l1"]).status_code == 200
assert client.get("/api/sops/SOP-NW-L2", headers=hdrs["agent_a_l1"]).status_code == 403
assert client.get("/api/sops/SOP-GLX-L1", headers=hdrs["agent_a_l1"]).status_code == 403
assert client.post("/api/sops/SOP-GLX-L1/verify", headers=hdrs["admin_a"]).status_code == 403
assert client.post("/api/sops/SOP-NW-L1/verify", headers=hdrs["agent_a_l1"]).status_code == 200

# Downstream search ignores body tenant_id / clearance_level overrides
ds_a_l1 = client.post(
    "/api/governance/downstream/search",
    headers=hdrs["agent_a_l1"],
    json={"query": "breakglass key proxy", "tenant_id": "tn_globex", "clearance_level": "L3"},
)
assert ds_a_l1.status_code == 200
ds_ids = {r["sop_id"] for r in ds_a_l1.json()["results"]}
assert "SOP-GLX-L1" not in ds_ids
assert "SOP-NW-L2" not in ds_ids
assert ds_a_l1.json()["caller_tenant"] == "tn_northwind"
assert ds_a_l1.json()["caller_clearance"] == "L1"

stats_a = client.get("/api/governance/downstream/stats?tenant_id=tn_globex", headers=hdrs["agent_a_l1"]).json()
assert stats_a["tenant_id"] == "tn_northwind"

# Security reviewer cannot use PUT canonical or sync-playbook (process_owner / admin only)
assert client.put("/api/governance/sops/SOP-NW-L1/canonical", headers=hdrs["sec_a"], json={}).status_code == 403
assert client.post("/api/governance/sops/SOP-NW-L1/sync-playbook", headers=hdrs["sec_a"], json={}).status_code == 403

# DELETE /api/sops/{id}: strictly admin and process_owner; security_reviewer & agent blocked!
assert client.delete("/api/sops/SOP-NW-L1", headers=hdrs["sec_a"]).status_code == 403
assert client.delete("/api/sops/SOP-NW-L1", headers=hdrs["agent_a_l2"]).status_code == 403
assert client.delete("/api/sops/SOP-NW-L1", headers=hdrs["carol_b"]).status_code == 403
assert client.delete("/api/sops/SOP-NW-L2", headers=hdrs["bob_a"]).status_code == 403  # L1 cannot delete L2/L3

# process_owner deletes L1 SOP within tenant -> deleted_role == "owner", actor derived from token!
del_po = client.request("DELETE", "/api/sops/SOP-NW-L1", headers=hdrs["bob_a"], json={"actor": "spoofed_actor", "reason": "Cleanup"})
assert del_po.status_code == 200, del_po.text
assert del_po.json()["deleted_by"] == "bob_a@tn_northwind.example"
assert del_po.json()["deleted_role"] == "owner"

# admin deletes L2/L3 SOP within tenant -> deleted_role == "admin"
del_adm = client.delete("/api/sops/SOP-NW-L2", headers=hdrs["admin_a"])
assert del_adm.status_code == 200, del_adm.text
assert del_adm.json()["deleted_by"] == "admin_a@tn_northwind.example"
assert del_adm.json()["deleted_role"] == "admin"

print("ALL_AUTH_RBAC_TENANT_CORS_ASSERTIONS_PASSED")
'''


class TestAuthRbacTenantIsolationAndCors(unittest.TestCase):
    def test_end_to_end_auth_rbac_tenant_isolation_csrf_and_cors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            driver_path = os.path.join(tmpdir, "run_security_driver.py")
            with open(driver_path, "w", encoding="utf-8") as f:
                f.write(_SUBPROCESS_SECURITY_DRIVER)

            env = dict(os.environ)
            env["ELONE_KB_DIR"] = tmpdir
            env["ELONE_BACKEND_DIR"] = BACKEND_DIR
            env["ELONE_JWT_SECRET"] = secrets.token_urlsafe(32)
            env["ELONE_AUTH_MODE"] = "local"
            env["ELONE_ALLOWED_ORIGINS"] = "http://127.0.0.1:8000,http://localhost:8000"
            env["ELONE_DEFAULT_TENANT"] = "tn_northwind"
            env.pop("ELONE_ALLOW_INSECURE_DEV_KEY", None)

            proc = subprocess.run(
                [sys.executable, driver_path],
                capture_output=True,
                text=True,
                env=env,
                timeout=90,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"Isolated C2 security driver failed (exit {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
            )
            self.assertIn("ALL_AUTH_RBAC_TENANT_CORS_ASSERTIONS_PASSED", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

