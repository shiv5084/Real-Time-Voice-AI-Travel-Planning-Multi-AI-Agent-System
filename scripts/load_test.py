"""
Load Testing Script for Phase 7B.

This script performs load testing with concurrent users to verify system stability
and performance under load. Uses asyncio for concurrent request handling.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import statistics

import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import get_settings


# Sample requests for load testing
LOAD_TEST_REQUESTS = [
    {
        "request": "Plan a 3-day trip to London with $2000 budget",
        "constraints": {"destination": "London", "duration": 3, "travelers": 1, "budget": 2000}
    },
    {
        "request": "Weekend trip to Paris for couples, $3000 budget",
        "constraints": {"destination": "Paris", "duration": 2, "travelers": 2, "budget": 3000}
    },
    {
        "request": "5-day family trip to Tokyo, $5000 budget, 4 people",
        "constraints": {"destination": "Tokyo", "duration": 5, "travelers": 4, "budget": 5000}
    },
    {
        "request": "Solo backpacking in Southeast Asia for 2 weeks, $1500",
        "constraints": {"destination": "Southeast Asia", "duration": 14, "travelers": 1, "budget": 1500}
    },
    {
        "request": "Luxury weekend in New York, $4000 budget",
        "constraints": {"destination": "New York", "duration": 3, "travelers": 2, "budget": 4000}
    }
]


class LoadTester:
    """Performs load testing on the travel planning API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.settings = get_settings()
        self.base_url = base_url
        self.results = []

    async def make_request(self, request_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Make a single API request and record metrics."""
        start_time = time.time()
        result = {
            "user_id": user_id,
            "request": request_data["request"],
            "success": False,
            "latency_ms": 0,
            "status_code": None,
            "error": None
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/trips/plan",
                    json={
                        "raw_request": request_data["request"],
                        "constraints": request_data["constraints"]
                    }
                )
                
                latency_ms = (time.time() - start_time) * 1000
                result["latency_ms"] = latency_ms
                result["status_code"] = response.status_code
                
                if response.status_code == 200:
                    result["success"] = True
                else:
                    result["error"] = f"HTTP {response.status_code}"
                    
        except Exception as e:
            result["latency_ms"] = (time.time() - start_time) * 1000
            result["error"] = str(e)
        
        return result

    async def simulate_user(self, user_id: int, num_requests: int = 5) -> List[Dict[str, Any]]:
        """Simulate a user making multiple requests."""
        user_results = []
        
        for i in range(num_requests):
            request_data = LOAD_TEST_REQUESTS[i % len(LOAD_TEST_REQUESTS)]
            result = await self.make_request(request_data, user_id)
            user_results.append(result)
            
            # Small delay between requests to simulate realistic user behavior
            await asyncio.sleep(0.5)
        
        return user_results

    async def run_concurrent_test(self, num_users: int = 10, requests_per_user: int = 5) -> Dict[str, Any]:
        """Run load test with concurrent users."""
        print("="*60)
        print("Load Testing")
        print("="*60)
        print(f"Concurrent Users: {num_users}")
        print(f"Requests per User: {requests_per_user}")
        print(f"Total Requests: {num_users * requests_per_user}")
        print(f"Environment: {self.settings.app_env}")
        print(f"Base URL: {self.base_url}")
        
        start_time = time.time()
        
        # Create tasks for all users
        tasks = [
            self.simulate_user(user_id, requests_per_user)
            for user_id in range(num_users)
        ]
        
        # Run all tasks concurrently
        user_results = await asyncio.gather(*tasks)
        
        # Flatten results
        all_results = [result for user_result in user_results for result in user_result]
        self.results = all_results
        
        total_duration = time.time() - start_time
        
        # Calculate metrics
        metrics = self._calculate_metrics(all_results, total_duration)
        
        # Print summary
        self._print_summary(metrics, num_users, requests_per_user)
        
        # Export results
        self._export_results(metrics, num_users, requests_per_user)
        
        return metrics

    def _calculate_metrics(self, results: List[Dict], total_duration: float) -> Dict[str, Any]:
        """Calculate load testing metrics."""
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        latencies = [r["latency_ms"] for r in successful]
        
        metrics = {
            "total_requests": len(results),
            "successful_requests": len(successful),
            "failed_requests": len(failed),
            "success_rate": len(successful) / len(results) if results else 0,
            "total_duration_sec": total_duration,
            "requests_per_second": len(results) / total_duration if total_duration > 0 else 0,
        }
        
        if latencies:
            latencies.sort()
            metrics["latency_min_ms"] = min(latencies)
            metrics["latency_max_ms"] = max(latencies)
            metrics["latency_avg_ms"] = statistics.mean(latencies)
            metrics["latency_median_ms"] = statistics.median(latencies)
            metrics["latency_p50_ms"] = latencies[len(latencies) // 2]
            metrics["latency_p95_ms"] = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
            metrics["latency_p99_ms"] = latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[0]
        else:
            metrics["latency_min_ms"] = 0
            metrics["latency_max_ms"] = 0
            metrics["latency_avg_ms"] = 0
            metrics["latency_median_ms"] = 0
            metrics["latency_p50_ms"] = 0
            metrics["latency_p95_ms"] = 0
            metrics["latency_p99_ms"] = 0
        
        return metrics

    def _print_summary(self, metrics: Dict, num_users: int, requests_per_user: int):
        """Print load testing summary."""
        print(f"\n{'='*60}")
        print("LOAD TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Requests: {metrics['total_requests']}")
        print(f"Successful: {metrics['successful_requests']}")
        print(f"Failed: {metrics['failed_requests']}")
        print(f"Success Rate: {metrics['success_rate']:.1%}")
        print(f"Total Duration: {metrics['total_duration_sec']:.2f}s")
        print(f"Requests/Second: {metrics['requests_per_second']:.2f}")
        print(f"\nLatency Metrics:")
        print(f"  Min: {metrics['latency_min_ms']:.0f}ms")
        print(f"  Max: {metrics['latency_max_ms']:.0f}ms")
        print(f"  Average: {metrics['latency_avg_ms']:.0f}ms")
        print(f"  Median: {metrics['latency_median_ms']:.0f}ms")
        print(f"  p50: {metrics['latency_p50_ms']:.0f}ms")
        print(f"  p95: {metrics['latency_p95_ms']:.0f}ms")
        print(f"  p99: {metrics['latency_p99_ms']:.0f}ms")
        
        # Check against targets
        print(f"\nTarget Comparison:")
        print(f"  Success Rate (target >=99%): {metrics['success_rate']:.1%} {'[PASS]' if metrics['success_rate'] >= 0.99 else '[FAIL]'}")
        print(f"  Concurrent Users (target 10): {num_users} {'[PASS]' if num_users >= 10 else '[FAIL]'}")
        print(f"  No Failures: {'[PASS]' if metrics['failed_requests'] == 0 else '[FAIL]'}")
        
        if metrics['failed_requests'] > 0:
            print(f"\nFailed Requests:")
            for result in self.results:
                if not result['success']:
                    print(f"  User {result['user_id']}: {result['error']}")

    def _export_results(self, metrics: Dict, num_users: int, requests_per_user: int):
        """Export load test results to JSON file."""
        output_dir = Path(__file__).parent.parent / "backend" / "test_results"
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"load_test_{num_users}users_{timestamp}.json"
        
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "environment": self.settings.app_env,
            "test_config": {
                "num_users": num_users,
                "requests_per_user": requests_per_user,
                "total_requests": num_users * requests_per_user
            },
            "metrics": metrics,
            "results": self.results
        }
        
        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2)

        print(f"\n[OK] Results exported to: {output_file}")


async def main():
    """Main entry point."""
    # Parse command line arguments
    num_users = 10
    requests_per_user = 5
    
    if len(sys.argv) > 1:
        num_users = int(sys.argv[1])
    if len(sys.argv) > 2:
        requests_per_user = int(sys.argv[2])
    
    tester = LoadTester()
    await tester.run_concurrent_test(num_users, requests_per_user)


if __name__ == "__main__":
    asyncio.run(main())
