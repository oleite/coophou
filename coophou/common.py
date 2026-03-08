import os


def log(t, msg):
    if os.getenv("COOPHOU_TESTING") != "1":
        return

    msg = f"  - {t}".ljust(20) + " | " + str(msg)
    print(msg)
