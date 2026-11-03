import streamlit as st
with st.spinner("Loading model… Please wait"):
    from tasks.T3_RAG import invoke_rag

st.caption("Task 3: Retrieval-augmented generation (RAG)")

st.header("Ask :green[Animal Wiki]")
st.write("Provie an image of an animal and ask a question about it!")

uploaded_file = st.file_uploader("Choose an image", type="image")

if uploaded_file is not None:
    st.image(uploaded_file)


user_question = st.text_input("Enter your question about the animal")

if st.button("Generate answer",
          type="primary",
          disabled=not user_question.strip() or uploaded_file is None,
):

    with st.spinner("Generating answer..."):
        answer, retrieved_images = invoke_rag(
            uploaded_file, user_question
        )

    st.write(answer)

    for i, image in enumerate(retrieved_images, start=1):
        st.image(image, caption=f"Image {i}")
