import os

from tqdm import tqdm

from zones.client import S3Client
from io import BytesIO
from pydub import AudioSegment
import csv
from io import StringIO

client = S3Client()
s3 = client.s3

SOURCE_BUCKET = "landing-zone"
SOURCE_PREFIX = "persistent_landing/audio/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "formatted-zone"
TARGET_PREFIX = "audio/"
client.bucket_exists(TARGET_BUCKET, True)
print("Connection to buckets achieved")

# progress bar
count_paginator = s3.get_paginator('list_objects_v2')
total_audio = sum(
    len(page.get('Contents', []))
    for page in count_paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
)

def to_wav(audio_bytes_wav):
    # converts audio bytes into .wav format
    # load the original audio from memory
    decoded_audio = AudioSegment.from_file(BytesIO(audio_bytes_wav))

    # convert to wav in memory
    wav_buffer = BytesIO()
    decoded_audio.export(wav_buffer, format="wav")

    return wav_buffer.getvalue()

# iterate through items in bucket
paginator = s3.get_paginator('list_objects_v2')

metadata_by_filename = {}

# first loop for metadata files
for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
    for csv_files in page.get('Contents', []):
        key = csv_files['Key']

        if not key.lower().endswith('.csv'):
            continue

        # parse csv
        response = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
        with response["Body"] as body:
            csv_text = body.read().decode("utf-8-sig")

        reader = csv.DictReader(StringIO(csv_text))

        # prefix always the same for metadata file and audio file
        # that's how we match them together
        csv_filename = os.path.basename(key)
        prefix = csv_filename.removesuffix("metadata.csv")

        for row in reader:
            audio_filename = prefix + row["file_name"]
            metadata_by_filename[audio_filename] = {
                "label": row["label"]
            }

# second loop to go through audio files
with tqdm(total=total_audio, desc="Formatting audio data") as progress:
    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
        for audio in page.get('Contents', []):
            key = audio['Key']

            if key.lower().endswith('.csv'):
                continue

            source_object = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
            audio_bytes = source_object['Body'].read()

            # don't transform if already .wav
            if not key.lower().endswith('.wav'):
                # transform to .wav
                audio_bytes = to_wav(audio_bytes)

            # save the audio + metadata to the formatted zone
            file_stem = os.path.splitext(os.path.basename(key))[0]
            target_key = f"{TARGET_PREFIX}{file_stem}.wav"

            filename = os.path.basename(key)
            try:
                metadata = metadata_by_filename[filename]
            except KeyError: # just in case there is no metadata available
                metadata = {}

            s3.put_object(
                Bucket=TARGET_BUCKET,
                Key=target_key,
                Body=audio_bytes,
                ContentType="audio/wav",
                Metadata=metadata
            )
            progress.update(1)

print("Successfully formatted audio data")


