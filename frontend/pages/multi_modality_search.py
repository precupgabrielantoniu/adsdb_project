from io import BytesIO
import os

from PIL import Image
import numpy as np

import chromadb#type:ignore
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction#type:ignore

import streamlit as st #type:ignore

from config import CHROMA_PATH
from zones.client import S3Client
from zones.formatted_zone.image import to_jpg

#Find the three collections from the persistent chromadb client
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
client = S3Client()
s3 = client.s3

text_embeddings = chroma_client.get_collection("text_embeddings_collection")
audio_embeddings = chroma_client.get_collection("audio_embeddings_collection")
image_embeddings = chroma_client.get_collection("image_embeddings_collection")

#Setting up a streamlit page to obtain the input
st.title("Task 2: Multimodal search")
st.divider()
st.text("Choose you data type here")
selection = st.segmented_control("Directions", ["Image", "Text"])
st.text("Choose the amount search of results to show per type of data")
topK = st.slider("Show top K results", 0, 50)

if selection == "Image": #If an image is choosen as input
    #Read it
    uploaded_image = st.file_uploader("Upload your search image here", accept_multiple_files=True, type=["jpg", "png"])
    image = Image.open(BytesIO(uploaded_image)).convert("RGB")
    image_array = np.array(image)
    jpg_image = to_jpg(uploaded_image) #convert to jpg
    #Get results both from text and image collections
    results_text = text_embeddings.query(query_images=[jpg_image], n_results=topK)
    results_image = image_embeddings.query(query_images=[jpg_image], n_results=topK)
    
elif selection == "Text":
    search_text = st.text_input("Input your search text here", "Lorem ipsum")
    results_text = text_embeddings.query(query_texts=[search_text], n_results=topK)
    results_image = image_embeddings.query(query_texts=[search_text], n_results=topK)

#Show the results regardles of input type with the images going first and the text afterwards
st.header(f"Closest {topK} images to yours")
for image in results_image: #per result
    #Retrieve the image from its bucket
    real_image = s3.Object(image["metadatas"]["source_bucket"], image["metadatas"]["source_key"]).get()['Body'].read()
    #Display the image
    st.image(real_image)
st.header(f"Closest {topK} texts to yours")
for text in results_text:
    #Retrieve the text from its bucket
    real_text = s3.Object(text["metadatas"]["source_bucket"], text["metadatas"]["source_key"]).get()['Body'].read()
    #Display the text
    st.divider()
    st.text(real_text)