from torsearch.redact import redact


def test_masks_url_credentials():
    msg = "Invalid URL 'http://user:S3CRET@:9091/transmission/rpc'"
    assert redact(msg) == "Invalid URL 'http://***@:9091/transmission/rpc'"


def test_masks_secret_query_parameters():
    msg = "Client error '404 Not Found' for url 'https://t.example/api?t=caps&apikey=PK123'"
    assert "PK123" not in redact(msg)
    assert "apikey=***" in redact(msg)
    assert "api_key=***" in redact("https://jelly/Items?Recursive=true&api_key=JF1")


def test_masks_telegram_bot_token():
    msg = "for url 'https://api.telegram.org/bot123:ABC-def/sendMessage'"
    assert redact(msg) == "for url 'https://api.telegram.org/bot***/sendMessage'"


def test_leaves_harmless_text_untouched():
    msg = "can't connect to transmission daemon: HTTPConnectionPool(host='localhost', port=9091)"
    assert redact(msg) == msg
