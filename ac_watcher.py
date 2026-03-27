"""
AC Watcher — monitors for acs.exe and auto-launches/kills the telemetry logger.
Run this on Windows startup. It sits silently in the background.
"""

import subprocess
import sys
import time
import os

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
LOGGER      = os.path.join(SCRIPT_DIR, "ac_logger.py")
AC_PROCESS  = "acs.exe"
POLL_SEC    = 3

def ac_running():
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {AC_PROCESS}", "/NH"],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return AC_PROCESS.lower() in result.stdout.lower()

def main():
    logger_proc = None
    print(f"AC Watcher running. Watching for {AC_PROCESS}...")
    print(f"Logger: {LOGGER}\n")

    try:
        while True:
            if ac_running():
                if logger_proc is None or logger_proc.poll() is not None:
                    print(f"AC detected — starting logger.")
                    logger_proc = subprocess.Popen(
                        [sys.executable, LOGGER],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
            else:
                if logger_proc is not None and logger_proc.poll() is None:
                    print("AC closed — stopping logger.")
                    logger_proc.terminate()
                    logger_proc = None

            time.sleep(POLL_SEC)

    except KeyboardInterrupt:
        print("\nWatcher stopped.")
        if logger_proc and logger_proc.poll() is None:
            logger_proc.terminate()

if __name__ == "__main__":
    main()
