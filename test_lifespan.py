import asyncio
from main import lifespan
from fastapi import FastAPI
app = FastAPI()
async def test():
    async with lifespan(app):
        print('DONE')
asyncio.run(test())
