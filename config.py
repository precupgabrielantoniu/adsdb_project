from dotenv import load_dotenv #type:ignore
import os

load_dotenv()

MINIO_ENDPOINT_URL = os.environ['MINIO_ENDPOINT_URL']
MINIO_ROOT_USER = os.environ['MINIO_ROOT_USER']
MINIO_ROOT_PASSWORD = os.environ['MINIO_ROOT_PASSWORD']

CHROMA_PATH = os.environ['CHROMA_PATH']

HF_TOKEN = os.environ['HF_TOKEN']