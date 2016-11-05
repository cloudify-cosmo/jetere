
import json
from functools import wraps
import zlib

from pymemcache.client.base import Client as MemcachedClient

from reports.config import instance as config

memcached = MemcachedClient(('localhost', 11211), timeout=1)

_enable_caching = config['enable_caching']


def cache_result(result_class,
                 key=None,
                 expire=0,
                 max_result_size=1000000,
                 **kw):

    def decorator(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            if key:
                memcached_key = key
            else:
                values = [str(x) for x in args[1:]]
                memcached_key = '{}-{}'.format(result_class.__name__.lower(),
                                               '-'.join(values))
            result = memcached.get(memcached_key) if _enable_caching else None
            if result:
                as_dict = json.loads(zlib.decompress(result))
            else:
                as_dict = func(*args, **kwargs)
                if _enable_caching:
                    compressed_data = zlib.compress(json.dumps(as_dict))
                    cache = len(compressed_data) < max_result_size
                    if cache:
                        cache_if = {k.replace('cache_if_', ''): v
                                    for k, v in kw.items()
                                    if k.startswith('cache_if')}
                        cache = True
                        if cache_if:
                            for k, v in cache_if.items():
                                if as_dict[k] != v:
                                    cache = False
                                    break
                        if cache:
                            memcached.set(
                                    memcached_key,
                                    zlib.compress(json.dumps(as_dict)),
                                    expire=expire)
            if isinstance(as_dict, list):
                return [result_class(x) for x in as_dict]
            else:
                return result_class(as_dict)

        return _wrapper

    return decorator
