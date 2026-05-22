"""Download PyTorch CUDA wheel with resume support."""
import os
import time
import urllib.request
import sys

URL = "https://download.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp313-cp313-win_amd64.whl"
OUTPUT = r"C:\Users\Administrator\Downloads\torch-2.6.0+cu124-cp313-cp313-win_amd64.whl"

def download_with_resume(url, output, max_retries=30):
    total_retries = 0

    while total_retries < max_retries:
        existing_size = os.path.getsize(output) if os.path.exists(output) else 0
        try:
            req = urllib.request.Request(url)
            if existing_size > 0:
                req.add_header("Range", f"bytes={existing_size}-")
                print(f"Resuming from byte {existing_size:_}")
            else:
                print("Starting fresh download...")

            with urllib.request.urlopen(req, timeout=90) as resp:
                expected_total = 0
                if "Content-Range" in resp.headers:
                    expected_total = int(resp.headers["Content-Range"].split("/")[-1])
                elif "Content-Length" in resp.headers:
                    expected_total = int(resp.headers["Content-Length"]) + existing_size

                if expected_total == 0:
                    print("Warning: could not determine total size")
                else:
                    print(f"Total size: {expected_total:_} bytes ({expected_total/1024/1024/1024:.2f} GB)")

                mode = "ab" if existing_size > 0 else "wb"
                with open(output, mode) as f:
                    chunk_size = 256 * 1024
                    downloaded = existing_size
                    last_print = 0
                    start_time = time.time()

                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if time.time() - last_print > 3:
                            elapsed = time.time() - start_time
                            speed = (downloaded - existing_size) / elapsed / 1024 / 1024 if elapsed > 0 else 0
                            if expected_total > 0:
                                pct = downloaded / expected_total * 100
                                eta = (expected_total - downloaded) / (speed * 1024 * 1024) if speed > 0 else 0
                                print(f"  {downloaded:_} / {expected_total:_} ({pct:.1f}%)  {speed:.1f} MB/s  ETA: {eta:.0f}s")
                            else:
                                print(f"  {downloaded:_} bytes  {speed:.1f} MB/s")
                            last_print = time.time()

                # Verify completeness
                if expected_total > 0 and downloaded < expected_total:
                    actual_size = os.path.getsize(output)
                    if actual_size < expected_total:
                        raise ConnectionError(
                            f"Incomplete download: {actual_size:_} / {expected_total:_} bytes "
                            f"({actual_size/expected_total*100:.1f}%). Will resume..."
                        )

                print(f"Download complete! {downloaded:_} bytes", flush=True)
                return True

        except ConnectionError as e:
            total_retries += 1
            print(f"Connection broken (retry {total_retries}/{max_retries}): {e}")
            wait = min(3 * total_retries, 30)
            print(f"Waiting {wait}s...")
            time.sleep(wait)

        except Exception as e:
            total_retries += 1
            print(f"Error (retry {total_retries}/{max_retries}): {e}")
            wait = min(3 * total_retries, 30)
            print(f"Waiting {wait}s...")
            time.sleep(wait)

    return False

if __name__ == "__main__":
    success = download_with_resume(URL, OUTPUT)
    if success:
        print("SUCCESS - now run: pip install " + OUTPUT)
    else:
        print("FAILED after all retries")
    sys.exit(0 if success else 1)