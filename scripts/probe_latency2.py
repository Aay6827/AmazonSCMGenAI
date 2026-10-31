import time

import httpx

URL = "http://127.0.0.1:40003/health"


def ms(fn, n=5):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append(round((time.perf_counter() - t) * 1000))
    return out


print("httpx.get, new client each call   ", ms(lambda: httpx.get(URL, timeout=15)))
print("httpx.get, trust_env=False        ", ms(lambda: httpx.get(URL, timeout=15, trust_env=False)))
print("httpx.create_ssl_context() alone  ", ms(httpx.create_ssl_context))
shared = httpx.Client(timeout=15)
shared.get(URL)  # warm-up connection
print("one shared httpx.Client, reused   ", ms(lambda: shared.get(URL)))