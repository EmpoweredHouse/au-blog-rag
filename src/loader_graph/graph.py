from typing import Optional, List, Literal
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph

from src.utils.configuration import LoaderConfiguration
from src.utils.state import LoaderState, LoaderInputState, LoaderOutputState
from src.loader_graph.docling_loader import DoclingHTMLLoader
from src.utils.vector_store_manager import VectorStoreManager
from src.utils.sitemap_entry import Sitemap, SitemapEntry


# Node 1: Extract sitemap entries from input
async def extract_sitemap_entries(state: LoaderInputState) -> dict[str, List[SitemapEntry]]:
    sitemap = Sitemap(sitemap=state.sitemap)
    return {"sitemap_entries": sitemap.load()}


# Node 2: Filter sitemap entries based on existing vectors in the index
async def filter_sitemap_entries(
    state: LoaderState, *, config: Optional[RunnableConfig] = None
) -> dict[str, List[SitemapEntry]]:
    if state.sitemap_entries is None:
        raise ValueError("No sitemap entries found in state.")
    sitemap_entries = state.sitemap_entries

    if not config:
        raise ValueError("Configuration required to run <filter_sitemap_entries>.")
    configuration = LoaderConfiguration.from_runnable_config(config)
    vsm = VectorStoreManager(configuration.index_name, configuration, skip_connection_check=False)

    k = 1 if vsm.total_count == 0 else vsm.total_count
    dummy_query = ""
    try:
        results = vsm.vector_store.similarity_search(query=dummy_query, k=k, namespace=None)
        metadata_list = [
            {
                "id": doc.id,
                "source": doc.metadata['source'],
                "lastmod": doc.metadata['lastmod'],
            }
            for doc in results
        ]
    except Exception as e:
        raise RuntimeError(f"Failed to retrieve documents: {e}")

    db_entries = {
        (metadata["source"], datetime.fromisoformat(metadata["lastmod"]))
        for metadata in metadata_list
    }

    new_entries: List[SitemapEntry] = []
    delete_ids: List[str] = []
    for entry in sitemap_entries:
        # 0: new, 1: exists (no update), 2: exists but updated
        vector_flag = 0
        for (db_url, db_lastmod) in db_entries:
            if entry.url == db_url:
                if entry.lastmod <= db_lastmod:
                    vector_flag = 1
                    break
                vector_flag = 2
                break

        if vector_flag == 0:
            print(f"<Adding> {entry.url}")
            new_entries.append(entry)
        elif vector_flag == 1:
            print(f"<Skipping> {entry.url}")
            pass
        elif vector_flag == 2:
            print(f"<Updating> {entry.url}")
            for metadata in metadata_list:
                if metadata["source"] == entry.url:
                    delete_ids.append(metadata["id"])
            new_entries.append(entry)

    print(f"Ids to delete [{len(delete_ids)}]: {delete_ids}")
    vsm.delete_by_ids(delete_ids)
    return {"sitemap_entries": new_entries}


# Node 3: Create documents from sitemap entries, process, and index them
async def create_documents(
    state: LoaderState, *, config: Optional[RunnableConfig] = None
) -> dict[str, int]:
    if not config:
        raise ValueError("Configuration required to run <filter_sitemap_entries>.")
    configuration = LoaderConfiguration.from_runnable_config(config)
    batch_size = configuration.load_documents_batch_size

    if not state.sitemap_entries:
        return {"documents_count": 0}
    print(f"Processing {len(state.sitemap_entries)} sitemap entries.")
    sitemap_entries = state.sitemap_entries[:batch_size]

    if not config:
        raise ValueError("Configuration required to run <create_documents>.")
    configuration = LoaderConfiguration.from_runnable_config(config)
    vsm = VectorStoreManager(configuration.index_name, configuration)

    loader = DoclingHTMLLoader(sitemap_entry=sitemap_entries)
    documents = loader.load()

    markdown_separators = [
        "\n#{1,6} ",
        "```\n",
        "\n\\*\\*\\*+\n",
        "\n---+\n",
        "\n___+\n",
        "\n\n",
        "\n",
        " ",
        "",
    ]
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        add_start_index=True,
        strip_whitespace=True,
        separators=markdown_separators,
    )

    processed_documents = text_splitter.split_documents(documents)
    # for i, doc in enumerate(processed_documents):
    #     print(f"***** {i + 1} *****\n"
    #           f"{doc.metadata}\n"
    #           f"{doc.page_content}\n")

    vsm.vector_store.add_documents(documents=processed_documents)
    vsm.total_count += len(processed_documents)

    print(f"Loaded {len(processed_documents)} vectors into database.")
    print(f"Total vector count: {vsm.total_count}")
    return {"documents_count": state.documents_count + len(processed_documents),
            "sitemap_entries": state.sitemap_entries[batch_size:]}


async def check_next_batch(
    state: LoaderState, *, config: Optional[RunnableConfig] = None
) -> Literal["create_documents", "__end__"]:
    if not state.sitemap_entries:
        return "__end__"
    return "create_documents"


builder = StateGraph(LoaderState,
                     input=LoaderInputState,
                     output=LoaderOutputState,
                     config_schema=LoaderConfiguration)
builder.add_node(extract_sitemap_entries)
builder.add_node(filter_sitemap_entries)
builder.add_node(create_documents)

builder.add_edge("__start__", "extract_sitemap_entries")
builder.add_edge("extract_sitemap_entries", "filter_sitemap_entries")
builder.add_edge("filter_sitemap_entries", "create_documents")
builder.add_conditional_edges(
    "create_documents",
    check_next_batch
)

graph = builder.compile()
graph.name = "LoaderGraph"
