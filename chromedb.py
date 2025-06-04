import chromadb
import datetime

# Initialize ChromaDB client (persistent storage)
chroma_client = chromadb.PersistentClient(path="./chroma_db")  # Store data in ./chroma_db
collection = chroma_client.get_or_create_collection("whatsapp_conversation_history")

def add_to_conversation_history(phone, role, message):
    """Adds a message to the ChromaDB conversation history."""
    timestamp = datetime.datetime.now().isoformat()
    collection.add(
        documents=[message],
        ids=[f"{phone}_{timestamp}"],  # Unique ID based on phone and timestamp
        metadatas=[{"role": role, "timestamp": timestamp,  "phone": phone}]
    )

def retrieve_conversation_history(phone, n_results=5):
    """Retrieves the most recent messages from the conversation history."""
    # Use the phone as a dummy query text to satisfy ChromaDB's requirement
    results = collection.query(
        query_texts=[phone],
        n_results=20,    # Fetch more to allow filtering
        where={"phone": phone}
    )
    # Flatten and sort by timestamp descending in Python
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    history = []
    items = []
    for doc, meta in zip(docs[0] if docs else [], metas[0] if metas else []):
        timestamp = meta.get("timestamp")
        items.append((timestamp, doc))
    # Sort by timestamp descending
    items.sort(reverse=True)
    for _, doc in items[:n_results]:
        history.append(doc)
    return history