#Necessary imports
import os
from io import BytesIO
from PIL import Image #type:ignore

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
SOURCE_BUCKET = "landing-zone"
SOURCE_PREFIX = "persistent_landing/images/"
try: s3.head_bucket(Bucket=SOURCE_BUCKET)
except ClientError: raise Exception("Landing Zone bucket does not exist")

TARGET_BUCKET = "formatted-zone"
TARGET_PREFIX = "images/"
try: s3.head_bucket(Bucket=TARGET_BUCKET)
except ClientError:
    #If the bucket does not exist then this might be the first time the script is being run so create it
    s3.create_bucket(Bucket = "formatted-zone")
    print("Created bucket for the Formatted Zone")
    
def to_jpg(image_bytes):
    """Converts raw image bytes of any Pillow-supported static format to JPEG bytes."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB") #For alpha channels
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer

#Pick all of the images from the bucket, convert each to .jpg, and upload them to the formatted zone
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
    for image in page.get('Contents', []):
        #Get the image
        key = image['Key']
        source_object = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
        image_bytes = source_object['Body'].read()

        #Transform the image into jpg no matter the type
        jpg_image = to_jpg(image_bytes)

        #Save the image to the formatted zone 
        file_stem = os.path.splitext(os.path.basename(key))[0]
        target_key = f"{TARGET_PREFIX}{file_stem}.jpg"
        s3.upload_fileobj(jpg_image, TARGET_BUCKET, target_key) #Access to the bucket was checked previously
