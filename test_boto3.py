import os
import boto3 #type:ignore
from botocore.client import Config #type:ignore
from dotenv import load_dotenv #type:ignore

load_dotenv()

MINIO_ENDPOINT_URL = os.environ['MINIO_ENDPOINT_URL']
MINIO_ROOT_USER = os.environ['MINIO_ROOT_USER']
MINIO_ROOT_PASSWORD = os.environ['MINIO_ROOT_PASSWORD']

#List all buckets and get one bucket
s3 = boto3.client('s3',
                  endpoint_url=MINIO_ENDPOINT_URL,
                  aws_access_key_id=MINIO_ROOT_USER,
                  aws_secret_access_key=MINIO_ROOT_PASSWORD)

response = s3.list_buckets()

# Output the bucket names
print('Existing buckets:')
for bucket in response['Buckets']:
    print(f'  {bucket["Name"]}')


#Uploading a file to a bucket
import logging
from botocore.exceptions import ClientError
import os


def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3',
                  endpoint_url=MINIO_ENDPOINT_URL,
                  aws_access_key_id=MINIO_ROOT_USER,
                  aws_secret_access_key=MINIO_ROOT_PASSWORD)
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True

upload_file("landing_zone.py", 'test')