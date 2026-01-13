#!/usr/bin/env python3
"""
Test script to simulate multiple REDCap webhook calls.
This script sends test patient data to the webhook endpoint.
"""

import requests
import json
import time
import sys
from typing import Dict, List, Tuple

# Configuration
WEBHOOK_URL = "http://localhost:8000/redcap/webhook"
HEALTH_CHECK_URL = "http://localhost:8000/health"

# Test data - simulating different CHU centers and patients
TEST_PATIENTS = [
    {
        "center_code": "Bordeaux",
        "patient_id": "CHUBDX_001",
        "age": 62,
        "sex": "M"
    },
    {
        "center_code": "Bordeaux",
        "patient_id": "CHUBDX_002",
        "age": 45,
        "sex": "F"
    },
    {
        "center_code": "Paris",
        "patient_id": "CHUPAR_001",
        "age": 38,
        "sex": "M"
    },
    {
        "center_code": "Paris",
        "patient_id": "CHUPAR_002",
        "age": 29,
        "sex": "F"
    },
    {
        "center_code": "Lyon",
        "patient_id": "CHULYO_001",
        "age": 55,
        "sex": "F"
    },
    {
        "center_code": "Lyon",
        "patient_id": "CHULYO_002",
        "age": 67,
        "sex": "M"
    },
    {
        "center_code": "Marseille",
        "patient_id": "CHUMAR_001",
        "age": 42,
        "sex": "M"
    }
]


def check_server_health() -> bool:
    """Check if the webhook server is running and healthy."""
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Server is healthy: {data.get('status')}")
            print(f"   Girder connection: {data.get('girder_connection')}")
            return True
        else:
            print(f"⚠️  Server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure FastAPI is running on http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Error checking server health: {str(e)}")
        return False


def send_webhook(patient_data: Dict) -> Tuple[bool, Dict]:
    """
    Send a single webhook request with patient data.
    
    Returns:
        (success: bool, response_data: dict)
    """
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=patient_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, response.json()
    except requests.exceptions.RequestException as e:
        return False, {"error": str(e)}


def run_tests(delay: float = 1.0, verbose: bool = True):
    """
    Run test suite by sending all test patient data.
    
    Args:
        delay: Delay between requests in seconds
        verbose: Print detailed information
    """
    print("=" * 60)
    print("REDCap Webhook Test Suite")
    print("=" * 60)
    print()
    
    # Check server health first
    if not check_server_health():
        print("\n❌ Server health check failed. Exiting.")
        sys.exit(1)
    
    print()
    print(f"Sending {len(TEST_PATIENTS)} test patient records...")
    print("-" * 60)
    
    results = {
        "success": 0,
        "failed": 0,
        "details": []
    }
    
    for i, patient in enumerate(TEST_PATIENTS, 1):
        if verbose:
            print(f"\n[{i}/{len(TEST_PATIENTS)}] Sending: {patient['patient_id']} from {patient['center_code']}...")
        
        success, response_data = send_webhook(patient)
        
        if success:
            results["success"] += 1
            if verbose:
                print(f"   ✅ Success: {response_data.get('message', 'Synced')}")
                if 'folder_structure' in response_data:
                    fs = response_data['folder_structure']
                    print(f"   📁 CHU Folder: {fs['chu_folder']['name']} (ID: {fs['chu_folder']['id'][:8]}...)")
                    print(f"   📁 Patient Folder: {fs['patient_folder']['name']} (ID: {fs['patient_folder']['id'][:8]}...)")
        else:
            results["failed"] += 1
            error_msg = response_data.get('detail', response_data.get('error', 'Unknown error'))
            if verbose:
                print(f"   ❌ Failed: {error_msg}")
        
        results["details"].append({
            "patient": patient,
            "success": success,
            "response": response_data
        })
        
        # Delay between requests
        if i < len(TEST_PATIENTS):
            time.sleep(delay)
    
    # Print summary
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total requests: {len(TEST_PATIENTS)}")
    print(f"✅ Successful: {results['success']}")
    print(f"❌ Failed: {results['failed']}")
    print()
    
    if results["failed"] > 0:
        print("Failed requests:")
        for detail in results["details"]:
            if not detail["success"]:
                patient = detail["patient"]
                error = detail["response"].get('detail', detail["response"].get('error', 'Unknown'))
                print(f"  - {patient['patient_id']}: {error}")
        print()
    
    return results


def test_single_patient(center_code: str, patient_id: str, age: int, sex: str):
    """Test with a single custom patient."""
    patient_data = {
        "center_code": center_code,
        "patient_id": patient_id,
        "age": age,
        "sex": sex
    }
    
    print(f"Testing single patient: {patient_id}")
    print("-" * 60)
    
    success, response = send_webhook(patient_data)
    
    if success:
        print("✅ Success!")
        print(json.dumps(response, indent=2))
    else:
        print("❌ Failed!")
        print(json.dumps(response, indent=2))
    
    return success, response


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test REDCap webhook endpoint")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output"
    )
    parser.add_argument(
        "--single",
        nargs=4,
        metavar=("CENTER", "PATIENT_ID", "AGE", "SEX"),
        help="Test a single patient: --single Bordeaux CHUBDX_001 62 M"
    )
    
    args = parser.parse_args()
    
    if args.single:
        center, patient_id, age, sex = args.single
        test_single_patient(center, patient_id, int(age), sex)
    else:
        run_tests(delay=args.delay, verbose=not args.quiet)

