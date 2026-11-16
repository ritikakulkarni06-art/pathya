"""Linux child wrapper, invoked inside an isolated network namespace by the adapter."""

import os
import sys


def main() -> None:
    if sys.platform != "linux":
        raise SystemExit("Linux sandbox required")
    import resource

    timeout = int(sys.argv[1])
    output_limit = int(sys.argv[2])
    resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
    resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    command = sys.argv[4:]
    if sys.argv[3] != "--" or not command:
        raise SystemExit("Extraction command required")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
