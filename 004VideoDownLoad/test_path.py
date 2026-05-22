import os
from pathvalidate import sanitize_filepath

desktop = os.path.join(os.path.expanduser("~"), "Desktop")

tests = [
    (desktop, "《恋恋喜钱》第一集#二次元#虐恋#女频#重生#ai漫剧.mp4"),
    (desktop, "@小泽剪辑(O3xhcy6vhfzcu3qe).mp4"),
    (desktop, "EP1-01.如何看懂日志1.mp4"),
]

for d, name in tests:
    path = os.path.join(d, name)
    sanitized = sanitize_filepath(path)
    print(f"Orig:      {path}")
    print(f"Sanitized: {sanitized}")
    print(f"Basename:  {os.path.basename(sanitized)}")
    exists = os.path.exists(sanitized)
    print(f"Exists:    {exists}")
    print()
