from io import BytesIO
import json
import os

import chromadb #type:ignore
import librosa
import numpy as np
from PIL import Image
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction #type:ignore

from config import CHROMA_PATH
from zones.client import S3Client


class SameModalitySearchService:
    """Service for same-modality similarity search across audio, images, and text."""

    def __init__(self):
        self.s3 = S3Client().s3

        # Load ChromaDB collections
        embedding_function = OpenCLIPEmbeddingFunction()
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.audio_collection = chroma_client.get_collection(
            name="audio_embeddings_collection"
        )
        self.image_collection = chroma_client.get_collection(
            name="image_embeddings_collection",
            embedding_function=embedding_function
        )
        self.text_collection = chroma_client.get_collection(
            name="text_embeddings_collection",
            embedding_function=embedding_function
        )

    def find_similar_audio(self, user_audio_bytes, top_k=5):
        """Find similar audio files from uploaded audio bytes."""
        try:
            # Compute MFCC embedding from user audio
            audio_data, sr = librosa.load(
                BytesIO(user_audio_bytes),
                sr=22050,
                mono=True
            )
            mfcc = librosa.feature.mfcc(y=audio_data, sr=sr, n_mfcc=13)
            embedding = np.concatenate([
                np.mean(mfcc, axis=1),
                np.std(mfcc, axis=1),
                np.min(mfcc, axis=1),
                np.max(mfcc, axis=1),
            ])
            embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
            query_embedding = embedding.tolist()
        except Exception as e:
            print(f"Error computing audio embedding: {e}")
            return []

        # Query ChromaDB for similar audio
        try:
            results = self.audio_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "distances"]
            )

            # Format results
            similar_audio = []
            if results and results['ids'] and len(results['ids']) > 0:
                for distance, metadata in zip(
                    results['distances'][0],
                    results['metadatas'][0]
                ):
                    similarity_score = 1 - distance
                    source_key = metadata.get('source_key', '')
                    similar_audio.append((source_key, similarity_score))

            return similar_audio
        except Exception as e:
            print(f"Error querying audio embeddings: {e}")
            return []

    def find_similar_images(self, user_image_bytes, top_k=5):
        """Find similar images from uploaded image bytes."""
        try:
            # Load and prepare image
            img = Image.open(BytesIO(user_image_bytes)).convert("RGB")
            img_array = np.array(img)

            # Query ChromaDB
            results = self.image_collection.query(
                query_images=[img_array],
                n_results=top_k,
                include=["metadatas", "distances"]
            )

            # Format results
            similar_images = []
            if results and results['ids'] and len(results['ids']) > 0:
                for doc_id, distance in zip(results['ids'][0], results['distances'][0]):
                    # doc_id is like "trusted-zone/images/filename.jpg", convert to exploitation-zone path
                    filename = doc_id.split('/')[-1]
                    source_key = f"images/{filename}"

                    # Verify image exists
                    try:
                        self.s3.head_object(Bucket="trusted-zone", Key=source_key)
                        similarity_score = 1 - distance
                        similar_images.append((source_key, similarity_score))
                    except:
                        pass

            return similar_images
        except Exception as e:
            print(f"Error querying similar images: {e}")
            return []

    def find_similar_texts(self, user_text, top_k=5):
        """Find similar texts from user input."""
        try:
            results = self.text_collection.query(
                query_texts=[user_text],
                n_results=top_k,
                include=["documents", "distances"]
            )

            # Format results
            similar_texts = []
            if results and results['ids'] and len(results['ids']) > 0:
                for doc_id, document, distance in zip(
                    results['ids'][0],
                    results['documents'][0],
                    results['distances'][0]
                ):
                    similarity_score = 1 - distance
                    similar_texts.append((doc_id, document, similarity_score))

            return similar_texts
        except Exception as e:
            print(f"Error querying similar texts: {e}")
            return []

