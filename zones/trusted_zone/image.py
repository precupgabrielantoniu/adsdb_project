#region Setup
#Necessary imports
import datetime
import os
import hashlib
import tempfile
from io import BytesIO

import altair as alt #type:ignore
import pandas as pd
from PIL import Image, ImageStat
from tqdm import tqdm #type:ignore
from pylatex import Document, Figure, LongTable, NoEscape, Section, Subsection #type:ignore

from zones.client import S3Client #type:ignore

#Set up the connection with minio
client = S3Client()
s3 = client.s3

#Check existence and set up the source (landing zone) and target (formatted zone) buckets and "folders"
SOURCE_BUCKET = "formatted-zone"
SOURCE_PREFIX = "images/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "trusted-zone"
TARGET_PREFIX = "images/"
client.bucket_exists(TARGET_BUCKET, True)

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
            #if any of the grids has the same property flag the image as partly blank (fully flat images are already counted above)
            is_part_flat = not is_flat and min(quadrant_stddevs) < FLAT_STDDEV_THRESHOLD

            image_records.append({
                "key": key,
                "width": width,
                "height": height,
                "area": width * height,
                "hash": content_hash,
                "stddev": global_stddev,
                "min_quadrant_stddev": min(quadrant_stddevs),
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

#endregion

#region Report
#Print a small summary with the information found
print(f"\nChecked {len(image_records) + len(corrupt_keys)} images")
print(f"  Corrupt (unreadable): {len(corrupt_keys)}")
print(f"  Duplicates: {sum(r['is_duplicate'] for r in image_records)}")
print(f"  Size outliers: {sum(r['is_size_outlier'] for r in image_records)}")
print(f"  Flat/blank image: {sum(r['is_flat'] for r in image_records)}")
print(f"  Partly flat/blank image: {sum(r['is_part_flat'] for r in image_records)}\n")

#Settings for table and image assets in the report
SAMPLE_COUNT = 4 #thumbnails shown per category
TABLE_LIMIT = 20 #rows listed per category before cutting the table short
THUMB_SIZE = 200 #thumbnail side in pixels
assets_dir = tempfile.mkdtemp() #holds the chart and thumbnails embedded in the pdf

def add_key_table(doc, header, rows):
    """Add a table listing the flagged images, capped at TABLE_LIMIT rows"""
    if not rows: return
    with doc.create(LongTable("l" + "|r" * (len(header) - 1))) as table: #LongTable breaks across pages, Tabular doesn't
        table.add_hline()
        table.add_row(header)
        table.add_hline()
        table.end_table_header() #repeat the header on every page
        for row in rows[:TABLE_LIMIT]:
            table.add_row(row)
        table.add_hline()
    if len(rows) > TABLE_LIMIT:
        doc.append(f"Only the first {TABLE_LIMIT} of {len(rows)} images are listed. ")

def add_samples(doc, keys, name, caption):
    """Download a few flagged images and show them side by side as one strip"""
    keys = keys[:SAMPLE_COUNT]
    if not keys: return
    strip = Image.new("RGB", (THUMB_SIZE * len(keys), THUMB_SIZE), "white")
    for i, key in enumerate(keys):
        thumb = Image.open(BytesIO(s3.get_object(Bucket=SOURCE_BUCKET, Key=key)['Body'].read())).convert("RGB")
        thumb.thumbnail((THUMB_SIZE, THUMB_SIZE)) #shrink keeping the aspect ratio
        strip.paste(thumb, (i * THUMB_SIZE + (THUMB_SIZE - thumb.width) // 2, (THUMB_SIZE - thumb.height) // 2)) #centre it in its slot
    strip_path = os.path.join(assets_dir, f"{name}.png")
    strip.save(strip_path)
    with doc.create(Figure(position="h!")) as figure:
        figure.add_image(strip_path, width=NoEscape(f"{0.24 * len(keys):.2f}\\textwidth"))
        figure.add_caption(caption)

#Boxplot of image areas, whiskers at 1.5 IQR like the outlier rule above so the dots are the outliers
size_df = pd.DataFrame({"area": areas})
size_chart_path = os.path.join(assets_dir, "size_boxplot.png")
if not size_df.empty:
    alt.Chart(size_df).mark_boxplot(extent=1.5, size=40, color="#2a78d6").encode(
        x=alt.X("area:Q", title="Image area (width x height, px)"),
    ).properties(width=450, height=80).save(size_chart_path, ppi=200)

#Create a pdf report through latex
geometry_options = {"margin": "2.5cm"}
doc = Document(geometry_options=geometry_options)

with doc.create(Section("Image quality report")):
    doc.append(f"This document shows results for a total of {total_images} image instances for the animal identification project pipeline.")
    with doc.create(Subsection("Corrupt images")):
        doc.append(f"A total of {len(corrupt_keys)} images were found to be corrupted and so unreadable. These images are not moved to the trusted zone. ")
        add_key_table(doc, ["Image"], [[os.path.basename(k)] for k in corrupt_keys])

    with doc.create(Subsection("Duplicate images")):
        doc.append("Duplicates are detected by computing an MD5 hash of each file's raw bytes: two images with the same hash are byte-for-byte identical. The first image seen is kept and later copies are flagged. ")
        doc.append(f"A total of {len([r for r in image_records if r["is_duplicate"]])} images were found to be duplicates of other images. Duplicates are not moved to the trusted zone. ")
        add_key_table(doc, ["Image"], [[os.path.basename(r["key"])] for r in image_records if r["is_duplicate"]])

    with doc.create(Subsection("Size outliers")):
        doc.append("To find outliers size is measured as the area (width x height) of each unique image. Using the interquartile range (IQR = Q3 - Q1), ")
        doc.append(f"an image is an outlier when its area is below Q1 - 1.5 IQR ({lower_bound:,.0f} px) or above Q3 + 1.5 IQR ({upper_bound:,.0f} px). ")
        doc.append(f"A total of {len((r for r in image_records if r["is_size_outlier"]))} images were found to be size outliers.")
        if os.path.exists(size_chart_path):
            with doc.create(Figure(position="h!")) as figure:
                figure.add_image(size_chart_path, width=NoEscape(r"0.8\textwidth"))
                figure.add_caption("Distribution of image areas. Points beyond the whiskers are size outliers.")
        add_key_table(doc, ["Image", "Width", "Height", "Area (px)"],
                      [[os.path.basename(r["key"]), r["width"], r["height"], f"{r['area']:,}"] for r in sorted((r for r in image_records if r["is_size_outlier"]), key=lambda r: r["area"], reverse=True)])

    with doc.create(Subsection("Flat/blank images")):
        doc.append("To find flat images each image is converted to grayscale and the standard deviation of its pixel values is measured. ")
        doc.append(f"A low standard deviation means the pixels barely change, so an image with a standard deviation below {FLAT_STDDEV_THRESHOLD} (on a 0-255 scale) is considered flat: blank or a single solid colour. ")
        doc.append(f"A total of {len((r for r in image_records if r["is_flat"]))} images were found to be flat.")
        add_samples(doc, [r["key"] for r in sorted((r for r in image_records if r["is_flat"]), key=lambda r: r["stddev"])], "flat_samples", "Sample flat images (lowest standard deviation first).")
        add_key_table(doc, ["Image", "Std. deviation"], [[os.path.basename(r["key"]), f"{r['stddev']:.2f}"] for r in sorted((r for r in image_records if r["is_flat"]), key=lambda r: r["stddev"])])

    with doc.create(Subsection("Partly flat/blank images")):
        doc.append("Some images are only partly blank, e.g. a cropped or padded image with a solid border. To catch these, the grayscale image is split into four quadrants and the same standard deviation is measured in each one. ")
        doc.append(f"An image that is not flat overall but has at least one quadrant below {FLAT_STDDEV_THRESHOLD} is considered partly flat. ")
        doc.append("This can also flag genuine photos with a uniform region such as a clear sky or a dark background, so the samples below should be checked. ")
        doc.append(f"A total of {len(r for r in image_records if r["is_part_flat"])} images were found to be partly flat.")
        add_samples(doc, [r["key"] for r in sorted((r for r in image_records if r["is_part_flat"]), key=lambda r: r["min_quadrant_stddev"])], "part_flat_samples", "Sample partly flat images (flattest quadrant first).")
        add_key_table(doc, ["Image", "Lowest quadrant std. deviation"], [[os.path.basename(r["key"]), f"{r['min_quadrant_stddev']:.2f}"] for r in len(r for r in image_records if r["is_part_flat"])])

path = "zones/trusted_zone/quality_reports/"
if not os.path.exists(path): os.mkdir(path)#Create directory to save the pdf in if nonexistent
doc.generate_pdf(filepath = os.path.join(path,f"image_quality_report_{datetime.date.today()}"), clean_tex=True) #save as pdf
#endregion

#endregion

#region Moving to Trusted zone
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