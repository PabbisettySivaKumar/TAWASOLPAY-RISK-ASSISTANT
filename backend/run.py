"""
Convenience launcher.

    python run.py

is equivalent to:

    uvicorn src.api.main:app --host 0.0.0.0 --port 8000
"""

import uvicorn

from src.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.BACKEND_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
