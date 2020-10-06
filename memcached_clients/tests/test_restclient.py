from unittest import TestCase, skipUnless
from commonconf import settings, override_settings
from memcached_clients.restclient import (
    RestclientPymemcacheClient, CachedHTTPResponse)
import os


class ClientCachePolicyTest(RestclientPymemcacheClient):
    def get_cache_expiry(self, service, url, status=None):
        if service == "abc":
            if status == 404:
                return None
            return 60
        return 0


class ClientCachePolicyNone(RestclientPymemcacheClient):
    def get_cache_expiry(self, service, url, status=None):
        return None


class CachedHTTPResponseTests(TestCase):
    def setUp(self):
        self.test_headers = {
            "Content-Disposition": "attachment; filename='name.ext'"
        }
        self.test_data = {
            "a": None, "b": b"test", "c": [(1, 2), (3, 4)]
        }
        self.test_status = 201
        self.response = CachedHTTPResponse(
            data=self.test_data,
            headers=self.test_headers,
            status=self.test_status)

    def test_read(self):
        empty = CachedHTTPResponse()
        self.assertEqual(empty.read(), None)

        self.assertEqual(self.response.read(), self.test_data)

    def test_getheader(self):
        empty = CachedHTTPResponse()
        self.assertEqual(empty.getheader("cache-control"), "")

        self.assertEqual(self.response.getheader("content-disposition"),
                         "attachment; filename='name.ext'")


class CachePolicyTests(TestCase):
    def test_get_cache_expiry(self):
        client = ClientCachePolicyTest()
        self.assertEqual(
            client.get_cache_expiry("xyz", "/api/v1/test", 200), 0)

        self.assertEqual(
            client.get_cache_expiry("abc", "/api/v1/test", 200), 60)

        self.assertEqual(
            client.get_cache_expiry("abc", "/api/v1/test", 404), None)

    @override_settings(RESTCLIENTS_MEMCACHED_DEFAULT_EXPIRY=3600)
    def test_defaullt_cache_expiry(self):
        client = RestclientPymemcacheClient()
        self.assertEqual(
            client.get_cache_expiry("abc", "/api/v1/test", 200), 3600)


class RestclientPymemcacheClientOfflineTests(TestCase):
    def test_create_key(self):
        client = RestclientPymemcacheClient()
        self.assertEqual(client._create_key("abc", "/api/v1/test"),
                         "abc-8157d24840389b1fec9480b59d9db3bde083cfee")

        long_url = "/api/v1/{}".format("x" * 250)
        self.assertEqual(client._create_key("abc", long_url),
                         "abc-61fdd52a3e916830259ff23198eb64a8c43f39f2")

    def test_format_data(self):
        self.test_response = CachedHTTPResponse(
            status=200,
            data={"a": 1, "b": b"test", "c": []},
            headers={"Content-Disposition": "attachment; filename='fname.ext'"}
        )
        client = RestclientPymemcacheClient()
        self.assertEqual(client._format_data(self.test_response), {
            "status": self.test_response.status,
            "headers": self.test_response.headers,
            "data": self.test_response.data
        })


@override_settings(MEMCACHED_SERVERS=["localhost:11211"],
                   MEMCACHED_NOREPLY=False)
@skipUnless(os.getenv("LIVE_TESTS"), "Set LIVE_TESTS=1 to run tests")
class RestclientPymemcacheClientLiveTests(TestCase):
    def setUp(self):
        self.test_response = CachedHTTPResponse(
            headers={}, status=200, data={"test": 12345})

        self.client = RestclientPymemcacheClient()
        self.client.flush_all()

    def test_getCache(self):
        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        self.client.updateCache("abc", "/api/v1/test", self.test_response)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response["response"].data, self.test_response.data)

    def test_deleteCache(self):
        reply = self.client.deleteCache("abc", "/api/v1/test")
        self.assertFalse(reply)

        self.client.updateCache("abc", "/api/v1/test", self.test_response)

        reply = self.client.deleteCache("abc", "/api/v1/test")
        self.assertTrue(reply)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

    def test_updateCache(self):
        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        self.client.updateCache("abc", "/api/v1/test", self.test_response)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response["response"].data, self.test_response.data)

    def test_processResponse(self):
        self.client.processResponse("abc", "/api/v1/test", self.test_response)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response["response"].data, self.test_response.data)

    def test_cache_policy_none(self):
        self.client = ClientCachePolicyNone()

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        self.client.updateCache("abc", "/api/v1/test", self.test_response)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)
