import signal, time, os, sys

received = []


def handler(signum, frame):
    received.append((time.time(), frame.f_code.co_filename, frame.f_lineno))
    print(
        f"[{time.time():.3f}] SIGINT received during {frame.f_code.co_filename}:{frame.f_lineno}",
        flush=True,
    )


signal.signal(signal.SIGINT, handler)
print(f"PID {os.getpid()} sleeping 30 seconds. Press nothing.", flush=True)

for i in range(30):
    time.sleep(1)
    print(f"  tick {i+1}/30, received {len(received)} signals so far", flush=True)

print(f"Done. Total signals received: {len(received)}", flush=True)
for t, fname, lineno in received:
    print(f"  {t:.3f}: {fname}:{lineno}")
