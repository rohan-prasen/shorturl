from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version


def main() -> None:
    print("Hello from shorturl!")


try:
    __version__ = _version("shorturl")
except PackageNotFoundError:
    __version__ = "unknown"
