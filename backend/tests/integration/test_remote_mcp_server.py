"""Test script to verify MCP client tools against remote MCP server at https://multi-mcp-servers.onrender.com"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Set MCP server URL to remote server
os.environ["MCP_SERVER_URL"] = "https://multi-mcp-servers.onrender.com"


# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.skyscanner import SkyscannerMCPClient
from app.mcp_clients.tavily import TavilyMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.gmail import GmailMCPClient
from app.config import get_settings


async def test_aviationstack():
    """Test AviationStackMCPClient get_flight_status tool"""
    print("\n" + "="*80)
    print("TESTING AviationStackMCPClient (get_flight_status)")
    print("="*80)

    client = AviationStackMCPClient()

    print("\n--- Tool: get_flight_status ---")
    print("Parameters:")
    print(json.dumps({
        "dep_iata": "LAX",
        "arr_iata": "JFK"
    }, indent=2))
    print("\nCalling MCP client...")

    try:
        result = await client.call(
            "get_flight_status",
            {
                "dep_iata": "LAX",
                "arr_iata": "JFK"
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_skyscanner():
    """Test SkyscannerMCPClient search_flight tool"""
    print("\n" + "="*80)
    print("TESTING SkyscannerMCPClient (search_flight)")
    print("="*80)

    client = SkyscannerMCPClient()

    print("\n--- Tool: search_flight ---")
    print("Parameters:")
    print(json.dumps({
        "origin": "LAX",
        "destination": "JFK",
        "departure_date": "2026-10-01",
        "adults": 1,
        "cabin_class": "economy"
    }, indent=2))
    print("\nCalling MCP client...")

    try:
        result = await client.call(
            "search_flight",
            {
                "origin": "LAX",
                "destination": "JFK",
                "departure_date": "2026-10-01",
                "adults": 1,
                "cabin_class": "economy"
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tavily():
    """Test TavilyMCPClient tavily_search tool"""
    print("\n" + "="*80)
    print("TESTING TavilyMCPClient (tavily_search)")
    print("="*80)

    client = TavilyMCPClient()

    print("\n--- Tool: tavily_search ---")
    print("Parameters:")
    print(json.dumps({
        "query": "hotels in Paris France",
        "search_depth": "basic"
    }, indent=2))
    print("\nCalling MCP client...")

    try:
        result = await client.call(
            "tavily_search",
            {
                "query": "hotels in Paris France",
                "search_depth": "basic"
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_maps():
    """Test MapsMCPClient tools"""
    print("\n" + "="*80)
    print("TESTING MapsMCPClient")
    print("="*80)

    client = MapsMCPClient()

    # Test google_maps_geocode
    print("\n--- Tool: google_maps_geocode ---")
    print("Parameters:")
    print(json.dumps({
        "address": "Eiffel Tower, Paris, France"
    }, indent=2))
    print("\nCalling MCP client...")

    geocode_success = False
    try:
        result = await client.call(
            "google_maps_geocode",
            {
                "address": "Eiffel Tower, Paris, France"
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        geocode_success = True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    # Test google_maps_directions
    print("\n--- Tool: google_maps_directions ---")
    print("Parameters:")
    print(json.dumps({
        "origin": "Paris, France",
        "destination": "London, UK",
        "mode": "driving"
    }, indent=2))
    print("\nCalling MCP client...")

    directions_success = False
    try:
        result = await client.call(
            "google_maps_directions",
            {
                "origin": "Paris, France",
                "destination": "London, UK",
                "mode": "driving"
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        directions_success = True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    return geocode_success and directions_success


async def test_gmail():
    """Test GmailMCPClient send_email tool"""
    print("\n" + "="*80)
    print("TESTING GmailMCPClient (send_email)")
    print("="*80)

    client = GmailMCPClient()

    print("\n--- Tool: send_email ---")
    print("Parameters:")
    print(json.dumps({
        "to": "test@example.com",
        "subject": "Test Email from Remote MCP Server",
        "body": "This is a test email from MCP client testing against remote server."
    }, indent=2))
    print("\nCalling MCP client...")

    try:
        result = await client.call(
            "send_email",
            {
                "to": "test@example.com",
                "subject": "Test Email from Remote MCP Server",
                "body": "This is a test email from MCP client testing against remote server."
            },
            agent="test"
        )
        print("\nResponse:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all MCP client tests against remote server"""
    settings = get_settings()
    print("\n" + "="*80)
    print("MCP CLIENT TESTING AGAINST REMOTE SERVER")
    print(f"Server URL: {settings.mcp_server_url}")
    print("="*80)

    results = {}

    # Test AviationStack
    results["aviationstack"] = await test_aviationstack()

    # Test Skyscanner
    results["skyscanner"] = await test_skyscanner()

    # Test Tavily
    results["tavily"] = await test_tavily()

    # Test Maps
    results["maps"] = await test_maps()

    # Test Gmail
    results["gmail"] = await test_gmail()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for client_name, success in results.items():
        status = "PASSED" if success else "FAILED"
        print(f"{client_name.upper()}: {status}")

    total = len(results)
    passed = sum(1 for s in results.values() if s)
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*80)

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
