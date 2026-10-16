#region Setup
#Necessary imports
import os
import json
from collections import defaultdict
from tqdm import tqdm #type:ignore

import boto3 #type:ignore
from botocore.client import Config #type:ignore
from botocore.exceptions import ClientError #type:ignore

from dotenv import load_dotenv #type:ignore

load_dotenv()

#Set up the connection with minio
MINIO_ENDPOINT_URL = os.environ['MINIO_ENDPOINT_URL']
MINIO_ROOT_USER = os.environ['MINIO_ROOT_USER']
MINIO_ROOT_PASSWORD = os.environ['MINIO_ROOT_PASSWORD']

s3 = boto3.client('s3',
                  endpoint_url=MINIO_ENDPOINT_URL,
                  aws_access_key_id=MINIO_ROOT_USER,
                  aws_secret_access_key=MINIO_ROOT_PASSWORD)

#Check existence and set up the source (landing zone) and target (formatted zone) buckets and "folders"
SOURCE_BUCKET = "formatted-zone"
SOURCE_PREFIX = "text/"
try: s3.head_bucket(Bucket=SOURCE_BUCKET)
except ClientError: raise Exception("Formatted Zone bucket does not exist")

TARGET_BUCKET = "trusted-zone"
TARGET_PREFIX = "text/"
try: s3.head_bucket(Bucket=TARGET_BUCKET)
except ClientError:
    #If the bucket does not exist then this might be the first time the script is being run so create it
    s3.create_bucket(Bucket = "trusted-zone")
    print("Created bucket for the Trusted Zone")
#endregion

#Count total text files for the progress bar
count_paginator = s3.get_paginator('list_objects_v2')
total_text = sum(
    len(page.get('Contents', []))
    for page in count_paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
)

def is_well_formatted(value):
    """A value counts as well-formatted if it starts capitalized or with a digit.
    Checked in general across ALL values of a record, not per specific attribute,
    since which attributes exist varies from dataset to dataset."""
    text = str(value)
    if text == "":
        return True
    first_char = text[0]
    return first_char.isupper() or first_char.isdigit()

text_records = []

#Tracks attribute emptiness across all datasets
attribute_stats = defaultdict(lambda: {"empty": 0, "present": 0})

#region Text quality analysis
paginator = s3.get_paginator('list_objects_v2')
with tqdm(total=total_text, desc="Checking text data quality") as progress:
    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
        for text_file in page.get('Contents', []):
            key = text_file["Key"]

            #listing metadata (Key/ETag/Size/...) and actual json file.
            response = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
            records = json.loads(response['Body'].read())
            if isinstance(records, dict):
                records = [records]

            has_empty_chars = False
            badly_formatted = False
            attribute_count = 0

            #Check per attribute if it is empty in this specific instance and flag
            for record in records:
                attribute_count += len(record)
                for attribute, value in record.items():
                    if value == "":
                        has_empty_chars = True
                        attribute_stats[attribute]["empty"] += 1
                    else:
                        attribute_stats[attribute]["present"] += 1
                        if not is_well_formatted(value): #If the attribute is badly formatted (does not start with number or capital letter, flag it)
                            badly_formatted = True

            text_records.append({
                            "key": key,
                            "length": attribute_count,
                            "has_empty_chars": has_empty_chars,
                            "badly_formatted" : badly_formatted,
                        })
            progress.update(1)#Update the progress bar


print(f"\nChecked {total_text} texts")
print(f"  Have empty characteristics: {sum(r['has_empty_chars'] for r in text_records)}")
print(f"  Badly formatted: {sum(r['badly_formatted'] for r in text_records)}")

#Per-attribute emptiness report, worst (most empty) first
print("\nEmptiness by attribute:")
for attribute, counts in sorted(attribute_stats.items(),
    key=lambda item: item[1]["empty"] / (item[1]["empty"] + item[1]["present"]), reverse=True,):
    total = counts["empty"] + counts["present"]
    rate = counts["empty"] / total
    print(f"  {attribute}: {counts['empty']}/{total} empty ({rate:.0%})")

with tqdm(total=total_text, desc=f"Moving {total_text} to {TARGET_BUCKET}") as progress:
    for record in text_records: #For every image
        #save the text to the target bucket
        target_key = f"{TARGET_PREFIX}{os.path.basename(record['key'])}"
        s3.copy_object(
            Bucket=TARGET_BUCKET,
            CopySource={"Bucket": SOURCE_BUCKET, "Key": record["key"]},
            Key=target_key,
        )
        progress.update(1)#Update the progress bar    

#endregion