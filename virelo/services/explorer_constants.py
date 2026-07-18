"""Import-light constants shared by Explorer services and workers."""

FVM_DETAILS = 4

# Debounce first, then retry after 100, 250, 500, and 1,000 milliseconds.
DEFAULT_AUTOSIZE_RETRY_SCHEDULE = (0.05, 0.1, 0.25, 0.5, 1.0)
