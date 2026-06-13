"""Test script to verify local MCP server endpoints at http://127.0.0.1:8000/"""

import asyncio
import json
import httpx


async def test_local_mcp_server():
    """Test all local MCP server endpoints directly"""
    
    base_url = "http://127.0.0.1:8000"
    
    print("\n" + "="*80)
    print("TESTING LOCAL MCP SERVER ENDPOINTS")
    print(f"Server URL: {base_url}")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        
        # Test 1: tavily_search
        print("\n--- Tool: tavily_search ---")
        try:
            response = await client.post(
                f"{base_url}/tavily_search",
                json={
                    "query": "hotels in Paris France",
                    "search_depth": "basic"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")
        
        # Test 2: get_flight_status
        print("\n--- Tool: get_flight_status ---")
        try:
            response = await client.post(
                f"{base_url}/get_flight_status",
                json={
                    "dep_iata": "LAX",
                    "arr_iata": "JFK",
                    "flight_date": "2026-08-01"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")
        
        # Test 3: google_maps_geocode
        print("\n--- Tool: google_maps_geocode ---")
        try:
            response = await client.post(
                f"{base_url}/google_maps_geocode",
                json={
                    "address": "Eiffel Tower, Paris, France"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")
        
        # Test 4: google_maps_directions
        print("\n--- Tool: google_maps_directions ---")
        try:
            response = await client.post(
                f"{base_url}/google_maps_directions",
                json={
                    "origin": "Paris, France",
                    "destination": "London, UK",
                    "mode": "driving"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")
        
        # Test 5: send_email
        print("\n--- Tool: send_email ---")
        try:
            response = await client.post(
                f"{base_url}/send_email",
                json={
                    "to": "test@example.com",
                    "subject": "Test Email",
                    "body": "This is a test email from MCP client testing."
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")

        # Test 6: search_flight (Skyscanner)
        print("\n--- Tool: search_flight ---")
        try:
            response = await client.post(
                f"{base_url}/search_flight",
                json={
                    "origin": "LAX",
                    "destination": "JFK",
                    "departure_date": "2026-07-30",
                    "adults": 1,
                    "cabin_class": "economy"
                },
                timeout=30.0
            )
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_local_mcp_server())
