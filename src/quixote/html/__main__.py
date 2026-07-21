import argparse
import sys


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="quixote.html",
        description="Tools for quixote.html",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "check",
        help="check that htmlformat() calls use t-string arguments",
        add_help=False,
    )

    args, rest = parser.parse_known_args(argv)

    if args.command == "check":
        from quixote.html.check_htmlformat import main as check_main

        return check_main(rest, prog=f"{parser.prog} check")
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
