#region Setup
#Necessary imports
import os
import json
from collections import defaultdict
from tqdm import tqdm #type:ignore
from pylatex import Document, Tabular, Section, Subsection #type:ignore

from zones.client import S3Client #type:ignore

client = S3Client()
s3 = client.s3

#Check existence and set up the source (landing zone) and target (formatted zone) buckets and "folders"
SOURCE_BUCKET = "formatted-zone"
SOURCE_PREFIX = "text/"
client.bucket_exists(SOURCE_BUCKET)


TARGET_BUCKET = "trusted-zone"
TARGET_PREFIX = "text/"
client.bucket_exists(TARGET_BUCKET, True)

#endregion

#Count total text files for the progress bar
count_paginator = s3.get_paginator('list_objects_v2')
total_text = sum(
    len(page.get('Contents', []))
    for page in count_paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
)

def is_well_formatted(value):
    """A value counts as well-formatted if it starts capitalized or with a digit.
    Checked in general across ALL values of a record, not per specific attribute,
    since which attributes exist varies from dataset to dataset."""
    text = str(value)
    if text == "":
        return True
    first_char = text[0]
    return first_char.isupper() or first_char.isdigit()

text_records = []

#Tracks attribute emptiness across all datasets
attribute_stats = defaultdict(lambda: {"empty": 0, "present": 0})

#region Text quality analysis
paginator = s3.get_paginator('list_objects_v2')
with tqdm(total=total_text, desc="Checking text data quality") as progress:
    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
        for text_file in page.get('Contents', []):
            key = text_file["Key"]

            #listing metadata (Key/ETag/Size/...) and actual json file.
            response = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
            records = json.loads(response['Body'].read())
            if isinstance(records, dict):
                records = [records]

            has_empty_chars = False
            badly_formatted = False
            attribute_count = 0

            #Check per attribute if it is empty in this specific instance and flag
            for record in records:
                attribute_count += len(record)
                for attribute, value in record.items():
                    if value == "":
                        has_empty_chars = True
                        attribute_stats[attribute]["empty"] += 1
                    else:
                        attribute_stats[attribute]["present"] += 1
                        if not is_well_formatted(value): #If the attribute is badly formatted (does not start with number or capital letter, flag it)
                            badly_formatted = True

            text_records.append({
                            "key": key,
                            "length": attribute_count,
                            "has_empty_chars": has_empty_chars,
                            "badly_formatted" : badly_formatted,
                        })
            progress.update(1)#Update the progress bar
#endregion
#region Report
print(f"\nChecked {total_text} texts")
print(f"  Have empty characteristics: {sum(r['has_empty_chars'] for r in text_records)}")
print(f"  Badly formatted: {sum(r['badly_formatted'] for r in text_records)}")

#Per-attribute emptiness report, worst (most empty) first
print("\nEmptiness by attribute:")
for attribute, counts in sorted(attribute_stats.items(),
    key=lambda item: item[1]["empty"] / (item[1]["empty"] + item[1]["present"]), reverse=True,):
    total = counts["empty"] + counts["present"]
    rate = counts["empty"] / total
    print(f"  {attribute}: {counts['empty']}/{total} empty ({rate:.0%})")

#Create a pdf text through latex
geometry_options = {"tmargin": "1cm", "lmargin": "10cm"}
doc = Document(geometry_options=geometry_options)

with doc.create(Section("Text quality report")):
    doc.append(f"This document shows results for a total of {total_text} instances for the animal identification project pipeline.")
    with doc.create(Subsection("Attribute emptiness")):
        doc.append(f"A total of {sum(r['has_empty_chars'] for r in text_records)} observations were found to have empty characteristics")
        doc.append(f"Emptiness characteristics per attribute are as follows:")
        with doc.create(Tabular) as table:
            table.add_hline()
            table.add_row("Attribute", "Empty instances", "Total instances", "Rate of emptiness")
            for attribute, counts in sorted(attribute_stats.items(), key=lambda item: item[1]["empty"] / (item[1]["empty"] + item[1]["present"]), reverse=True,):
                total = counts["empty"] + counts["present"]
                rate = counts["empty"] / total
                table.add_hline()
                table.add_row((attribute, counts['empty'], total, f"{rate:.0%}" ))
            table.add_caption("Emptiness by attribute")
            #Potentially add a graph here with distribution of attributes ??

    with doc.create(Subsection("Formatting issues")):
        doc.add(f"A total of {sum(r['badly_formatted'] for r in text_records)} observations had baldy formatted attributes (not starting with uppercase or number)")

#endregion

#region Moving to trusted zone
with tqdm(total=total_text, desc=f"Moving {total_text} to {TARGET_BUCKET}") as progress:
    for record in text_records: #For every text
        #save the text to the target bucket
        target_key = f"{TARGET_PREFIX}{os.path.basename(record['key'])}"
        s3.copy_object(
            Bucket=TARGET_BUCKET,
            CopySource={"Bucket": SOURCE_BUCKET, "Key": record["key"]},
            Key=target_key,
        )
        progress.update(1)#Update the progress bar    

#endregion