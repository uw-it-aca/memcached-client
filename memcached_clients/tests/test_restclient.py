from unittest import TestCase, skipUnless
from commonconf import settings, override_settings
from memcached_clients.restclient import (
    RestclientCacheClient, CachePolicy, CachedHTTPResponse)
import os


class CachePolicyTest(CachePolicy):
    def get_cache_expiry(self, service, url):
        if service == "abc":
            return 60
        return 0


class CachePolicyNone(CachePolicy):
    def get_cache_expiry(self, service, url):
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
        policy = CachePolicyTest()
        self.assertEqual(
            policy.get_cache_expiry("abc", "https://api.edu/api/v1/test"), 60)


class RestclientCacheClientOfflineTests(TestCase):
    def setUp(self):
        RestclientCacheClient.policy = None

    def test_create_key(self):
        client = RestclientCacheClient()
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
        client = RestclientCacheClient()
        self.assertEqual(client._format_data(self.test_response), {
            "status": self.test_response.status,
            "headers": self.test_response.headers,
            "data": self.test_response.data
        })

    def test_get_policy(self):
        self.assertRaises(ImportError, RestclientCacheClient._get_policy,
                          "memcached_clients.tests.Fake")

        self.assertRaises(ImportError, RestclientCacheClient._get_policy,
                          None)

        self.assertEqual(RestclientCacheClient._get_policy(
            "memcached_clients.tests.test_restclient.CachePolicyTest"),
            CachePolicyTest)

    @override_settings(RESTCLIENTS_CACHE_POLICY_CLASS=(
        "memcached_clients.tests.test_restclient.CachePolicyTest"))
    def test_policy_setting(self):
        client1 = RestclientCacheClient()
        self.assertIs(client1.policy, CachePolicyTest)

        client2 = RestclientCacheClient()
        self.assertIs(client2.policy, CachePolicyTest)
        self.assertIs(client1.policy, client2.policy)


@override_settings(MEMCACHED_SERVERS=[("localhost", "11211")],
                   MEMCACHED_NOREPLY=False)
@skipUnless(os.getenv("LIVE_TESTS"), "Set LIVE_TESTS=1 to run tests")
class RestclientCacheClientLiveTests(TestCase):
    def setUp(self):
        self.test_response = CachedHTTPResponse(
            headers={}, status=200, data="some data")
        self.client = RestclientCacheClient()
        self.client.flush_all()

    def test_getCache(self):
        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        self.client.set(self.client._create_key("abc", "/api/v1/test"),
                        self.client._format_data(self.test_response))

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response.data, "some data")

    def test_deleteCache(self):
        reply = self.client.deleteCache("abc", "/api/v1/test")
        self.assertFalse(reply)

        self.client.set(self.client._create_key("abc", "/api/v1/test"),
                        self.client._format_data(self.test_response))

        reply = self.client.deleteCache("abc", "/api/v1/test")
        self.assertTrue(reply)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

    def test_updateCache(self):
        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        reply = self.client.updateCache(
            "abc", "/api/v1/test", self.test_response)
        self.assertTrue(reply)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response.data, "some data")

    def test_processResponse(self):
        reply = self.client.processResponse(
            "abc", "/api/v1/test", self.test_response)
        self.assertTrue(reply)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertEqual(response.data, "some data")

    @override_settings(RESTCLIENTS_CACHE_POLICY_CLASS=(
        "memcached_clients.tests.test_restclient.CachePolicyNone"))
    def test_cache_policy_none(self):
        RestclientCacheClient.policy = None
        self.client = RestclientCacheClient()

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)

        reply = self.client.updateCache(
            "abc", "/api/v1/test", self.test_response)
        self.assertNone(reply)

        response = self.client.getCache("abc", "/api/v1/test")
        self.assertIsNone(response)