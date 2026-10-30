import chromadb#type:ignore
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction#type:ignore

from config import CHROMA_PATH

#Find the three collections from the persistent chromadb client
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

text_embeddings = chroma_client.get_collection("text_embeddings_collection")
#audio_embeddings = chroma_client.get_collection("audio_embeddings_collection")
#image_embeddings = chroma_client.get_collection("image_embeddings_collection")

#Get an input (for now a file path to an image, text or audio file)
input_path = input("Write the path to the desired element...\n").strip()

#Query each of the collections and return three top ones per collection

