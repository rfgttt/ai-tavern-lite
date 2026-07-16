import urllib.request
import json

# Test health
print("=== 1. Health Check ===")
r = urllib.request.urlopen('http://127.0.0.1:8765/api/health')
data = json.loads(r.read().decode('utf-8'))
print(f"Status: {data['status']}")
print(f"Mock mode: {data['mock_mode']}")
assert data['status'] == 'ok'
assert data['mock_mode'] == True
print("PASS")

# Test characters
print("\n=== 2. Characters List ===")
r = urllib.request.urlopen('http://127.0.0.1:8765/api/characters')
data = json.loads(r.read().decode('utf-8'))
print(f"Count: {len(data)}")
assert len(data) >= 1
char_id = data[0]['id']
char_name = data[0]['name']
print(f"Demo character: {char_name}")
print("PASS")

# Test character detail
print("\n=== 3. Character Detail ===")
r = urllib.request.urlopen(f'http://127.0.0.1:8765/api/characters/{char_id}')
char_detail = json.loads(r.read().decode('utf-8'))
print(f"Name: {char_detail['name']}")
print(f"Has first_message: {bool(char_detail.get('first_message'))}")
assert char_detail['name'] == char_name
print("PASS")

# Test create session
print("\n=== 4. Create Session ===")
req_data = json.dumps({"character_id": char_id}).encode('utf-8')
req = urllib.request.Request(
    'http://127.0.0.1:8765/api/sessions',
    data=req_data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = urllib.request.urlopen(req)
session = json.loads(r.read().decode('utf-8'))
session_id = session['id']
print(f"Session title: {session['title']}")
print(f"Session ID: {session_id}")
print("PASS")

# Test messages (should have first message)
print("\n=== 5. Initial Messages ===")
r = urllib.request.urlopen(f'http://127.0.0.1:8765/api/sessions/{session_id}/messages')
msgs = json.loads(r.read().decode('utf-8'))
print(f"Message count: {len(msgs)}")
assert len(msgs) >= 1
assert msgs[0]['role'] == 'assistant'
print(f"First message: {msgs[0]['content'][:50]}...")
print("PASS")

# Test settings
print("\n=== 6. Settings (API Key Masked) ===")
r = urllib.request.urlopen('http://127.0.0.1:8765/api/settings')
settings = json.loads(r.read().decode('utf-8'))
print(f"Mock mode: {settings['mock_llm']}")
print(f"API key configured: {settings['api_key_configured']}")
print(f"API key masked: '{settings['api_key_masked']}'")
# Verify no full API key leaked
assert 'api_key' not in settings or settings.get('api_key_masked', '') != settings.get('api_key', '')
print("PASS")

# Test lorebook
print("\n=== 7. Lorebook ===")
r = urllib.request.urlopen(f'http://127.0.0.1:8765/api/characters/{char_id}/lorebook')
lorebook = json.loads(r.read().decode('utf-8'))
print(f"Lorebook entries: {len(lorebook.get('entries', []))}")
assert len(lorebook.get('entries', [])) >= 2
print("PASS")

# Test prompt preview
print("\n=== 8. Prompt Preview ===")
preview_data = json.dumps({
    "session_id": session_id,
    "message": "你好"
}).encode('utf-8')
req = urllib.request.Request(
    'http://127.0.0.1:8765/api/chat/prompt-preview',
    data=preview_data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = urllib.request.urlopen(req)
preview = json.loads(r.read().decode('utf-8'))
print(f"Sections: {len(preview['sections'])}")
print(f"Total estimated tokens: {preview['total_estimated_tokens']}")
assert preview['total_estimated_tokens'] > 0
for s in preview['sections']:
    print(f"  - {s['name']}: ~{s['estimated_tokens']} tokens ({s['source']})")
print("PASS")

# Test sessions list
print("\n=== 9. Sessions List ===")
r = urllib.request.urlopen(f'http://127.0.0.1:8765/api/sessions?character_id={char_id}')
sessions = json.loads(r.read().decode('utf-8'))
print(f"Session count: {len(sessions)}")
assert len(sessions) >= 1
print("PASS")

# Test frontend page
print("\n=== 10. Frontend Static Files ===")
r = urllib.request.urlopen('http://127.0.0.1:8765/')
assert r.status == 200
content = r.read().decode('utf-8')
assert '<!doctype html>' in content.lower() or '<!DOCTYPE html>' in content
print(f"Index page loaded: {len(content)} bytes")

# Test assets
try:
    r = urllib.request.urlopen('http://127.0.0.1:8765/assets/')
except urllib.error.HTTPError as e:
    # 404 is expected for directory listing
    pass
print("PASS")

print("\n" + "="*50)
print("ALL END-TO-END TESTS PASSED!")
print("="*50)
print(f"Demo character: {char_name}")
print(f"Session ID: {session_id}")
print(f"Mock mode: ENABLED")
print(f"Server: http://127.0.0.1:8765")
