import json
import csv
import os
from io import StringIO, BytesIO

import pandas as pd

from zones.client import S3Client

client = S3Client()
s3 = client.s3

SOURCE_BUCKET = "landing-zone"
SOURCE_PREFIX = "persistent_landing/text/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "formatted-zone"
TARGET_PREFIX = "text/"
client.bucket_exists(TARGET_BUCKET, True)

def parquet_to_json(parquet_bytes):
    df = pd.read_parquet(BytesIO(parquet_bytes), engine="pyarrow")
    json_text = df.to_json(
        orient="records",
        indent=4,
        date_format="iso",
        force_ascii=False
    )
    return json_text.encode("utf-8")

def csv_to_json(csv_bytes):
    # decode csv bytes into text
    csv_text = csv_bytes.decode("utf-8-sig")

    # read csv rows
    csv_reader = csv.DictReader(StringIO(csv_text))
    rows = list(csv_reader)

    # convert
    json_text = json.dumps(rows, indent=4)
    return json_text.encode("utf-8")

# iterate through items in bucket
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
    for text in page.get('Contents', []):
        key = text['Key']
        source_object = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
        text_bytes = source_object['Body'].read()

        # script only transforms .csv and .parquet into json
        if key.lower().endswith('.csv'):
            text_bytes = csv_to_json(text_bytes)
        elif key.lower().endswith('.parquet'):
            text_bytes = parquet_to_json(text_bytes)
        elif key.lower().endswith('.json'):
            # do nothing no need to transform
            pass
        else:
            continue

        file_stem = os.path.splitext(os.path.basename(key))[0]
        target_key = f"{TARGET_PREFIX}{file_stem}.json"

        s3.put_object(
            Bucket=TARGET_BUCKET,
            Key=target_key,
            Body=text_bytes,
            ContentType="application/json"
        )

    print("Successfully formatted text data")