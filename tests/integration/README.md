# Integration tests

Integration tests that require the private snapshot are opt-in and must read `ECOM_SOURCE_ROOT`.
They must never copy source rows into fixtures or failure output.

