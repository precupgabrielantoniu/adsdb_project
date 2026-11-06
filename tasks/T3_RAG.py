from io import BytesIO

import chromadb
import numpy as np
from PIL import Image
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction
import torch
from transformers import AutoProcessor, LlavaOnevisionForConditionalGeneration

from config import CHROMA_PATH
from zones.client import S3Client

class RagService:
    def __init__(self):
        # https://huggingface.co/llava-hf/llava-onevision-qwen2-0.5b-ov-hf
        MODEL_ID = "llava-hf/llava-onevision-qwen2-0.5b-ov-hf"

        # converts images and text into the numerical inputs the model expects
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)

        self.model = LlavaOnevisionForConditionalGeneration.from_pretrained(
            MODEL_ID,
            dtype=torch.float32,
        ).eval()


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

    def invoke(self, user_image, user_question):

        # convert the input photo into image format expected by OpenCLIP
        user_image.seek(0)
        uploaded_image = Image.open(user_image).convert("RGB")
        image = np.array(uploaded_image)

        # search for similar text embeddings
        text_results = self.text_collection.query(
            query_images=[image],
            n_results=2,
            include=["documents", "distances"],
        )

        # search for similar image embeddings
        image_results = self.image_collection.query(
            query_images=[image],
            n_results=2,
            include=["metadatas", "distances"],
        )
        # for debugging purposes
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
               Key=metadata["source_key"],
            )

            body = response["Body"]

            try:
                image_bytes = body.read()
            finally:
                body.close()

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            retrieved_images.append(image)

        # create prompt
        context = "\n\n".join(
            f"[T{i}] {document}"
            for i, document in enumerate(text_results["documents"][0], start=1)
        )

        prompt = f"""
        You are an animal expert.
        
        Answer the user's question about the first image.
        The other images are references from our database and may show different animals.
        The retrieved text is from our database and may describe other animals.
        Use the retrieved images and text to answer the user's question.
    
        Question:
        {user_question}
    
        Retrieved text:
        {context}
        """

        # images to give to the LLM
        images = [uploaded_image, *retrieved_images]

        conversation = [{
            "role": "user",
            "content": [
                *[{"type": "image"} for _ in images],
                {"type": "text", "text": prompt},
            ],
        }]

        formatted_prompt = self.processor.apply_chat_template(
            conversation,
            add_generation_prompt=True,
        )

        inputs = self.processor(
            text=formatted_prompt,
            images=[images],
            return_tensors="pt",
        )

        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=500,
                do_sample=False,
            )

        answer_tokens = output[0, inputs["input_ids"].shape[1]:]
        answer = self.processor.decode(answer_tokens, skip_special_tokens=True)

        return answer, retrieved_images