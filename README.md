# RAG-LINE Bridge: Gemini-Powered LINE Bot

A proof-of-concept (POC) project demonstrating the integration of a LINE Messaging Bot with a Retrieval-Augmented Generation (RAG) backend powered by the Gemini API. This bridge allows users to interact with a knowledge base through a conversational LINE interface.

## Key Features

*   **LINE Messaging API Integration:** Receives and responds to user messages via LINE's webhook.
*   **Retrieval-Augmented Generation (RAG):** Utilizes a vector store for efficient document indexing and retrieval to provide context-aware answers.
*   **Gemini API:** Leverages Google's powerful Gemini models for natural language understanding and generation.
*   **Django Backend:** A robust backend framework to handle webhook events and business logic.
*   **Dockerized Environment:** Comes with a `docker-compose.yml` for easy setup and deployment.

## Architecture (Conceptual)

The following diagram illustrates the flow of a user's message from the LINE app to the RAG engine and back:

```
[LINE User] -> [LINE Platform] -> [Django Webhook] -> [RAG Engine] -> [Gemini API] -> [Django] -> [LINE Platform] -> [LINE User]
```

1.  A user sends a message to the LINE Bot.
2.  The LINE Platform forwards the message to the Django application's webhook endpoint.
3.  The Django application extracts the user's query and sends it to the RAG engine.
4.  The RAG engine retrieves relevant documents from the vector store and combines them with the user's query to form a prompt.
5.  The prompt is sent to the Gemini API.
6.  The Gemini API generates a response.
7.  The Django application sends the generated response back to the user via the LINE Messaging API.

## Prerequisites

Before you begin, ensure you have the following installed:

*   [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/install/)
*   [Python 3.10+](https://www.python.org/downloads/) (for local development and setup)
*   Access to the Gemini API and a valid API key.
*   A LINE Developer account and a channel with a channel access token and channel secret.

## Getting Started

Follow these steps to get the project up and running:

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd RAG-LINE-bridge
```

### 2. Set Up Environment Variables

Create a `.env` file by copying the example file:

```bash
cp .env.example .env
```

Now, edit the `.env` file and fill in the required values:

```
# Django
SECRET_KEY=<your-django-secret-key>
DEBUG=True
ALLOWED_HOSTS=*

# LINE Bot
LINE_CHANNEL_ACCESS_TOKEN=<your-line-channel-access-token>
LINE_CHANNEL_SECRET=<your-line-channel-secret>

# Langflow / RAG
LANGFLOW_API_URL=http://localhost:7860/api/v1/run/
LANGFLOW_API_KEY=<your-langflow-api-key>
FLOW_ID=<your-langflow-flow-id>
```

### 3. Set Up the RAG Index

This POC uses a local vector store for the RAG index. To set up the index, you will need to:

1.  **Place your documents** in a designated folder (e.g., `documents/`).
2.  **Run the indexing script** to process your documents and create the vector store. 
    *(Note: The indexing script is not yet included in this POC. You will need to create a script using a library like LangChain or LlamaIndex to load your documents, split them into chunks, generate embeddings using the Gemini API, and store them in a vector store like FAISS or ChromaDB.)*

    **Example using LangChain (conceptual):**
    ```python
    from langchain_community.document_loaders import DirectoryLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    from langchain_community.vectorstores import FAISS
    import os

    # 1. Load documents
    loader = DirectoryLoader('documents/', glob="**/*.txt")
    docs = loader.load()

    # 2. Split documents
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    # 3. Create embeddings and vector store
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=os.getenv("GEMINI_API_KEY"))
    vectorstore = FAISS.from_documents(splits, embeddings)

    # 4. Save the vector store
    vectorstore.save_local("faiss_index")
    ```

### 4. Build and Run with Docker Compose

Once your `.env` file is configured and your RAG index is built, you can start the application using Docker Compose:

```bash
docker-compose up --build
```

This will build the Docker image and start the Django development server on `http://localhost:8000`.

### 5. Configure the LINE Webhook

You will need to expose your local server to the internet using a tool like [ngrok](https://ngrok.com/) to set up the LINE webhook.

1.  Start ngrok:
    ```bash
    ngrok http 8000
    ```
2.  Copy the HTTPS forwarding URL provided by ngrok (e.g., `https://<your-ngrok-subdomain>.ngrok.io`).
3.  In your LINE Developer Console, go to your channel's "Messaging API" settings and set the "Webhook URL" to `<your-ngrok-url>/callback/`.

You should now be able to send messages to your LINE Bot and receive responses from the RAG engine.

## Project Structure

```
.
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── README.md
├── requirements.txt
├── .env.example
├── line_bot/
│   ├── ... (Django app for LINE Bot logic)
└── line_bot_backend/
    ├── ... (Django project settings)
```

## API Endpoints

*   `POST /callback/`: The webhook endpoint for the LINE Messaging API.
