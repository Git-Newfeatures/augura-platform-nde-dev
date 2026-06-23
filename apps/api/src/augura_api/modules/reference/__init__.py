"""Public interface for the reference module — other modules import only this."""

from augura_api.modules.reference.router import router

__all__ = ["router"]
