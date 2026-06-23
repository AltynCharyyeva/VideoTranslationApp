import os
import re
import time
import pytest
import requests

BASE = os.getenv("API_BASE", "http://localhost:8000")
TEST_EMAIL = os.getenv("TEST_EMAIL", "gold@gmail.com")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "12345")

HEADERS = {}

def setup_module():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    HEADERS["Authorization"] = f"Bearer {r.json()['access_token']}"


def _wait_for_completion(job_id, timeout=600):
    for _ in range(timeout // 5):
        data = requests.get(f"{BASE}/videos/{job_id}", headers=HEADERS).json()
        if data["status"] == "COMPLETED":
            return data
        if data["status"] == "FAILED":
            pytest.fail(f"Job failed: {data}")
        time.sleep(5)
    pytest.fail("Timeout waiting for job completion")


def test_short_video_completes_and_produces_srt():
    with open("tests/fixtures/song.mp4", "rb") as f:
        r = requests.post(f"{BASE}/videos/translate", headers=HEADERS,
                          data={"target_language": "ron_Latn"},
                          files={"file": ("clip.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    job_id = r.json()["translation_id"]

    result = _wait_for_completion(job_id)
    assert result["status"] == "COMPLETED"

    srt = requests.get(f"{BASE}/videos/{job_id}/download/srt", headers=HEADERS)
    assert srt.status_code == 200
    assert "-->" in srt.text
    assert len(srt.text) > 10


def test_srt_timestamps_are_chronological():
    with open("tests/fixtures/song.mp4", "rb") as f:
        r = requests.post(f"{BASE}/videos/translate", headers=HEADERS,
                          data={"target_language": "ron_Latn"},
                          files={"file": ("clip.mp4", f, "video/mp4")})
    job_id = r.json()["translation_id"]
    _wait_for_completion(job_id)

    srt = requests.get(f"{BASE}/videos/{job_id}/download/srt", headers=HEADERS).text
    times = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) -->", srt)
    assert times == sorted(times)


def test_silent_video_does_not_crash():
    with open("tests/fixtures/silence.mp4", "rb") as f:
        r = requests.post(f"{BASE}/videos/translate", headers=HEADERS,
                          data={"target_language": "ron_Latn"},
                          files={"file": ("clip.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    job_id = r.json()["translation_id"]
    # should COMPLETE with empty SRT, not FAIL
    result = _wait_for_completion(job_id)
    assert result["status"] == "COMPLETED"
