"""Separate dormant worker entrypoint; no queues, providers, or content ingestion."""
import argparse
from threading import Event
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate demo configuration and exit")
    args = parser.parse_args()
    Settings.from_environment().require_demo()
    if args.check:
        return
    try:
        Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

