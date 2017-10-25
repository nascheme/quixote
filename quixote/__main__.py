import sys
import os

USAGE = "Usage: quixote run [options]"

def usage():
    print(USAGE, file=sys.stderr)
    raise SystemExit()

def main():
    if len(sys.argv) <= 1:
        usage()

    cmd = sys.argv[1]
    if cmd == 'run':
        # only command supported right now
        import quixote.server.simple_server
        quixote.server.simple_server.main(sys.argv[2:])
    elif cmd == 'version':
        import quixote
        print(quixote.__version__)
    else:
        usage()


if __name__ == '__main__':
    main()
