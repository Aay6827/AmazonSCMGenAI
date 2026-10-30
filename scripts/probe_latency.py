import time

import httpx

for host in ("localhost", "127.0.0.1"):
    times = []
    for _ in range(3):
        t = time.perf_counter()
        httpx.get(f"http://{host}:40003/health", timeout=15)
        times.append(round((time.perf_counter() - t) * 1000))
    print(f"{host:<12}{times} ms")