"""Private child-process resource envelope for local media tools; never accepts URLs."""

import os
import resource
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"ffmpeg", "ffprobe"}:
        raise SystemExit("Unsupported decoder")
    # Limits are applied in this short-lived process, never via preexec_fn in a threaded server.
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # Linux additionally supports a predictable address-space cap. macOS relies on the
    # decoder allocation, dimensions, input bytes, threads, CPU, file and wall-clock caps.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
