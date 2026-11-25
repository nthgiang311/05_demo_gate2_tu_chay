"""Call before importing the core: only OPENAI_API_KEY from this package's own .env, tracing off."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def setup():
    if not os.environ.get("OPENAI_API_KEY"):
        try:
            from dotenv import dotenv_values
            k = dotenv_values(os.path.join(HERE, ".env")).get("OPENAI_API_KEY")
        except ImportError:
            k = None
        if k:
            os.environ["OPENAI_API_KEY"] = k
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
