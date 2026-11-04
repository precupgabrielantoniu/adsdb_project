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

        # Load audio embeddings from S3
        self.audio_embeddings = []
        self.audio_embedding_index = {}
        self._load_audio_embeddings()

        # Load ChromaDB collections
        embedding_function = OpenCLIPEmbeddingFunction()
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.image_collection = chroma_client.get_collection(
            name="image_embeddings_collection",
            embedding_function=embedding_function
        )
        self.text_collection = chroma_client.get_collection(
            name="text_embeddings_collection",
            embedding_function=embedding_function
        )

    def _load_audio_embeddings(self):
        """Load audio embeddings index from S3."""
        try:
            response = self.s3.get_object(
                Bucket="exploitation-zone",
                Key="audio/_embedding_index.json"
            )
            index_data = json.loads(response['Body'].read().decode('utf-8'))
            self.audio_embeddings = index_data.get('embeddings', [])
            self.audio_embedding_index = index_data.get('index', {})
        except Exception:
            self.audio_embeddings = []
            self.audio_embedding_index = {}

    def find_similar_audio(self, user_audio_bytes, top_k=5, similarity_threshold=0.3):
        """Find similar audio files from uploaded audio bytes."""
        if not self.audio_embeddings:
            return []

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

        # Search for similar audio
        similarities = []
        for record in self.audio_embeddings:
            sim = self._cosine_similarity(query_embedding, record["embedding"])
            if sim >= similarity_threshold:
                similarities.append((record["key"], sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

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
                    exploitation_key = f"images/{filename}"

                    # Verify image exists
                    try:
                        self.s3.head_object(Bucket="exploitation-zone", Key=exploitation_key)
                        similarity_score = 1 - distance
                        similar_images.append((exploitation_key, similarity_score))
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

    def _cosine_similarity(self, embedding1, embedding2):
        """Calculate cosine similarity between two embeddings."""
        e1 = np.array(embedding1, dtype=np.float32)
        e2 = np.array(embedding2, dtype=np.float32)

        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(e1, e2) / (norm1 * norm2))
