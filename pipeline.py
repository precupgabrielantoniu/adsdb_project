#Run every zone of the pipeline in order (the existing ones)
import subprocess
import sys

STAGES = [
    "zones.landing_zone",
    "zones.formatted_zone.image",
    "zones.formatted_zone.text",
    "zones.formatted_zone.audio",
    "zones.trusted_zone.image",
    "zones.trusted_zone.text",
    "zones.exploitation_zone.text",
]

for stage in STAGES:
    print(f"\n=== {stage} ===")
    subprocess.run([sys.executable, "-m", stage], check=True) #check=True stops the pipeline if a stage fails
