def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_qt: marks tests requiring PySide6/Qt (excluded from CI)"
    )
