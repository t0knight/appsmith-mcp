import unittest

from appsmith_mcp.redaction import REDACTED, is_sensitive_key, redact


class SensitiveKeyTests(unittest.TestCase):
    def test_secret_like_key_names(self):
        for key in (
            "password", "dbPassword", "passwd", "pwd", "clientSecret", "client_secret",
            "accessToken", "refresh-token", "bearerToken", "X-Auth-Token", "apiKey",
            "x-api-key", "privateKey", "secretKey", "serviceRoleKey", "Authorization",
            "Proxy-Authorization", "Cookie", "Set-Cookie", "credentials",
        ):
            with self.subTest(key=key):
                self.assertTrue(is_sensitive_key(key))

    def test_ordinary_key_names(self):
        for key in (
            "username", "host", "port", "databaseName", "url", "accessTokenUrl",
            "authenticationType", "value", "key", "body", "label", "", None,
        ):
            with self.subTest(key=key):
                self.assertFalse(is_sensitive_key(key))


class RedactTests(unittest.TestCase):
    def test_masks_values_under_secret_keys_at_any_depth(self):
        config = {
            "endpoints": [{"host": "db.example.com", "port": 5432}],
            "authentication": {"username": "app", "password": "s3cr3t"},
            "nested": {"oauth": {"clientSecret": "abc", "accessTokenUrl": "https://example.com/token"}},
        }

        self.assertEqual(
            redact(config),
            {
                "endpoints": [{"host": "db.example.com", "port": 5432}],
                "authentication": {"username": "app", "password": REDACTED},
                "nested": {"oauth": {"clientSecret": REDACTED, "accessTokenUrl": "https://example.com/token"}},
            },
        )

    def test_masks_value_of_key_value_pairs_with_secret_key(self):
        headers = [
            {"key": "Authorization", "value": "Bearer abc"},
            {"key": "X-API-Key", "value": "k-123"},
            {"key": "Accept", "value": "application/json"},
        ]

        self.assertEqual(
            redact(headers),
            [
                {"key": "Authorization", "value": REDACTED},
                {"key": "X-API-Key", "value": REDACTED},
                {"key": "Accept", "value": "application/json"},
            ],
        )

    def test_masks_api_key_authentication_value(self):
        auth = {"authenticationType": "apiKey", "label": "api_key", "value": "k-123", "addTo": "HEADER"}

        self.assertEqual(redact(auth)["value"], REDACTED)
        self.assertEqual(redact(auth)["label"], "api_key")

    def test_masks_credential_shaped_strings_under_neutral_keys(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
        self.assertEqual(redact({"value": "Bearer abc.def"}), {"value": REDACTED})
        self.assertEqual(redact({"data": "Basic dXNlcjpwYXNz"}), {"data": REDACTED})
        self.assertEqual(redact({"session": jwt}), {"session": REDACTED})
        self.assertEqual(
            redact({"url": "postgres://app:s3cr3t@db.example.com:5432/shop"}),
            {"url": f"postgres://app:{REDACTED}@db.example.com:5432/shop"},
        )

    def test_keeps_binding_references_empty_values_and_flags(self):
        config = {
            "headers": [{"key": "Authorization", "value": "Bearer {{ appsmith.store.token }}"}],
            "accessToken": "{{ appsmith.store.access_token }}",
            "password": "",
            "secretExists": True,
            "refreshToken": None,
        }

        self.assertEqual(redact(config), config)

    def test_masks_literal_secret_mixed_with_a_binding(self):
        self.assertEqual(redact({"apiKey": "k-123{{ x }}"}), {"apiKey": REDACTED})

    def test_key_hint_masks_scalar_and_nested_values(self):
        self.assertEqual(redact("abc", "access_token"), REDACTED)
        self.assertEqual(redact({"a": 1}, "credentials"), REDACTED)
        self.assertEqual(redact(7, "id"), 7)

    def test_does_not_mutate_input(self):
        original = {"password": "s3cr3t", "items": [{"key": "Cookie", "value": "sid=1"}]}
        snapshot = {"password": "s3cr3t", "items": [{"key": "Cookie", "value": "sid=1"}]}

        redact(original)

        self.assertEqual(original, snapshot)

    def test_secret_under_neutral_name_in_unknown_format_is_not_detected(self):
        # Documented limitation: detection is best-effort, based on names and formats.
        self.assertEqual(redact({"config": "hunter2"}), {"config": "hunter2"})


if __name__ == "__main__":
    unittest.main()
