import sys
import difflib

import hou
from hutil.pprint import pformat


def strdiff(str1, str2, filename1="Before", filename2="After"):
    # Split strings by line break
    lines1 = str1.splitlines(keepends=True)
    lines2 = str2.splitlines(keepends=True)

    # Generate unified diff lines
    diff = difflib.unified_diff(lines1, lines2, fromfile=filename1, tofile=filename2)

    # ANSI Color Escape Codes
    RED = "\033[31m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    RESET = "\033[0m"

    # Process and colorize each line
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            sys.stdout.write(f"{GREEN}{line}{RESET}")
        elif line.startswith("-") and not line.startswith("---"):
            sys.stdout.write(f"{RED}{line}{RESET}")
        elif line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
            sys.stdout.write(f"{CYAN}{line}{RESET}")
        else:
            sys.stdout.write(line)


def diff(n1, n2):
    return strdiff(pformat(n1.asData(children=True)), pformat(n2.asData(children=True)))


obj = hou.node("/obj")
geo1 = obj.createNode("geo", "geo1")


geo2 = obj.createNode("geo", "geo2")

roberto = geo1.createNode("testgeometry_rubbertoy")

hou.hscript("coop_start")


roberto.parm("ry").set(42)

hou.hscript("coop_undo")

hou.hscript("coop_stop")


geo2.createNode("testgeometry_pighead")



# print(obj.children())
# diff(hou.node("/obj/geo1"), hou.node("/obj/geo2"))

