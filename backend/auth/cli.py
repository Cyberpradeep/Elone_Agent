"""
Local Auth & Service-Account CLI Bootstrap Utility (C2)
=======================================================
Usage (from backend/):
  python -m auth.cli create-user --username alice --role process_owner --tenant tn_northwind --clearance L1
  python -m auth.cli issue-agent-token --tenant tn_northwind --clearance L1 --persona service_desk_agent
  python -m auth.cli list-users [--tenant tn_northwind]
  python -m auth.cli disable-user --username alice
"""

import argparse
import getpass
import json
import sys

from .models import AuthPrincipal, ROLE_AGENT, ROLE_SET
from .tokens import create_access_token
from .user_store import user_store


def _cmd_create_user(args: argparse.Namespace) -> int:
    password = args.password
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    if ROLE_AGENT not in roles and not password:
        password = getpass.getpass(f"Password for {args.username}: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            return 1

    rec = user_store.create_user(
        username=args.username,
        password=password,
        roles=roles,
        tenant_id=args.tenant,
        clearance=args.clearance,
        identity=args.identity or args.username,
        display_name=args.display_name or args.username,
        agent_id=args.agent_id,
        agent_persona=args.agent_persona,
    )
    print(json.dumps(rec.to_public_dict(), indent=2))
    return 0


def _cmd_issue_agent_token(args: argparse.Namespace) -> int:
    principal = AuthPrincipal(
        sub=f"agt_{args.agent_id}",
        identity=args.agent_id,
        display_name=args.agent_id,
        roles=[ROLE_AGENT],
        tenant_id=args.tenant,
        clearance=args.clearance,
        actor_type="agent",
        agent_id=args.agent_id,
        agent_persona=args.persona,
    )
    token, jti, expires_in = create_access_token(
        principal, ttl_seconds=args.ttl_minutes * 60
    )
    print(json.dumps({
        "token_type": "bearer",
        "access_token": token,
        "jti": jti,
        "expires_in": expires_in,
        "principal": principal.to_public_dict(),
    }, indent=2))
    return 0


def _cmd_list_users(args: argparse.Namespace) -> int:
    users = user_store.list_users(tenant_id=args.tenant)
    print(json.dumps([u.to_public_dict() for u in users], indent=2))
    return 0


def _cmd_set_disabled(args: argparse.Namespace, disabled: bool) -> int:
    rec = user_store.get_by_username(args.username)
    if not rec:
        print(f"Error: user '{args.username}' not found.", file=sys.stderr)
        return 1
    updated = user_store.update_user(rec.sub, disabled=disabled)
    print(json.dumps(updated.to_public_dict(), indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Elone Governance Hub Auth Bootstrap CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_create = subparsers.add_parser("create-user", help="Create a local human or service account")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--identity", default=None, help="Immutable audit identity (email/id)")
    p_create.add_argument("--display-name", default=None)
    p_create.add_argument(
        "--role", "--roles", dest="roles", required=True,
        help=f"Comma-separated roles from: {', '.join(sorted(ROLE_SET))}",
    )
    p_create.add_argument("--tenant", default="tn_northwind")
    p_create.add_argument("--clearance", default="L1", choices=["L0", "L1", "L2", "L3"])
    p_create.add_argument("--password", default=None)
    p_create.add_argument("--agent-id", default=None)
    p_create.add_argument("--agent-persona", default=None)

    p_agent = subparsers.add_parser("issue-agent-token", help="Mint a scoped downstream agent JWT")
    p_agent.add_argument("--tenant", required=True)
    p_agent.add_argument("--clearance", required=True, choices=["L0", "L1", "L2", "L3"])
    p_agent.add_argument("--agent-id", required=True)
    p_agent.add_argument("--persona", default=None)
    p_agent.add_argument("--ttl-minutes", type=int, default=480)

    p_list = subparsers.add_parser("list-users", help="List configured users")
    p_list.add_argument("--tenant", default=None)

    p_dis = subparsers.add_parser("disable-user", help="Disable a user account")
    p_dis.add_argument("--username", required=True)

    p_en = subparsers.add_parser("enable-user", help="Re-enable a user account")
    p_en.add_argument("--username", required=True)

    args = parser.parse_args(argv)
    if args.command == "create-user":
        return _cmd_create_user(args)
    if args.command == "issue-agent-token":
        return _cmd_issue_agent_token(args)
    if args.command == "list-users":
        return _cmd_list_users(args)
    if args.command == "disable-user":
        return _cmd_set_disabled(args, True)
    if args.command == "enable-user":
        return _cmd_set_disabled(args, False)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

