"""``api`` maintenance commands. ``make token ROLE=approver SUB=alice`` mints a dev JWT."""

import typer

from qgate_api.main import ApiSettings
from qgate_core.auth import Role, mint

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """api maintenance."""


@app.command()
def token(role: Role = Role.APPROVER, sub: str = "dev") -> None:
    typer.echo(mint(sub, role, ApiSettings().jwt_secret))
