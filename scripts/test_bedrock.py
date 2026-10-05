"""Make a small live Bedrock Converse call using the configured AWS identity."""

from __future__ import annotations

import argparse
import os
import sys
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Optional locally configured AWS SSO profile")
    args = parser.parse_args()

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    model_id = os.getenv("ATLAS_BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    if not region:
        print("Set AWS_REGION (and enable the model in that region) before testing.", file=sys.stderr)
        return 2

    try:
        session = boto3.Session(profile_name=args.profile, region_name=region)
        identity = session.client("sts").get_caller_identity()
        client = session.client("bedrock-runtime")
        started = time.perf_counter()
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Reply with exactly: ATLAS_BEDROCK_LIVE_OK"}],
                }
            ],
            inferenceConfig={"maxTokens": 40, "temperature": 0},
        )
    except (BotoCoreError, ClientError) as exc:
        print(
            f"Live Bedrock test failed ({type(exc).__name__}). Check SSO login, "
            "region, model access, and bedrock:InvokeModel permission.",
            file=sys.stderr,
        )
        return 1

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    text = " ".join(
        block.get("text", "")
        for block in response["output"]["message"]["content"]
        if block.get("text")
    ).strip()
    if not text:
        print("Bedrock returned no text content.", file=sys.stderr)
        return 1

    print(f"Live Bedrock call succeeded: model={model_id}, region={region}, latency_ms={elapsed_ms}")
    print(f"AWS identity authenticated: {'yes' if identity.get('Arn') else 'unknown'}")
    print(f"Model response: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
