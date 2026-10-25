"""Create a demo account preloaded with the sample demo nonprofit (see grantbridge/demo.py).

Usage (from the repo folder):
    python -m scripts.create_demo_account --email you@example.org
    python -m scripts.create_demo_account --email you@example.org --prompt-password
    python -m scripts.create_demo_account --email you@example.org --reset

Without --prompt-password, a random password is generated and shown once in this
terminal. It is never written to disk or logged. There are no shared default
credentials: each person who runs this gets their own password.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from grantbridge import auth
from grantbridge.demo import demo_fixture, load_demo_data
from grantbridge.db import connect, init_db
from grantbridge.validation import ValidationError


def _remove_existing(email: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (email.strip().lower(),))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Login email for the demo account")
    parser.add_argument("--prompt-password", action="store_true", help="Type your own password instead of generating one")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the account if it already exists")
    args = parser.parse_args(argv)

    init_db()
    if args.reset:
        _remove_existing(args.email)

    if args.prompt_password:
        password = getpass.getpass("Password for the demo account: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
    else:
        password = secrets.token_urlsafe(15)

    try:
        user = auth.sign_up(args.email, password, demo_fixture()["profile"]["name"])
    except (auth.AuthError, ValidationError) as err:
        print(f"Could not create the demo account: {err}", file=sys.stderr)
        print("Use --reset to recreate an existing demo account.", file=sys.stderr)
        return 1

    load_demo_data(user.id)

    print(f"Demo account ready: {user.email}")
    if not args.prompt_password:
        print(f"Password (shown once, not saved anywhere): {password}")
    print("Start the app with:  python -m streamlit run streamlit_app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
