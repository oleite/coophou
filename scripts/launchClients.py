import os
import subprocess
import shutil
import argparse


def launchClients(sessionCount: int):
    if not shutil.which("houdini"):
        print(
            "Error: 'houdini' command not found. Please ensure Houdini is installed and added to your PATH."
        )
        return

    for i in range(sessionCount):

        env = os.environ.copy()
        env["COOPHOU_TESTING"] = "1"
        env["COOPHOU_TESTING_COLUMN"] = str(i)
        env["COOPHOU_TESTING_COLUMN_COUNT"] = str(sessionCount)
        # env["COOPHOU_TESTING_AS_SERVER"] = "1" if i == 0 else "0"

        print(f"Launching Houdini session {i + 1}/{sessionCount}")
        subprocess.Popen(["houdini", "-desktop", "CoopHouTesting"], env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch multiple Houdini sessions.")
    parser.add_argument(
        "--sessions", type=int, default=2, help="Number of Houdini sessions to launch"
    )
    args = parser.parse_args()

    launchClients(args.sessions)
