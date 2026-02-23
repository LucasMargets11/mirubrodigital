import http.client
import mimetypes
from codecs import encode
import json

# Create a simple 1x1 PNG
png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

# Create multipart form data
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
dataList = []

# Add the file
dataList.append(encode('--' + boundary))
dataList.append(encode('Content-Disposition: form-data; name="logo_horizontal"; filename="test.png"'))
dataList.append(encode('Content-Type: image/png'))
dataList.append(encode(''))
dataList.append(png_data)
dataList.append(encode('--' + boundary + '--'))
dataList.append(encode(''))

body = b'\r\n'.join(dataList)

# Make the request
conn = http.client.HTTPConnection('localhost', 8000)

headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}',
    'Cookie': 'sessionid=YOUR_SESSION_ID_HERE'  # You'll need to replace this
}

print("Sending PATCH request to /api/v1/settings/branding/...")
print(f"Content-Type: {headers['Content-Type']}")
print(f"Body length: {len(body)} bytes")

conn.request('PATCH', '/api/v1/settings/branding/', body, headers)
response = conn.getresponse()

print(f"\nResponse status: {response.status} {response.reason}")
print(f"Response headers: {dict(response.getheaders())}")

response_data = response.read().decode()
print(f"\nResponse body:\n{response_data}")

try:
    print(f"\nParsed JSON:\n{json.dumps(json.loads(response_data), indent=2)}")
except:
    pass
