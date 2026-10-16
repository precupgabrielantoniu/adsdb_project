import boto3
from config import MINIO_ROOT_PASSWORD, MINIO_ROOT_USER, MINIO_ENDPOINT_URL

class S3Client:
    # set up the connection with minio
    s3 = boto3.client('s3',
                      endpoint_url=MINIO_ENDPOINT_URL,
                      aws_access_key_id=MINIO_ROOT_USER,
                      aws_secret_access_key=MINIO_ROOT_PASSWORD)