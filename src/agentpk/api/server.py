from __future__ import annotations


def serve(host: str = "0.0.0.0", port: int = 8080, reload: bool = False) -> None:
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "API server requires additional dependencies.\n"
            "Install with: pip install agentpk[api]"
        )

    from agentpk.api.app import create_app
    app = create_app()
    uvicorn.run(app, host=host, port=port, reload=reload)
