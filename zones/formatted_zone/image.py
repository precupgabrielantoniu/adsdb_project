#Necessary imports
import os
from io import BytesIO
from PIL import Image #type:ignore

from tqdm import tqdm #type:ignore

from zones.client import S3Client #type:ignore


client = S3Client()
s3 = client.s3

#Check existence and set up the source (landing zone) and target (formatted zone) buckets and "folders"
SOURCE_BUCKET = "landing-zone"
SOURCE_PREFIX = "persistent_landing/images/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "formatted-zone"
TARGET_PREFIX = "images/"
client.bucket_exists(TARGET_BUCKET, True)
print("Connection to buckets achieved")

def to_jpg(image_bytes):
    """Converts raw image bytes of any Pillow-supported static format to JPEG bytes."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB") #For alpha channels
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer

#Count total images for the progress bar
count_paginator = s3.get_paginator('list_objects_v2')
total_images = sum(
    len(page.get('Contents', []))
    for page in count_paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
)

#Pick all of the images from the bucket, convert each to .jpg, and upload them to the formatted zone
paginator = s3.get_paginator('list_objects_v2')
with tqdm(total=total_images, desc=f"Moving images to {TARGET_BUCKET}") as progress:
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

            progress.update(1)#Update the progress bar

print(f"Loaded all images to {TARGET_BUCKET}")
