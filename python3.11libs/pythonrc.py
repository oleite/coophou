import os
import sys
import inspect

# Appending to PYTHONPATH directly within the package JSON isn't working
# for some reason, so we have to do it here in the startup script.
sys.path.append(
    os.path.dirname(os.path.dirname(inspect.getfile(inspect.currentframe())))
)
