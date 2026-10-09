import boto3 #type:ignore  
from botocore.client import Config #type:ignore
from botocore.exceptions import ClientError

#Create bucket
s3 = boto3.client('s3',
                  endpoint_url='http://localhost:9000',
                  aws_access_key_id='minioadmin',
                  aws_secret_access_key='minioadmin')

try:
    s3.create_bucket(Bucket = "landing_zone")
    print("Bucket created landing zone")
except ClientError as e:
    if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
        print("Bucket exists")
else: raise 

#For file in folder 

    #Hugging face


#Put in bucket =)