import os

from PIL import Image
import numpy as np

import chromadb#type:ignore
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction#type:ignore

import streamlit as st #type:ignore

from config import CHROMA_PATH

#Find the three collections from the persistent chromadb client
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

text_embeddings = chroma_client.get_collection("text_embeddings_collection")
audio_embeddings = chroma_client.get_collection("audio_embeddings_collection")
image_embeddings = chroma_client.get_collection("image_embeddings_collection")

#Get an input (for now a file path to an image, text or audio file)
input_path = input("Write the path to the desired element...\n").strip()

#Read the input and query each of the collections returning top three ones per collection depending on type of input
extension = os.path.splitext(input_path)[1].lower()

if extension in (".jpg", ".jpeg", ".png"):
    image = np.array(Image.open(input_path).convert("RGB"))
    results_text = text_embeddings.query(query_images=[image], n_results=3)
    results_image = image_embeddings.query(query_images=[image], n_results=3)
    results_audio = audio_embeddings.query(query_images=[image], n_results=3)#works the same as a text embeddign collection
else:
    with open(input_path, "r", encoding="utf-8") as f: content = f.read()
    results_text = text_embeddings.query(query_texts=[content], n_results=3)
    results_image = image_embeddings.query(query_texts=[content], n_results=3)
    results_audio = audio_embeddings.query(query_texts=[content], n_results=3)

#Return then In a file? using a small streamlit app?
st.image{}

