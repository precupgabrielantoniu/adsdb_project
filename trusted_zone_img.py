#region Setup
#Necessary imports
import os
import hashlib
from io import BytesIO

import boto3 #type:ignore
from botocore.client import Config #type:ignore
from botocore.exceptions import ClientError #type:ignore
from PIL import Image, ImageStat
from tqdm import tqdm #type:ignore

from config import MINIO_ENDPOINT_URL, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER #type:ignore

#Set up the connection with minio
s3 = boto3.client('s3',
                  endpoint_url=MINIO_ENDPOINT_URL,
                  aws_access_key_id=MINIO_ROOT_USER,
                  aws_secret_access_key=MINIO_ROOT_PASSWORD)

#Check existence and set up the source (landing zone) and target (formatted zone) buckets and "folders"
SOURCE_BUCKET = "formatted-zone"
SOURCE_PREFIX = "images/"
try: s3.head_bucket(Bucket=SOURCE_BUCKET)
except ClientError: raise Exception("Formatted Zone bucket does not exist")

TARGET_BUCKET = "trusted-zone"
TARGET_PREFIX = "images/"
try: s3.head_bucket(Bucket=TARGET_BUCKET)
except ClientError:
    #If the bucket does not exist then this might be the first time the script is being run so create it
    s3.create_bucket(Bucket = "trusted-zone")
    print("Created bucket for the Trusted Zone")
#endregion

#region Image quality analysis

#initialize lists to keep lightweight metadata per image (key, dimensions, hash)
image_records = []   # One dict per readable image: {key, width, height, hash}
corrupt_keys = []    # Keys of images that failed to decode at all

#Count total images for the progress bar
count_paginator = s3.get_paginator('list_objects_v2')
total_images = sum(
    len(page.get('Contents', []))
    for page in count_paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
)

#Set a low boundry for flat images
FLAT_STDDEV_THRESHOLD = 5
#download each image once, check it's readable, and record its hash and size
paginator = s3.get_paginator('list_objects_v2')
with tqdm(total=total_images, desc=f"Checking corruption and pixel variance") as progress:
    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
        for image in page.get('Contents', []):
            key = image['Key']
            image_bytes = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)['Body'].read()

            #use.load() to raise an error if the file is truncated or otherwise broken.
            try:
                img = Image.open(BytesIO(image_bytes))
                img.load()
            except Exception:
                corrupt_keys.append(key)
                continue

            #Keep MD5 of the raw bytes to assert duplicates
            content_hash = hashlib.md5(image_bytes).hexdigest()

            #convert to grayscale and measure how spread out the pixel values are (standard deviation)
            width, height = img.size
            gray = img.convert("L")
            global_stddev = ImageStat.Stat(gray).stddev[0]

            #Check variance in a grid of four
            half_w, half_h = width // 2, height // 2
            quadrants = [
                gray.crop((0, 0, half_w, half_h)),
                gray.crop((half_w, 0, width, half_h)),
                gray.crop((0, half_h, half_w, height)),
                gray.crop((half_w, half_h, width, height)),]
            quadrant_stddevs = [ImageStat.Stat(q).stddev[0] for q in quadrants]

            #if it has low enough variation mark the image as blank or a solid colour 
            is_flat = global_stddev < FLAT_STDDEV_THRESHOLD 
            #if any of the grids has the same property flag the image as partly blank
            is_part_flat = any(s < FLAT_STDDEV_THRESHOLD for s in quadrant_stddevs)

            image_records.append({
                "key": key,
                "width": width,
                "height": height,
                "hash": content_hash,
                "is_flat": is_flat,
                "is_part_flat" : is_part_flat,
            })
            progress.update(1)#Update the progress bar

#Detect duplicate hashes (same images) and mark the duplicated
print("Detecting duplicates")
seen_hashes = set()
for record in image_records:
    record["is_duplicate"] = record["hash"] in seen_hashes
    seen_hashes.add(record["hash"])

#find outliers by size
print("Detecting size outliers")
areas = sorted(r["width"] * r["height"] for r in image_records if not r["is_duplicate"]) #get all sizes in order

if areas: #use IQR to determine a range for the outliers
    q1 = areas[len(areas) // 4] 
    q3 = areas[(3 * len(areas)) // 4]
    iqr = q3 - q1
    lower_bound, upper_bound = q1 - 1.5 * iqr, q3 + 1.5 * iqr
else:
    lower_bound, upper_bound = 0, 0

for record in image_records: #Check each image is within the range and flag those that are not
    area = record["width"] * record["height"]
    record["is_size_outlier"] = area < lower_bound or area > upper_bound

#Print a small summary with the information found
print(f"\nChecked {len(image_records) + len(corrupt_keys)} images")
print(f"  Corrupt (unreadable): {len(corrupt_keys)}")
print(f"  Duplicates: {sum(r['is_duplicate'] for r in image_records)}")
print(f"  Size outliers: {sum(r['is_size_outlier'] for r in image_records)}")
print(f"  Flat/blank image: {sum(r['is_flat'] for r in image_records)}")
print(f"  Partly flat/blank image: {sum(r['is_part_flat'] for r in image_records)}\n")

with tqdm(total=total_images, desc=f"Moving {total_images} to {TARGET_BUCKET}") as progress:
    for record in image_records: #For every image
        if record["is_duplicate"]: #If it is duplicated do not save it
            continue
        #save the non duplicated non corrupt images to the trusted zone (others will be saved just reported on)
        target_key = f"{TARGET_PREFIX}{os.path.basename(record['key'])}"
        s3.copy_object(
            Bucket=TARGET_BUCKET,
            CopySource={"Bucket": SOURCE_BUCKET, "Key": record["key"]},
            Key=target_key,
        )
        progress.update(1)#Update the progress bar
#endregion