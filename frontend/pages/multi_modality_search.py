from io import BytesIO
import os

from PIL import Image
import numpy as np

import chromadb#type:ignore
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction#type:ignore

import streamlit as st #type:ignore

from config import CHROMA_PATH
from tasks.T2_MMS import MultiModalSearchService

#Find the two collections from the persistent chromadb client
@st.cache_resource(show_spinner="Loading model… Please wait")
def get_multimodalsearch_service():
    return MultiModalSearchService()

service = get_multimodalsearch_service()

#Setting up a streamlit page to obtain the input
st.title("Task 2: Multimodal search")
st.divider()
st.text("Choose you data type here")
selection = st.segmented_control("Directions", ["Image", "Text"])
st.text("Choose the amount search of results to show per type of data")
topK = st.slider("Show top K results", 1, 50)

if selection == "Image": #If an image is choosen as input
    #Read it
    results_image, results_text = None, None

if selection == "Image": #If an image is choosen as input
    #Read it
    uploaded_image = st.file_uploader("Upload your search image here", type=["jpg", "png"])
    if uploaded_image is not None:
        results_image, results_text = service.image_query(uploaded_image, topK)

elif selection == "Text":
    search_text = st.text_input("Input your search text here", "Lorem ipsum")
    if search_text and search_text != "Lorem ipsum":
        results_image, results_text = service.text_query(search_text, topK)

#Show the results regardles of input type with the images going first and the text afterwards
if 'results_image' in locals():
    st.header(f"Closest {topK} images to yours")
    for image in results_image: #per result
        st.image(image)

    st.header(f"Closest {topK} texts to yours")
    for text in results_text:
        st.divider()
        st.text(text.decode("utf-8", errors="replace") if isinstance(text, bytes) else text)