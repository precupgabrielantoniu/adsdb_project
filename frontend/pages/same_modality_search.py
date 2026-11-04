import streamlit as st
import json
import os
from io import BytesIO
from PIL import Image

# Configure page
st.set_page_config(page_title="Same-Modality Search", layout="wide")

# Import search functions
import sys
sys.path.insert(0, '/home/precupgabriel/3A/adsdb_project')

from zones.client import S3Client
from zones.exploitation_zone.audio import find_similar_audio
from zones.exploitation_zone.image import find_similar_images
from zones.exploitation_zone.text import find_similar_texts

# Initialize S3 client
@st.cache_resource
def get_s3_client():
    client = S3Client()
    return client.s3

@st.cache_data
def load_test_audio_files():
    """Load test audio file list from S3"""
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket="exploitation-zone", Key="audio/_embedding_index.json")
        data = json.loads(obj['Body'].read().decode('utf-8'))
        return data.get('test_files', [])
    except:
        return []

@st.cache_data
def load_test_text_metadata():
    """Load test text metadata from S3"""
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket="exploitation-zone", Key="text/_test_metadata.json")
        data = json.loads(obj['Body'].read().decode('utf-8'))
        return data
    except:
        return {}

@st.cache_data
def load_text_dataset():
    """Load all text entries from ChromaDB collection"""
    try:
        import chromadb
        from config import CHROMA_PATH
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = chroma_client.get_collection("text_embeddings_collection")
        all_docs = collection.get()
        return all_docs
    except:
        return None

# UI
st.title("🔍 Same-Modality Similarity Search")
st.markdown("Find similar items from the **test set** against the **training set**")

# Modality selection
modality = st.radio("Select Modality", ["🎵 Audio", "🖼️ Image", "📄 Text"], horizontal=True)

st.divider()

if modality == "🎵 Audio":
    st.subheader("🎵 Audio Similarity Search (Test vs Training)")

    test_audio_files = load_test_audio_files()

    if test_audio_files:
        audio_basenames = [os.path.basename(f) for f in test_audio_files]

        selected_audio = st.selectbox("Select a test audio file", audio_basenames)

        if selected_audio:
            # Show selected test audio
            try:
                s3 = get_s3_client()
                audio_bytes = s3.get_object(Bucket="exploitation-zone", Key=f"audio/test/{selected_audio}")["Body"].read()
                st.audio(audio_bytes)
                st.caption(f"Test file: {selected_audio}")
            except Exception as e:
                st.error(f"Could not load audio: {e}")

            if st.button("🔍 Find Similar Audios in Training Set", key="audio_search"):
                # Find the full key from test files
                query_key = None
                for test_file in test_audio_files:
                    if os.path.basename(test_file) == selected_audio:
                        query_key = test_file
                        break

                if query_key:
                    similar = find_similar_audio(query_key, top_k=5, similarity_threshold=0.3)

                    if similar:
                        st.success(f"Found {len(similar)} similar audios in training set")

                        for idx, (key, score) in enumerate(similar, 1):
                            col1, col2, col3 = st.columns([2, 1, 2])
                            with col1:
                                st.write(f"**#{idx}** {os.path.basename(key)}")
                            with col2:
                                st.metric("Similarity", f"{score:.2%}")
                            with col3:
                                try:
                                    s3 = get_s3_client()
                                    audio_bytes = s3.get_object(Bucket="exploitation-zone", Key=f"audio/{os.path.basename(key)}")["Body"].read()
                                    st.audio(audio_bytes)
                                except Exception as e:
                                    st.error(f"Audio unavailable: {e}")
                    else:
                        st.warning("No similar audios found in training set")
    else:
        st.warning("Test audio files not found. Run the pipeline first.")

elif modality == "🖼️ Image":
    st.subheader("🖼️ Image Similarity Search (Test vs Training)")

    try:
        s3 = get_s3_client()

        # List available test images
        paginator = s3.get_paginator('list_objects_v2')
        test_images = []
        try:
            for page in paginator.paginate(Bucket="exploitation-zone", Prefix="images/test/"):
                if 'Contents' in page:
                    for obj in page.get('Contents', []):
                        key = obj['Key']
                        if not key.endswith('/'):
                            test_images.append(key)
        except Exception as e:
            st.error(f"Error listing test images: {e}")

        if test_images:
            selected_image = st.selectbox("Select a test image", test_images)

            if selected_image:
                try:
                    img_bytes = s3.get_object(Bucket="exploitation-zone", Key=selected_image)["Body"].read()
                    img = Image.open(BytesIO(img_bytes))
                    st.image(img, caption=os.path.basename(selected_image), width="stretch")
                except Exception as e:
                    st.error(f"Could not load image: {e}")

                if st.button("🔍 Find Similar Images in Training Set", key="image_search"):
                    similar = find_similar_images(selected_image, top_k=5)

                    if similar:
                        st.success(f"Found {len(similar)} similar images in training set")
                        cols = st.columns(3)
                        for idx, (key, score) in enumerate(similar):
                            with cols[idx % 3]:
                                try:
                                    img_bytes = s3.get_object(Bucket="exploitation-zone", Key=key)["Body"].read()
                                    img = Image.open(BytesIO(img_bytes))
                                    st.image(img, caption=f"Match: {score:.0%}", width="stretch")
                                except Exception as e:
                                    st.error(f"Could not load image: {e}")
                    else:
                        st.warning("No similar images found in training set")
        else:
            st.warning("No test images found in exploitation-zone/images/test/")
            st.info("Make sure the pipeline has been run to split and process images.")
    except Exception as e:
        st.error(f"Error: {e}")

elif modality == "📄 Text":
    st.subheader("📄 Text Similarity Search (Test vs Training)")

    test_metadata = load_test_text_metadata()

    if test_metadata:
        # Create list of test text entries
        test_entries = []
        for filename, sentences in test_metadata.items():
            for i, sentence in enumerate(sentences):
                test_entries.append({
                    'id': f"{filename}_{i}",
                    'filename': filename,
                    'text': sentence,
                    'index': i
                })

        if test_entries:
            # Show test entries in selectbox
            test_display = [f"{entry['filename']} #{entry['index']}: {entry['text'][:60]}..." if len(entry['text']) > 60 else f"{entry['filename']} #{entry['index']}: {entry['text']}"
                           for entry in test_entries]

            selected_test_display = st.selectbox("Select a test text entry", test_display)

            if selected_test_display:
                # Get the selected entry
                selected_idx = test_display.index(selected_test_display)
                selected_entry = test_entries[selected_idx]

                st.write("**Selected test entry:**")
                st.write(selected_entry['text'])

                if st.button("🔍 Find Similar Texts in Training Set", key="text_search_test"):
                    similar = find_similar_texts(selected_entry['text'], top_k=5)

                    if similar:
                        st.success(f"Found {len(similar)} similar texts in training set")
                        for idx, result in enumerate(similar, 1):
                            # Handle new format with document text
                            if len(result) == 3:
                                doc_id, document, score = result
                                st.write(f"**#{idx}** Similarity: **{score:.2%}**")
                                st.write(document)
                            else:
                                doc_id, score = result
                                st.write(f"**#{idx}** Similarity: **{score:.2%}** (ID: `{doc_id}`)")
                            st.divider()
                    else:
                        st.warning("No similar texts found in training set")
        else:
            st.warning("No test text entries found")
    else:
        st.warning("Test text metadata not found. Run the pipeline first.")

st.divider()
st.caption("💡 This interface tests model generalization using unseen test data (20%) against training embeddings (80%)")
