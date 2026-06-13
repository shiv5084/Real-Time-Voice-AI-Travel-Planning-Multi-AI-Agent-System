import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import asyncio
from app.config import get_settings
from langchain_google_genai import ChatGoogleGenerativeAI

async def main():
    settings = get_settings()
    print(f"Gemini API key: {settings.gemini_api_key[:10]}...")
    print(f"Gemini Model: {settings.gemini_model}")
    
    llm = ChatGoogleGenerativeAI(
        google_api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        temperature=0.0,
    )
    
    print("Invoking Gemini...")
    resp = await llm.ainvoke("Write a one-sentence travel greeting.")
    print("Response:")
    print(resp.content)

if __name__ == "__main__":
    asyncio.run(main())
