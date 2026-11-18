import sys as _sys
import traceback as _traceback

Manager = None
_import_error_traceback = None
try:
    from .manager import Manager
except ImportError:
    # Tests import this package outside Ableton (where ableton.v2.* and
    # _Framework are unavailable). Swallow the ImportError so pytest can still
    # collect this __init__.py, but stash the traceback so create_instance can
    # surface it when called from Ableton.
    _import_error_traceback = _traceback.format_exc()

def create_instance(c_instance):
    if Manager is None:
        _sys.stderr.write(
            "Suno Bridge: failed to import Manager:\n%s" % _import_error_traceback
        )
        raise ImportError(
            "Suno Bridge: Manager import failed; see Ableton Log.txt for details"
        )
    return Manager(c_instance)
