from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from core.init import ensure_runtime_dir
from core.paths import get_data_dir, get_persons_dir, get_shared_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("animaworks")


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize the runtime data directory from templates."""
    data_dir = get_data_dir()
    if data_dir.exists() and not getattr(args, "force", False):
        print(f"Runtime directory already exists: {data_dir}")
        print("Use --force to re-initialize from templates.")
        return
    ensure_runtime_dir()
    print(f"Runtime directory initialized: {data_dir}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the daemon (FastAPI + APScheduler)."""
    import uvicorn

    from server.app import create_app

    ensure_runtime_dir()
    app = create_app(get_persons_dir(), get_shared_dir())
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_chat(args: argparse.Namespace) -> None:
    """One-shot chat with a person from CLI."""
    from core.person import DigitalPerson

    ensure_runtime_dir()
    person_dir = get_persons_dir() / args.person
    if not person_dir.exists():
        print(f"Person not found: {args.person}")
        sys.exit(1)

    person = DigitalPerson(person_dir, get_shared_dir())
    response = asyncio.run(person.process_message(args.message))
    print(response)


def cmd_heartbeat(args: argparse.Namespace) -> None:
    """Manually trigger heartbeat."""
    from core.person import DigitalPerson

    ensure_runtime_dir()
    person_dir = get_persons_dir() / args.person
    if not person_dir.exists():
        print(f"Person not found: {args.person}")
        sys.exit(1)

    person = DigitalPerson(person_dir, get_shared_dir())
    result = asyncio.run(person.run_heartbeat())
    print(f"[{result.action}] {result.summary[:500]}")


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message from one person to another."""
    from core.messenger import Messenger

    ensure_runtime_dir()
    messenger = Messenger(get_shared_dir(), args.from_person)
    msg = messenger.send(
        to=args.to_person,
        content=args.message,
        thread_id=args.thread_id or "",
        reply_to=args.reply_to or "",
    )
    print(f"Sent: {msg.from_person} -> {msg.to_person} (id: {msg.id}, thread: {msg.thread_id})")


def cmd_list(args: argparse.Namespace) -> None:
    """List all persons."""
    ensure_runtime_dir()
    persons_dir = get_persons_dir()
    if not persons_dir.exists():
        print("No persons directory found.")
        return
    for d in sorted(persons_dir.iterdir()):
        if d.is_dir() and (d / "identity.md").exists():
            print(f"  {d.name}")


def cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="AnimaWorks - Digital Person Framework"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override runtime data directory (default: ~/.animaworks or ANIMAWORKS_DATA_DIR)",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize runtime directory from templates")
    p_init.add_argument("--force", action="store_true", help="Re-initialize even if exists")
    p_init.set_defaults(func=cmd_init)

    p_serve = sub.add_parser("serve", help="Start daemon (web + scheduler)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=18500)
    p_serve.set_defaults(func=cmd_serve)

    p_chat = sub.add_parser("chat", help="Chat with a person")
    p_chat.add_argument("person", help="Person name")
    p_chat.add_argument("message", help="Message to send")
    p_chat.set_defaults(func=cmd_chat)

    p_hb = sub.add_parser("heartbeat", help="Trigger heartbeat")
    p_hb.add_argument("person", help="Person name")
    p_hb.set_defaults(func=cmd_heartbeat)

    p_send = sub.add_parser("send", help="Send message between persons")
    p_send.add_argument("from_person", help="Sender name")
    p_send.add_argument("to_person", help="Recipient name")
    p_send.add_argument("message", help="Message content")
    p_send.add_argument("--thread-id", default=None, help="Thread ID")
    p_send.add_argument("--reply-to", default=None, help="Reply to message ID")
    p_send.set_defaults(func=cmd_send)

    p_list = sub.add_parser("list", help="List all persons")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()

    # Apply --data-dir override before any command
    if args.data_dir:
        os.environ["ANIMAWORKS_DATA_DIR"] = args.data_dir

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    cli_main()
