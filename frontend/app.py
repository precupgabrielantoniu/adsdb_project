import streamlit as st#type:ignore

pages = [
    st.Page(
        "pages/same_modality_search.py",
        title="Same-Modality Similarity Search",
        default=True,
    ),
    st.Page(
        "pages/multi_modality_search.py",
        title="Multi-Modality Similarity Search",
    ),
    st.Page(
        "pages/rag.py",
        title="Retrieval-Augmented Generation (RAG)",
    ),
]

page = st.navigation(pages)

st.title(":green[Animal Wiki]")
page.run()
