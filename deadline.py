import streamlit as st

st.set_page_config(page_title="Deadline Missed")

st.markdown(
    """
    <style>
    .deadline-container {
        max-width: 600px;
        margin: 0 auto;
        text-align: center;
        padding: 2rem;
        border: 1px solid #f5c2c7;
        background-color: #f8d7da;
        color: #842029;
        border-radius: 0.5rem;
    }
    </style>
    <div class="deadline-container">
        <h1>Deadline Missed</h1>
        <p>You have missed the deadline.</p>
        <p>Please contact the Developer.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
