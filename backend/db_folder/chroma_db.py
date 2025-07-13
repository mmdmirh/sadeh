import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions as chromadb_ef


def get_chroma_client(path: str):
    """
    Initializes and returns a PersistentClient for ChromaDB.
    """
    return chromadb.PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False) # Ensure telemetry is off
    )


def get_embedding_function(embedding_model_name: str, ollama_host: str = None, hf_token: str = None):
    """
    Returns the appropriate embedding function based on the model name.
    """
    if embedding_model_name.startswith('ollama/'):
        ollama_model_name = embedding_model_name.split('ollama/')[1]
        return chromadb_ef.OllamaEmbeddingFunction(
            model_name=ollama_model_name,
            url=ollama_host
        )
    elif embedding_model_name.startswith('huggingface/'):
        hf_model_name = embedding_model_name.split('huggingface/')[1]
        return chromadb_ef.HuggingFaceEmbeddingFunction(
            api_key=hf_token,
            model_name=hf_model_name
        )
    else:
        raise ValueError(f"Unsupported embedding model type: {embedding_model_name}")
