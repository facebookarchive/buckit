#!/usr/bin/env python3
import base64
import random
import time
import sys


sys.stdout.buffer.write(base64.urlsafe_b64encode(
    (
        (int(time.time()) << 64) + random.randrange(2 ** 64)
    ).to_bytes(16, 'big').strip(b'\0')
).strip(b'='))
