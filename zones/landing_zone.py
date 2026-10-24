#region Setup
#Necessary imports
import os
from pathlib import Path

import kagglehub #type:ignore
import pyarrow.parquet as pq #type:ignore
from huggingface_hub import snapshot_download #type:ignore

from zones.client import S3Client

#Set up the connection with minio
client = S3Client()
s3 = client.s3

#One bucket with two "folders": the Formatted Zone reads from landing-zone/persistent_landing/<media_type>/
BUCKET = "landing-zone"
TEMPORAL, PERSISTENT = "temporal_landing/", "persistent_landing/"
try: s3.create_bucket(Bucket=BUCKET)
except s3.exceptions.BucketAlreadyOwnedByYou: pass
#endregion

#region Temporal Landing

# ---------------------------------------------------------------------------
# Data sources registry
# ---------------------------------------------------------------------------
# source     -> where the data comes from (used in the persistent file name)
# dataset    -> short dataset name (used in the persistent file name; no "$")
# media_type -> Persistent Landing folder the whole dataset goes to
# repo_id / allow_patterns -> Hugging Face repository and which files to fetch
# handle     -> Kaggle dataset handle
DATA_SOURCES = [
    {
        "source": "huggingface",
        "dataset": "animal-sounds",
        "repo_id": "cgeorgiaw/animal-sounds",
        "media_type": "audio",
        # Only the "birds" subset: its .wav files plus its metadata.csv.
        "allow_patterns": ["birds/*"],
    },
    {
        "source": "huggingface",
        "dataset": "animalimages",
        "repo_id": "ardavkocak/animalimages",
        "media_type": "images",
        # Images are published embedded in parquet shards.
        "allow_patterns": ["data/*"],
    },
    {
        "source": "huggingface",
        "dataset": "animal-dataset",
        "repo_id": "nirmalendu01/animal_dataset",
        "media_type": "images",
        "allow_patterns": ["images/train-00010-of-00025.parquet"],
    },
    {
        "source": "huggingface",
        "dataset": "animals-info",
        "repo_id": "PenguinPush/animals-info",
        "media_type": "text",
        "allow_patterns": ["*.csv"],
    },
    {
        "source": "kaggle",
        "dataset": "animal-species-data",
        "handle": "kennyloic/animal-species-data",
        "media_type": "text",
    },
]

#Download the raw files of each dataset into downloaded_data/<media_type>/<source>/<dataset>/ (re-runs skip what is already there)
for source in DATA_SOURCES:
    if source["source"] == "huggingface":
        snapshot_download(
            source["repo_id"],
            repo_type="dataset",
            allow_patterns=source["allow_patterns"],
            local_dir=f"downloaded_data/{source['media_type']}/{source['source']}/{source['dataset']}",
        )
    elif source["source"] == "kaggle":
        kagglehub.dataset_download(
            source["handle"],
            output_dir=f"downloaded_data/{source['media_type']}/{source['source']}/{source['dataset']}",
        )
    else:
        raise ValueError(f"Unknown source: {source['source']}")


#Dump every file as temporal_landing/<media_type>/<source>/<dataset>/<original path>
for path in Path("downloaded_data").rglob("*"):
    if not path.is_file() or any(part.startswith(".") for part in path.parts): continue #.cache/.complete are the downloaders' bookkeeping
    key = f"{TEMPORAL}{path.relative_to('downloaded_data').as_posix()}"
    if key.startswith(f"{TEMPORAL}images/") and path.suffix == ".parquet":
        #The images are published inside parquet files: land each one as its own file, bytes untouched
        split = path.name.split("-")[0] #train or test
        cols = ["image", "file_name"] if "nirmalendu01" in key else ["image"]
        table = pq.read_table(path, columns=cols)
        for i, image in enumerate(table.column("image").to_pylist()):
            #image['path'] may be None; use file_name column if available
            filename = table.column("file_name")[i].as_py() if "file_name" in table.column_names else image['path']
            s3.put_object(Bucket=BUCKET, Key=f"{key.rsplit('/', 2)[0]}/{split}/{filename}", Body=image["bytes"])
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
