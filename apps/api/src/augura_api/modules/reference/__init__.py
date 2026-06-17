"""Interface publique du module reference — les autres modules n'importent que ceci."""

from augura_api.modules.reference.router import router

__all__ = ["router"]
