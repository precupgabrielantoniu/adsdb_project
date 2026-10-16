#region Setup
#Necessary imports
import os
from pathlib import Path

import boto3 #type:ignore
import kagglehub #type:ignore
import pyarrow.parquet as pq #type:ignore
from huggingface_hub import snapshot_download #type:ignore

from config import MINIO_ENDPOINT_URL, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER #type:ignore

#Set up the connection with minio
s3 = boto3.client('s3',
                  endpoint_url=MINIO_ENDPOINT_URL,
                  aws_access_key_id=MINIO_ROOT_USER,
                  aws_secret_access_key=MINIO_ROOT_PASSWORD)

#One bucket with two "folders": the Formatted Zone reads from landing-zone/persistent_landing/<media_type>/
BUCKET = "landing-zone"
TEMPORAL, PERSISTENT = "temporal_landing/", "persistent_landing/"
try: s3.create_bucket(Bucket=BUCKET)
except s3.exceptions.BucketAlreadyOwnedByYou: pass
#endregion

#region Temporal Landing
#Download the raw files of each dataset into downloaded_data/<media_type>/<source>/<dataset>/ (re-runs skip what is already there)
snapshot_download("cgeorgiaw/animal-sounds", repo_type="dataset", allow_patterns="birds/*", local_dir="downloaded_data/audio/huggingface/animal-sounds")
snapshot_download("ardavkocak/animalimages", repo_type="dataset", allow_patterns="data/*", local_dir="downloaded_data/images/huggingface/animalimages")
snapshot_download("nirmalendu01/animal_dataset", repo_type="dataset", allow_patterns="data/*", local_dir="downloaded_data/text/huggingface/animal-dataset")
snapshot_download("PenguinPush/animals-info", repo_type="dataset", allow_patterns="*.csv", local_dir="downloaded_data/text/huggingface/animals-info")
kagglehub.dataset_download("kennyloic/animal-species-data", output_dir="downloaded_data/text/kaggle/animal-species-data")

#Dump every file as temporal_landing/<media_type>/<source>/<dataset>/<original path>
for path in Path("downloaded_data").rglob("*"):
    if not path.is_file() or any(part.startswith(".") for part in path.parts): continue #.cache/.complete are the downloaders' bookkeeping
    key = f"{TEMPORAL}{path.relative_to('downloaded_data').as_posix()}"
    if key.startswith(f"{TEMPORAL}images/") and path.suffix == ".parquet":
        #The images are published inside parquet files: land each one as its own file, bytes untouched
        split = path.name.split("-")[0] #train or test
        for image in pq.read_table(path, columns=["image"]).column("image").to_pylist():
            s3.put_object(Bucket=BUCKET, Key=f"{key.rsplit('/', 2)[0]}/{split}/{image['path']}", Body=image["bytes"])
    else:
        s3.upload_file(str(path), BUCKET, key)
#endregion

#region Persistent Landing
#Move every temporal file to persistent_landing/<media_type>/<source>$<dataset>$<dd-mm-yyyy>$<original_name>.<ext>
#The date is when the file landed in temporal (its LastModified)
paginator = s3.get_paginator('list_objects_v2')
objects = [obj for page in paginator.paginate(Bucket=BUCKET, Prefix=TEMPORAL) for obj in page.get('Contents', [])]
for obj in objects:
    media_type, source, dataset, original = obj["Key"].removeprefix(TEMPORAL).split("/", 3)
    stem, ext = os.path.splitext(original)
    target_key = f"{PERSISTENT}{media_type}/{source}${dataset}${obj['LastModified']:%d-%m-%Y}${stem.replace('/', '_')}{ext.lower()}"
    s3.copy_object(Bucket=BUCKET, Key=target_key, CopySource={"Bucket": BUCKET, "Key": obj["Key"]})
    s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
print(f"Moved {len(objects)} files to {BUCKET}/{PERSISTENT}")
#endregion
