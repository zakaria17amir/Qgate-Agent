"""``detect api`` serves drift/bench queries; ``detect worker`` streams SPC rule alerts."""

import typer

from qgate_core import otel
from qgate_core.health import serve
from qgate_core.logs import configure_logging
from qgate_core.settings import Settings
from qgate_detect import worker as worker_mod
from qgate_detect.api import build_api

app = typer.Typer(add_completion=False)


@app.command()
def api() -> None:
    configure_logging()
    otel.configure("detect")
    serve(build_api(Settings()))


@app.command()
def worker() -> None:
    worker_mod.main()
