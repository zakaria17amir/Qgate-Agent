from qgate_core.health import health_app, serve

app = health_app("ingest")


def main() -> None:
    serve(app)
