import typer
from fastapi import FastAPI

from qgate_core.health import health_app, serve

app = typer.Typer(add_completion=False)


def build_app(role: str) -> FastAPI:
    return health_app(f"detect-{role}")


@app.command()
def api() -> None:
    serve(build_app("api"))


@app.command()
def worker() -> None:
    serve(build_app("worker"))
