import click


@click.group(short_help="aircan CLI.")
def aircan():
    """aircan CLI.
    """
    pass


@aircan.command()
@click.argument("name", default="aircan")
def command(name):
    """Docs.
    """
    click.echo("Hello, {name}!".format(name=name))


def get_commands():
    return [aircan]
