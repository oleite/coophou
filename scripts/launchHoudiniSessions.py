import sys
import os
import subprocess
import shutil
import argparse


def launchHoudiniSessions(sessionCount: int):
    if not shutil.which("houdini"):
        print(
            "Error: 'houdini' command not found. Please ensure Houdini is installed and added to your PATH."
        )
        return

    scriptDir = os.path.dirname(sys.argv[0])
    scriptPath = os.path.join(scriptDir, "setupHouWindow.py")

    for i in range(sessionCount):
        command = [
            "houdini",
            scriptPath,
            "--column",
            str(i),
            "--columnCount",
            str(sessionCount),
        ]

        if i == 0:
            command.append("--asServer")

        print(f"Launching Houdini session {i + 1}/{sessionCount}")
        subprocess.Popen(command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch multiple Houdini sessions.")
    parser.add_argument(
        "--sessions", type=int, default=2, help="Number of Houdini sessions to launch"
    )
    args = parser.parse_args()

    launchHoudiniSessions(args.sessions)
