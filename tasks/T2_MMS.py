from io import BytesIO

import chromadb #type:ignore
import numpy as np
from PIL import Image
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction#type:ignore
import torch#type:ignore

from config import CHROMA_PATH
from zones.client import S3Client


class MultiModalSearchService:
    def __init__(self):
        embedding_function = OpenCLIPEmbeddingFunction()

        # chromadb client
        client = chromadb.PersistentClient(path=CHROMA_PATH)

        self.text_collection = client.get_collection(
            name="text_embeddings_collection",
            embedding_function=embedding_function,
        )

        self.image_collection = client.get_collection(
            name="image_embeddings_collection",
            embedding_function=embedding_function,
        )

        # s3 client to retrieve images from minio
        self.s3 = S3Client().s3
    
    def text_query(self, user_text, topk):
    
            # search for similar text embeddings
            text_results = self.text_collection.query(
                query_texts=[user_text],
                n_results=topk,
                include=["documents", "metadatas", "distances"],
            )
    
            # search for similar image embeddings
            image_results = self.image_collection.query(
                query_texts=[user_text],
                n_results=topk,
                include=["metadatas", "distances"],
            )
    
            retrieved_images, retrieved_texts = self.log_and_retrieve_results(text_results, image_results)
           
            return retrieved_images, retrieved_texts

    def image_query(self, user_image, topk):

        # convert the input photo into image format expected by OpenCLIP
        user_image.seek(0)
        uploaded_image = Image.open(user_image).convert("RGB")
        image = np.array(uploaded_image)

        # search for similar text embeddings
        text_results = self.text_collection.query(
            query_images=[image],
            n_results=topk,
            include=["documents", "metadatas", "distances"],
        )

        # search for similar image embeddings
        image_results = self.image_collection.query(
            query_images=[image],
            n_results=topk,
            include=["metadatas", "distances"],
        )

        retrieved_images, retrieved_texts = self.log_and_retrieve_results(text_results, image_results)
       
        return retrieved_images, retrieved_texts

    def log_and_retrieve_results(self, text_results, image_results):
        print("\nRetrieved text:")
        for source_id, document, distance in zip(
                text_results["ids"][0],
                text_results["documents"][0],
                text_results["distances"][0],
            ):
            print(f"\n{source_id} | distance: {distance:.3f}")
            print(document)
    
        print("\nRetrieved images:")
        for source_id, metadata, distance in zip(
                image_results["ids"][0],
                image_results["metadatas"][0],
                image_results["distances"][0],
            ):
            print(f"\n{source_id} | distance: {distance:.3f}")
            print(metadata)
    
            # retrieve the actual images from minio
        retrieved_images = []

        for metadata in image_results["metadatas"][0]:
            response = self.s3.get_object(
                   Bucket=metadata["source_bucket"],
                   Key=metadata["source_key"])
    
            body = response["Body"]
    
            try:image_bytes = body.read()
            finally:body.close()
    
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            retrieved_images.append(image)
    
            #Retrieve text from minio
        retrieved_texts = []
    
        for docu in text_results["documents"][0]:
        
            retrieved_texts.append(docu)
        return retrieved_images,retrieved_texts
    