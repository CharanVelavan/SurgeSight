"""Set Firebase custom claims (department, role) on a user, or create the demo accounts.

Usage:
  python scripts/set_department_claims.py --email officer@example.org --department "Health Department" --role approver
  python scripts/set_department_claims.py --list
  python scripts/set_department_claims.py --demo-viewer   # creates/updates demo@surgesight.example as a view-only user

Needs Application Default Credentials with Firebase Auth admin rights (gcloud auth application-default login).
Passwords are never stored here: new users get a random one that you reset from the Firebase console, or sign in with Google.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.auth import ROLES

DEMO_EMAIL = "demo@surgesight.example"


def claims_for(department: str | None, role: str) -> dict[str, str]:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    return {"role": role, **({"department": department} if department else {})}


def _init():
    import firebase_admin
    from dotenv import load_dotenv

    load_dotenv()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")})


def set_claims(email: str, department: str | None, role: str, *, create: bool = False) -> str:
    from firebase_admin import auth

    _init()
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        if not create:
            raise SystemExit(f"No Firebase user {email}. Create them in the console first, or pass --create.")
        user = auth.create_user(email=email, password=secrets.token_urlsafe(18), email_verified=True)
    auth.set_custom_user_claims(user.uid, claims_for(department, role))
    return user.uid


def list_users() -> None:
    from firebase_admin import auth

    _init()
    for user in auth.list_users().iterate_all():
        c = user.custom_claims or {}
        print(f"{user.email or user.uid:40} role={c.get('role', '-'):9} department={c.get('department', '-')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email")
    parser.add_argument("--department")
    parser.add_argument("--role", choices=ROLES, default="viewer")
    parser.add_argument("--create", action="store_true", help="create the user if missing")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--demo-viewer", action="store_true")
    args = parser.parse_args()
    if args.list:
        list_users()
    elif args.demo_viewer:
        print("demo viewer uid:", set_claims(DEMO_EMAIL, None, "viewer", create=True))
    elif args.email:
        print("updated uid:", set_claims(args.email, args.department, args.role, create=args.create))
        print("The user must sign in again (or refresh their token) to pick up the new claims.")
    else:
        parser.error("give --email, --list or --demo-viewer")


if __name__ == "__main__":
    main()
