from typing import List
from langchain.embeddings import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain.document_loaders import WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain.vectorstores.base import VectorStore
from langchain.schema import Document

class DocumentProcessor:
    def __init__(self, llm_model_name: str, embeddings_model_name: str, vector_db_path: str):
        """
        Initializes the Document Processor.

        Parameters:
            llm_model_name (str): The name of the LLM model to be used.
            embeddings_model_name (str): The name of the Embeddings model to be used.
            vector_db_path (str): Path to store/load the vector database.
        """
        self.embeddings = OpenAIEmbeddings(model=embeddings_model_name)
        self.vector_db = self._initialize_vector_db(vector_db_path)
        
        # # Delete all collections
        # for collection in self.vector_db._client.list_collections():
        #     self.vector_db._client.delete_collection(collection.name)
        
        self.llm = ChatOpenAI(
            model_name=llm_model_name,
            temperature=0.5
        )

    def _initialize_vector_db(self, vector_db_path: str) -> VectorStore:
        """
        Initializes the vector database.
        If a saved vector database exists, it will load it; otherwise, it will create a new one.

        Parameters:
            vector_db_path (str): Path to store/load the vector database.
        Returns:
            VectorStore: The vector database.
        """
        return Chroma(persist_directory=vector_db_path, embedding_function=self.embeddings)

    # def load_and_index_documents(self, urls: List[str]) -> None:
    #     loader = DoclingHTMLLoader(file_path=urls)
    #     text_splitter = RecursiveCharacterTextSplitter(
    #         chunk_size=1000,
    #         chunk_overlap=100
    #     )
    # 
    #     docs = loader.load()
    #     splits = text_splitter.split_documents(docs)
    #     
    #     texts = [doc.page_content for doc in splits]
    #     metadatas = [doc.metadata for doc in splits]
    # 
    #     # Add summaries to the vector store
    #     self.vector_db.add_texts(
    #         texts=texts,
    #         metadatas=metadatas
    #     )    
    
    def load_and_index_documents(self, urls: List[str]) -> None:
        # Load documents using your custom loader
        loader = DoclingHTMLLoader(file_path=urls)
        docs = loader.load()
        
        # Initialize MarkdownHeaderTextSplitter
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        text_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

        # Split the documents
        splits = []
        for doc in docs:
            # Split content using MarkdownHeaderTextSplitter
            chunks = text_splitter.split_text(doc.page_content)
            for chunk in chunks:
                # Preserve original metadata and add header-based metadata
                chunk.metadata.update(doc.metadata)  # Combine parent doc metadata
                splits.append(chunk)
        
        # Extract texts and metadata for storage in the vector database
        texts = [doc.page_content for doc in splits]
        metadatas = [doc.metadata for doc in splits]

        # Add the splits to the vector store
        self.vector_db.add_texts(
            texts=texts,
            metadatas=metadatas
        )
        
    def test_db(self) -> None:
        import json

        # Get all collections
        collections = self.vector_db._client.list_collections()

        # Iterate over each collection and print documents with metadata
        for collection in collections:
            print(f"\nCollection Name: {collection.name}")
            # Fetch the collection object
            col = self.vector_db._client.get_collection(collection.name)
    
            # Retrieve documents and metadata
            docs = col.get(include=["metadatas", "documents"])  # Adjust 'include' as per your structure

            # Iterate over each document and print it nicely formatted
            for i, (doc, metadata) in enumerate(zip(docs["documents"], docs["metadatas"])):
                print(f"\nDocument {i+1}")
                print("Content:", doc)
                print("Metadata:", json.dumps(metadata, indent=4))  # Nicely formatted metadata



# Module 1: Document Processing
doc_processor = DocumentProcessor(
    llm_model_name="gpt-4o-mini",
    embeddings_model_name="text-embedding-3-small",
    vector_db_path="./vector_db"
)

# Extract URLs and limit to the first 5 elements
urls_list = [entry.url for entry in sitemap_entries]

doc_processor.load_and_index_documents(urls=urls_list)
# doc_processor.test_db()
