from zsper.security.redaction import redact_secrets


def test_redaction_removes_secret_values_from_nested_json_shapes() -> None:
    payload = {
        "apiKey": "ak-value",
        "nested": {
            "token": "token-value",
            "items": [
                {"Authorization": "bearer secret"},
                {"safe": "visible"},
            ],
        },
        "password": "password-value",
        "safe": "keep",
    }

    redacted = redact_secrets(payload)
    rendered = repr(redacted)

    assert redacted["apiKey"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["items"][0]["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["items"][1]["safe"] == "visible"
    assert redacted["safe"] == "keep"
    assert "ak-value" not in rendered
    assert "token-value" not in rendered
    assert "bearer secret" not in rendered
    assert "password-value" not in rendered


def test_redaction_preserves_non_secret_list_shape() -> None:
    payload = [{"name": "local"}, {"secret": "hide"}]

    assert redact_secrets(payload) == [{"name": "local"}, {"secret": "[REDACTED]"}]
