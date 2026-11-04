import streamlit as st
import os
from io import BytesIO
from PIL import Image

# Configure page
st.set_page_config(page_title="Same-Modality Search", layout="wide")

# Import search service
import sys
sys.path.insert(0, '/home/precupgabriel/3A/adsdb_project')

from tasks.T1_SMS import SameModalitySearchService
from zones.client import S3Client

# Initialize service
@st.cache_resource(show_spinner="Loading models… Please wait")
def get_search_service():
    return SameModalitySearchService()

service = get_search_service()

# UI
st.title("🔍 Same-Modality Similarity Search")
st.markdown("Find similar audio, images, or text items")

# Modality selection
modality = st.radio("Select Modality", ["🎵 Audio", "🖼️ Image", "📄 Text"], horizontal=True)

st.divider()

if modality == "🎵 Audio":
    st.subheader("🎵 Audio Similarity Search")

    uploaded_audio = st.file_uploader("Upload an audio file", type=["wav", "mp3", "flac", "ogg"])

    if uploaded_audio is not None:
        st.audio(uploaded_audio)
        st.caption(f"Uploaded: {uploaded_audio.name}")

        if st.button("🔍 Find Similar Audios", key="audio_search"):
            uploaded_audio.seek(0)
            audio_bytes = uploaded_audio.read()
            similar = service.find_similar_audio(audio_bytes, top_k=5)

            if similar:
                st.success(f"Found {len(similar)} similar audios")

                s3 = S3Client().s3
                for idx, (key, score) in enumerate(similar, 1):
                    col1, col2, col3 = st.columns([2, 1, 2])
                    with col1:
                        st.write(f"**#{idx}** {os.path.basename(key)}")
                    with col2:
                        st.metric("Similarity", f"{score:.2%}")
                    with col3:
                        try:
                            audio_bytes = s3.get_object(Bucket="exploitation-zone", Key=key)["Body"].read()
                            st.audio(audio_bytes)
                        except Exception as e:
                            st.error(f"Could not load audio: {e}")
            else:
                st.warning("No similar audios found")

elif modality == "🖼️ Image":
    st.subheader("🖼️ Image Similarity Search")

    uploaded_image = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])

    if uploaded_image is not None:
        img = Image.open(BytesIO(uploaded_image.read()))
        st.image(img, caption=uploaded_image.name, use_column_width="auto")

        if st.button("🔍 Find Similar Images", key="image_search"):
            uploaded_image.seek(0)
            similar = service.find_similar_images(uploaded_image.read(), top_k=5)

            if similar:
                st.success(f"Found {len(similar)} similar images")
                cols = st.columns(3)

                s3 = S3Client().s3
                for idx, (key, score) in enumerate(similar):
                    with cols[idx % 3]:
                        try:
                            img_bytes = s3.get_object(Bucket="exploitation-zone", Key=key)["Body"].read()
                            img = Image.open(BytesIO(img_bytes))
                            st.image(img, caption=f"Match: {score:.0%}", use_column_width="stretch")
                        except Exception as e:
                            st.error(f"Could not load image: {e}")
            else:
                st.warning("No similar images found")

elif modality == "📄 Text":
    st.subheader("📄 Text Similarity Search")

    query_text = st.text_area("Enter text to find similar entries", height=100)

    if st.button("🔍 Find Similar Texts", key="text_search"):
        if query_text:
            similar = service.find_similar_texts(query_text, top_k=5)

            if similar:
                st.success(f"Found {len(similar)} similar text entries")
                for idx, (doc_id, document, score) in enumerate(similar, 1):
                    st.write(f"**#{idx}** Similarity: **{score:.2%}**")
                    st.write(document)
                    st.divider()
            else:
                st.warning("No similar texts found")
        else:
            st.warning("Please enter text to search")

st.divider()
st.caption("💡 Upload your own files to find similar items in the knowledge base")
