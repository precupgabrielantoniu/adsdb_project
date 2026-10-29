import datetime
import hashlib
import os
import tempfile
import wave
from collections import Counter

import altair as alt
import numpy as np
import pandas as pd
from io import BytesIO
from pylatex import Document, Figure, LongTable, NoEscape, Section, Subsection
from pylatex.utils import escape_latex
from zones.client import S3Client
from tqdm import tqdm

client = S3Client()
s3 = client.s3

SOURCE_BUCKET = "formatted-zone"
SOURCE_PREFIX = "audio/"
client.bucket_exists(SOURCE_BUCKET)

TARGET_BUCKET = "trusted-zone"
TARGET_PREFIX = "audio/"
client.bucket_exists(TARGET_BUCKET, True)
print("Connection to buckets achieved")


# store audio quality results
audio_records = []
corrupt_keys = []
# count available and missing labels
label_counts = Counter()
missing_label_count = 0

# get wav files for the progress bar
paginator = s3.get_paginator("list_objects_v2")
audio_keys = [
    obj["Key"]
    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX)
    for obj in page.get("Contents", [])
    if obj["Key"].lower().endswith(".wav")
]
total_audio = len(audio_keys)

# silence threshold
SILENCE_THRESHOLD = 0.00001

# go through audio files and check quality
for key in tqdm(audio_keys, desc="Checking audio quality"):
    response = s3.get_object(Bucket=SOURCE_BUCKET, Key=key)
    # get label metadata,
    label = response.get("Metadata", {}).get("label", "").strip()
    if label:
        label_counts[label] += 1
    else:
        missing_label_count += 1
    with response["Body"] as body:
        audio_bytes = body.read()

    try:
        # read wav header and samples
        with wave.open(BytesIO(audio_bytes), "rb") as audio:
            sample_rate = audio.getframerate()
            channels = audio.getnchannels()
            frames = audio.getnframes()
            sample_width = audio.getsampwidth()

            raw_audio = audio.readframes(frames)

        # check for empty audio or invalid sample rate
        if frames == 0 or sample_rate <= 0:
            raise ValueError("Empty audio or invalid sample rate")

        # check that all samples from the header are available
        expected_size = frames * channels * sample_width
        if len(raw_audio) != expected_size:
            raise ValueError("Incomplete audio file")

        # convert bytes to sample values, 24-bit needs three bytes combined
        if sample_width == 3:
            values = np.frombuffer(raw_audio, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            samples = values[:, 0] | (values[:, 1] << 8) | (values[:, 2] << 16)
            samples = (samples ^ 0x800000) - 0x800000 # convert to signed 24-bit values
        else:
            dtype = "u1" if sample_width == 1 else f"<i{sample_width}"
            samples = np.frombuffer(raw_audio, dtype=dtype).astype(float)
            if sample_width == 1: # 8-bit silence is 128, shift it to zero
                samples -= 128

        # normalize samples and calculate volume using rms
        samples = samples / (2 ** (8 * sample_width - 1))
        rms = np.sqrt(np.mean(samples ** 2))
        audio_records.append({
            "key": key,
            "hash": hashlib.md5(audio_bytes).hexdigest(), # hash file bytes to find duplicates
            "duration": frames / sample_rate, # duration in seconds
            "rms": float(rms),
            "is_silent": rms < SILENCE_THRESHOLD,
        })

    except (wave.Error, EOFError, ValueError) as e:
        print(f"Error reading {key}: {e}")
        corrupt_keys.append(key)

# mark duplicate audio files using their hashes
print("Detecting duplicates")
seen_hashes = set()

for record in audio_records:
    record["is_duplicate"] = record["hash"] in seen_hashes
    seen_hashes.add(record["hash"])

# find duration outliers
print("Detecting duration outliers")

durations = [r["duration"] for r in audio_records if not r["is_duplicate"]]

if durations:
    # calculate iqr bounds using the same quartiles as the boxplot
    q1, q3 = np.percentile(durations, [25, 75])
    iqr = q3 - q1
    lower_bound = max(0, q1 - 1.5 * iqr)
    upper_bound = q3 + 1.5 * iqr
else:
    lower_bound, upper_bound = 0, 0

# flag audio outside the duration bounds
for record in audio_records:
    record["is_duration_outlier"] = not lower_bound <= record["duration"] <= upper_bound

# group results for the report
duplicate_records = [r for r in audio_records if r["is_duplicate"]]
trusted_records = [r for r in audio_records if not r["is_duplicate"]]
outlier_records = [r for r in audio_records if r["is_duration_outlier"]]
silent_records = [r for r in audio_records if r["is_silent"]]

# print quality summary
print(f"\nChecked {len(audio_records) + len(corrupt_keys)} audio files")
print(f"  Corrupt (unreadable): {len(corrupt_keys)}")
print(f"  Duplicates: {len(duplicate_records)}")
print(f"  Duration outliers: {len(outlier_records)}")
print(f"  Silent audio: {len(silent_records)}")
print(f"  With label: {total_audio - missing_label_count}")
print(f"  Without label: {missing_label_count}")
# print recordings per label, most common first
print("\nRecordings per label:")
for label, count in label_counts.most_common():
    print(f"  {label}: {count}")

TABLE_LIMIT = 20 # maximum files shown per category

def add_key_table(doc, header, rows):
    """Add a table listing the flagged audio files, capped at TABLE_LIMIT rows"""
    if not rows:
        return
    # keep subfolders in the displayed filename
    with doc.create(LongTable(
        NoEscape(r"p{0.52\textwidth}" + "|r" * (len(header) - 1))
    )) as table:
        table.add_hline()
        table.add_row(header)
        table.add_hline()
        table.end_table_header() # repeat header on each page
        for key, *values in rows[:TABLE_LIMIT]:
            # escape latex characters and wrap long filenames
            name = str(escape_latex(key.removeprefix(SOURCE_PREFIX)))
            name = NoEscape(name.replace(r"\_", r"\_\allowbreak ").replace("/", r"/\allowbreak "))
            table.add_row([name, *values])
        table.add_hline()
    if len(rows) > TABLE_LIMIT:
        doc.append(f"Only the first {TABLE_LIMIT} of {len(rows)} files are listed. ")

# keep chart files until pdf generation is finished
with tempfile.TemporaryDirectory() as assets_dir:
    duration_chart_path = os.path.join(assets_dir, "duration_boxplot.png")
    # duration boxplot with the same iqr bounds
    if durations:
        duration_df = pd.DataFrame({"duration": durations})
        alt.Chart(duration_df).mark_boxplot(extent=1.5, size=40, color="#2a78d6").encode(
            x=alt.X("duration:Q", title="Audio duration (seconds)"),
        ).properties(width=450, height=80).save(duration_chart_path, ppi=200)

    # create pdf report
    doc = Document(geometry_options={"margin": "2.5cm"}, page_numbers=False)
    doc.change_document_style("plain")
    with doc.create(Section("Audio quality report")):
        doc.append(
            f"This document shows results for {total_audio} WAV files in the animal "
            "identification project pipeline. Each file is checked for readability, "
            "duplicates, unusual duration, silence and label metadata. "
            f"A total of {len(trusted_records)} unique, readable recordings will be copied "
            "to the trusted zone. Silent recordings and duration outliers are kept "
            "for review; corrupt files and duplicate copies are excluded. "
            "The categories can overlap, so their counts should not be added together. "
        )

        with doc.create(Subsection("Corrupt or empty audio")):
            doc.append(
                "WAV files must decode successfully, contain at least one frame and "
                "provide all sample bytes declared in their header. The decoder supports "
                "8-, 16-, 24- and 32-bit integer PCM WAV files; unsupported encodings "
                "are also counted as unreadable. "
                f"A total of {len(corrupt_keys)} files failed these checks and are excluded. "
            )
            add_key_table(doc, ["Audio file"], [[k] for k in corrupt_keys])

        with doc.create(Subsection("Duplicate audio")):
            doc.append(
                "An MD5 hash is computed from each readable file's original bytes. "
                "The first file with each hash is kept; later copies are excluded. "
                "This detects byte-identical files, so recordings with different "
                "headers or encodings may still contain the same sound without matching. "
                f"A total of {len(duplicate_records)} duplicate copies were found. "
            )
            add_key_table(doc, ["Audio file"], [[r["key"]] for r in duplicate_records])

        with doc.create(Subsection("Duration outliers")):
            doc.append(
                "Duration is calculated as the frame count divided by the sample rate. "
                "Quartiles are calculated from unique, readable recordings, so duplicate "
                "copies do not skew the distribution. Using IQR = Q3 - Q1, a recording "
                f"is flagged below {lower_bound:.3f} seconds (Q1 - 1.5 IQR, bounded "
                f"at zero) or above {upper_bound:.3f} seconds (Q3 + 1.5 IQR). "
                f"A total of {len(outlier_records)} recordings were flagged. "
                "An unusual duration does not necessarily indicate bad audio, so these "
                "recordings are retained unless they are duplicates. "
            )
            if durations:
                with doc.create(Figure(position="h!")) as figure:
                    figure.add_image(duration_chart_path, width=NoEscape(r"0.8\textwidth"))
                    figure.add_caption(
                        "Duration distribution of unique, readable recordings. "
                        "Points beyond the whiskers are duration outliers."
                    )
            else:
                doc.append("No readable recordings were available to calculate quartiles. ")
            add_key_table(doc, ["Audio file", "Duration (s)"], [
                [r["key"], f"{r['duration']:.3f}"] for r in outlier_records
            ])

        with doc.create(Subsection("Silent audio")):
            doc.append(
                "Integer samples are normalized to approximately -1 to 1. "
                "Root mean square (RMS) amplitude is the square root of the mean "
                "squared sample values, measured across all samples and channels. "
                "Squaring prevents positive and negative samples from cancelling out. "
                f"Recordings with RMS below {SILENCE_THRESHOLD:.5f} are flagged as "
                f"silent or nearly silent. A total of {len(silent_records)} recordings "
                "were flagged. This threshold is a heuristic; quiet animal sounds can "
                "still be useful, so these recordings are retained unless duplicated. "
            )
            add_key_table(doc, ["Audio file", "RMS amplitude"], [
                [r["key"], f"{r['rms']:.8f}"] for r in silent_records
            ])

        with doc.create(Subsection("Label metadata")):
            doc.append(
                f"Of {total_audio} source WAV files, {total_audio - missing_label_count} "
                f"have a label and {missing_label_count} have no label. "
                "Absent, empty and whitespace-only labels count as missing. "
                "These counts include duplicates and unreadable audio, before filtering. "
                "A missing label does not exclude a recording from the trusted zone. "
                "The table lists the number of source recordings for every available label. "
                "Labels are ordered by frequency, reading left to right across each row. "
            )
            if label_counts:
                labels = label_counts.most_common()
                # show three labels per row to save space
                doc.append(NoEscape(r"\begingroup\small"))
                with doc.create(LongTable(NoEscape(r"p{0.20\textwidth}r|p{0.20\textwidth}r|p{0.20\textwidth}r"))) as table:
                    table.add_hline()
                    table.add_row([NoEscape(r"\textbf{Label}"), NoEscape(r"\textbf{Count}")] * 3)
                    table.add_hline()
                    table.end_table_header() # repeat header on each page
                    for start in range(0, len(labels), 3):
                        row = []
                        for label, count in labels[start:start + 3]:
                            row.extend([label, count])
                        table.add_row(row + [""] * (6 - len(row))) # fill empty columns in the last row
                    table.add_hline()
                doc.append(NoEscape(r"\endgroup"))

    report_dir = os.path.join(os.path.dirname(__file__), "quality_reports")
    os.makedirs(report_dir, exist_ok=True) # create report folder if needed
    report_path = os.path.join(report_dir, f"audio_quality_report_{datetime.date.today()}")
    # compile twice to align table columns across pages
    doc.generate_pdf(filepath=report_path, compiler="pdflatex", clean=False, clean_tex=False)
    doc.generate_pdf(filepath=report_path, compiler="pdflatex", clean_tex=True)

# copy readable audio without duplicates to the trusted zone
for record in tqdm(trusted_records, desc=f"Moving audio to {TARGET_BUCKET}"):
    # keep subfolders to avoid overwriting files with the same name
    relative_key = record["key"][len(SOURCE_PREFIX):]
    target_key = f"{TARGET_PREFIX}{relative_key}"
    s3.copy_object(
        Bucket=TARGET_BUCKET,
        CopySource={"Bucket": SOURCE_BUCKET, "Key": record["key"]},
        Key=target_key,
    )

