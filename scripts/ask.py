"""Ask NikshayNavigator and measure streaming response performance."""

import argparse
import json
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    endpoint = f"{args.url.rstrip('/')}/v1/chat"

    try:
        with httpx.Client(timeout=90.0) as client:
            started = time.perf_counter()

            if args.json:
                response = client.post(
                    endpoint,
                    json={"message": args.message, "stream": False},
                )
                response.raise_for_status()
                data = response.json()

                print(data["answer"])
                print(
                    f"\n--- {data['provider']} / {data['model']}: "
                    f"tokens in={data['tokens_in']} "
                    f"out={data['tokens_out']} "
                    f"cost Rs {data['cost_inr']:.6f}"
                )
                return

            first_token = None
            metadata = {}
            event_name = ""

            with client.stream(
                "POST",
                endpoint,
                json={"message": args.message, "stream": True},
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(response.read().decode("utf-8"))

                async_stream_error = False

                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event_name = line.partition(":")[2].strip()

                    elif line.startswith("data:"):
                        payload = json.loads(line.partition(":")[2].strip())

                        if event_name == "error":
                            print("\nStreaming error:", payload)
                            async_stream_error = True
                            break

                        if event_name == "done":
                            metadata = payload

                        elif "delta" in payload:
                            if first_token is None:
                                first_token = time.perf_counter()
                            print(payload["delta"], end="", flush=True)

                    elif not line:
                        event_name = ""

            finished = time.perf_counter()

            if async_stream_error:
                raise RuntimeError("The LLM stream failed.")

            if not metadata:
                raise RuntimeError("Stream ended without a done event.")

            first_seconds = first_token - started if first_token else 0

            print(
                f"\n\n--- {metadata['provider']} / {metadata['model']}: "
                f"first words after {first_seconds:.2f} s, "
                f"total {finished - started:.2f} s"
            )
            print(
                f"    tokens in={metadata['tokens_in']} "
                f"out={metadata['tokens_out']} "
                f"cost Rs {metadata['cost_inr']:.6f} "
                f"attempts={metadata['attempts']} "
                f"fallback={'YES' if metadata['fallback_used'] else 'no'}"
            )

    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Request failed: {exc}")


if __name__ == "__main__":
    main()
