"""Reload-stable ownership registry for the one active HOM probe."""

_active_probe = None


def claim(probe):
    """Stop the previous coophou probe and make *probe* the owner."""
    global _active_probe
    if _active_probe is probe:
        return
    previous = _active_probe
    _active_probe = probe
    if previous is not None:
        previous.stopWatcher()


def release(probe):
    global _active_probe
    if _active_probe is probe:
        _active_probe = None


def active_probe():
    return _active_probe
