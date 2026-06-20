from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    stockfish_path: str = r"C:\stockfish\stockfish-windows-x86-64-avx2.exe"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    analysis_depth: int = 15
    blunder_threshold: int = 300
    mistake_threshold: int = 100
    inaccuracy_threshold: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
