from qgate_core.health import health_app, serve

app = health_app("api")


def main() -> None:
    serve(app)
