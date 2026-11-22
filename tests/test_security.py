import unittest

import requests

import main


class SafeRequestErrorTests(unittest.TestCase):
    def test_request_error_does_not_expose_url_or_query_token(self):
        secret_url = (
            "https://api.example.test/data?"
            "apikey=TOP_SECRET_VALUE&symbol=EUR%2FUSD"
        )
        error = requests.RequestException(secret_url)

        message = main.safe_request_error(error)

        self.assertEqual(message, "RequestException")
        self.assertNotIn("TOP_SECRET_VALUE", message)
        self.assertNotIn("apikey", message)
        self.assertNotIn("api.example.test", message)

    def test_http_error_keeps_status_without_response_body(self):
        response = requests.Response()
        response.status_code = 401
        error = requests.HTTPError(
            "https://api.example.test/data?apikey=TOP_SECRET_VALUE",
            response=response,
        )

        message = main.safe_request_error(error)

        self.assertEqual(message, "HTTPError (HTTP 401)")
        self.assertNotIn("TOP_SECRET_VALUE", message)


if __name__ == "__main__":
    unittest.main()
