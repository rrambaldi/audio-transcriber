"""The local web interface: the same transcriptions, from a browser.

FastAPI and Uvicorn are an optional extra, so they are imported only when the
interface is actually started; installing the package for the command line
pulls in neither.
"""
import sys


def create_app(settings=None, queue=None):
    """The ASGI application, for ``uvicorn`` or a test client."""
    from .api import create_app as build

    return build(settings, queue)


def run(host="127.0.0.1", port=8765, settings=None, root_path=""):
    """Serve the interface until interrupted.

    ``root_path`` is the prefix a reverse proxy strips before passing the
    request on (``/transcriber``). The page itself does not need it — every URL
    it builds is relative — but the generated API documentation does."""
    from ..i18n import t

    try:
        import uvicorn
    except ImportError:
        sys.exit(t("web.missing"))
    try:
        app = create_app(settings)
    except ImportError:
        sys.exit(t("web.missing"))
    uvicorn.run(app, host=host, port=port, log_level="warning",
                root_path=root_path or "")
    return 0
