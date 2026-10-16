#region Setup
#Necessary imports
import os

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

#region Text quality analysis
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
    for text_file in page.get('Contents', []):
        pass
#endregion