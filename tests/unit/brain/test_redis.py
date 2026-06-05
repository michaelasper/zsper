from zsper.brain.redis import (
    CANONICAL_RECORD_TYPES,
    REDIS_RUNTIME_PURPOSES,
    redis_config_from_env,
    redis_is_canonical_storage,
)


def test_redis_config_is_profile_aware_from_service_env() -> None:
    config = redis_config_from_env(
        {
            "ZSPER_PROFILE_ID": "work",
            "REDIS_URL": "redis://redis:6379/0",
            "REDIS_KEY_PREFIX": "zsper:work:",
        }
    )

    assert config.profile_id == "work"
    assert config.url == "redis://redis:6379/0"
    assert config.key("jobs", "ingest", "123") == "zsper:work:jobs:ingest:123"


def test_redis_is_limited_to_runtime_cache_and_coordination() -> None:
    assert REDIS_RUNTIME_PURPOSES == frozenset({"cache", "job-coordination", "locks"})

    for record_type in CANONICAL_RECORD_TYPES:
        assert not redis_is_canonical_storage(record_type)
