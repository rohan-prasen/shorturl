from importlib.metadata import PackageNotFoundError, version


def main() -> None:
    print("Hello from shorturl!")


try:
    __version__ = version("shorturl")
except PackageNotFoundError:
    __version__ = "unknown"
