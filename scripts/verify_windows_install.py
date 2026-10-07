"""One real private-Windows numerical HTTP job for the installer smoke test."""
import argparse
import time

from caelab.workbench_client import Client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    client = Client(args.url)
    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    history = [identity, [[1.001, 0, 0], [0, 1, 0], [0, 0, 1]],
               [[1.002, 0, 0], [0, 1, 0], [0, 0, 1]]]
    job = client.submit("evaluate", {"backend": "material.felupe", "settings": {
        "time": [0, 1, 2], "deformation_gradient": history,
        "stress_unit": "MPa", "model": "linear_elastic",
        "parameters": {"E": 1000, "nu": 0.25}}})
    identifier = job["id"]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = client.status(identifier)
        if status["state"] in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            break
        time.sleep(0.25)
    else:
        raise AssertionError(f"Job {identifier} did not finish within 60 seconds")
    if status["state"] != "SUCCEEDED":
        raise AssertionError(f"Job {identifier} ended in {status['state']}")
    response = client.result(identifier)["responses"]["stress_xx"]
    actual = response["value"][1]
    if response["unit"] != "MPa" or abs(actual - 1.2) > 1e-8:
        raise AssertionError(f"Unexpected Hooke stress for {identifier}: {actual} {response['unit']}")
    print(f"PASS Windows private runtime: {identifier}, stress_xx[1]={actual:.8f} MPa")


if __name__ == "__main__":
    main()
