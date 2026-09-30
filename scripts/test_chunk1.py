import asyncio
import httpx

urls = [
    "https://www.ventureplastics.com",
    "https://tasus.com",
    "https://www.evcoplastics.com",
    "https://www.sussexim.com",
    "https://www.montaplast.com",
]

async def test_url(u):
    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            r = await client.get(u)
            print(f"{u}: status={r.status_code}")
    except Exception as e:
        print(f"{u}: error={type(e).__name__} {e}")

async def main():
    await asyncio.gather(*[test_url(u) for u in urls])

if __name__ == "__main__":
    asyncio.run(main())
