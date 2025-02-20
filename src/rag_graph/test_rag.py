import asyncio
from src.rag_graph.graph import graph
from src.utils.state import RAGState
from langchain_core.runnables import RunnableConfig

async def check_queries():
    config = RunnableConfig(
        configurable={
            "index_name": "au-blog-rag-fine-tuned",
            "filter_false": True,
            "result_summary_prompt": "A concise summary of the article in plain, non-technical language",
            "embedding_model": "wylupek/au-blog-rag-embedder",
        }
    )
    input_data = RAGState(
        query="We're discussing with a prospect client that wants to implement an AI feature in the app. Please show me article about our experience and knowledge."
    )
    output = await graph.ainvoke(input_data, config=config)
    for analysis in output['analyses']:
        print(analysis)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(check_queries())