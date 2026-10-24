import boto3#type:ignore
from botocore.exceptions import ClientError#type:ignore

from config import MINIO_ROOT_PASSWORD, MINIO_ROOT_USER, MINIO_ENDPOINT_URL

class S3Client:
    def __init__(self):
        # set up the connection with minio
        self.s3 = boto3.client('s3',
                          endpoint_url=MINIO_ENDPOINT_URL,
                          aws_access_key_id=MINIO_ROOT_USER,
                          aws_secret_access_key=MINIO_ROOT_PASSWORD)


    def bucket_exists(self, bucket_name, create = False):
        try:
            self.s3.head_bucket(Bucket=bucket_name)
        except ClientError:
            if create:
                self.s3.create_bucket(Bucket=bucket_name)
                print("Created bucket for " + bucket_name)
            else:
                raise Exception(bucket_name + " bucket does not exist")