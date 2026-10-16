import os

from zones.client import S3Client
from io import BytesIO
from pydub import AudioSegment

client = S3Client()
s3 = client.s3

SOURCE_BUCKET = "landing-zone"
SOURCE_PREFIX = "persistent_landing/audio/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "formatted-zone"
TARGET_PREFIX = "audio/"
client.bucket_exists(TARGET_BUCKET, True)
print("Connection to buckets achieved")


def to_wav(audio_bytes):
    # converts audio bytes into .wav format
    # load the original audio from memory
    decoded_audio = AudioSegment.from_file(BytesIO(audio_bytes))

    # convert to wav in memory
    wav_buffer = BytesIO()
    decoded_audio.export(wav_buffer, format="wav")

    return wav_buffer.getvalue()

# iterate through items in bucket
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
    for audio in page.get('Contents', []):
        key = audio['Key']

        # TODO: what are we doing with .csv file?
        if key.lower().endswith('.csv'):
            continue

        source_object = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
        audio_bytes = source_object['Body'].read()

        # don't transform if already .wav
        if not key.lower().endswith('.wav'):
            # transform to .wav
            audio_bytes = to_wav(audio_bytes)

        # save the audio to the formatted zone
        file_stem = os.path.splitext(os.path.basename(key))[0]
        target_key = f"{TARGET_PREFIX}{file_stem}.wav"
        s3.put_object(
            Bucket=TARGET_BUCKET,
            Key=target_key,
            Body=audio_bytes,
            ContentType="audio/wav"
        )

print("Successfully formatted audio data")


