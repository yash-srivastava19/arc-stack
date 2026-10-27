def __getattr__(name: str) -> str:
    # Looked up on first use: importing importlib.metadata slows every arc command.
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("arc-prs")
        except PackageNotFoundError:  # source checkout without `pip install -e .`
            return "0.0.0+dev"
    raise AttributeError(f"module 'arc' has no attribute {name!r}")
