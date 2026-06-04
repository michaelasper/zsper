# Test Fixtures

Fixtures in this directory are repository-owned sample data for tests. Shared
runtime paths should come from `tests/conftest.py` fixtures instead of real user
locations.

- Use `profile_root_factory` to create unique temporary profile roots.
- Use `isolated_registry_path` for a temporary profile registry file path.
- Do not write under `/Users/michaelasper` unless a test explicitly opts into a
  real local integration path.
