import json
import time
import uuid
import pathlib
import urllib.request

from google.auth.transport.requests import Request
from google.oauth2 import service_account

ROOT = pathlib.Path(r"D:\Projects\frontend-nextjs")
SA = ROOT / ".secrets" / "genomic-ast-invoker.json"
BASE = "https://genomic-ast-api-67343763423.us-central1.run.app"
FASTA = pathlib.Path(r"D:\Projects\backend-fastapi\data\samples\demo_ecoli_cipro_r.fasta")

creds = service_account.IDTokenCredentials.from_service_account_file(
    str(SA), target_audience=BASE
)
creds.refresh(Request())
auth = {"Authorization": f"Bearer {creds.token}"}


def call(method, path, data=None, headers=None, raw=False):
    h = dict(auth)
    if headers:
        h.update(headers)
    body = None
    if data is not None and not raw:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    elif raw:
        body = data
    req = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw_body = resp.read()
        if resp.status == 204:
            return None
        if not raw_body:
            return None
        return json.loads(raw_body.decode())


meta = {
    "sample_name": "demo_ecoli_live",
    "organism": "Escherichia coli",
    "platform": "illumina",
    "read_type": "assembly",
    "file_format": "fasta",
    "notes": "live smoke",
}
content = FASTA.read_bytes()
up = call(
    "POST",
    "/api/v2/uploads",
    {
        "filename": FASTA.name,
        "content_type": "application/octet-stream",
        "size_bytes": len(content),
        "metadata": meta,
    },
)
print("upload", up["upload_id"])
boundary = "----bound" + uuid.uuid4().hex
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{FASTA.name}"\r\n'
    "Content-Type: application/octet-stream\r\n\r\n"
).encode() + content + f"\r\n--{boundary}--\r\n".encode()
call(
    "PUT",
    f"/api/v2/uploads/{up['upload_id']}/content",
    body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    raw=True,
)
print("content_uploaded")
analysis = call(
    "POST",
    "/api/v2/analyses",
    {
        "upload_id": up["upload_id"],
        "object_key": up["object_key"],
        "metadata": meta,
    },
)
aid = analysis["analysis_id"]
print("analysis", aid)
st = None
for i in range(120):
    st = call("GET", f"/api/v2/analyses/{aid}")
    print(i, st["status"], st.get("current_stage"), st.get("progress"), st.get("error"))
    if st["status"] in {"completed", "failed"}:
        break
    time.sleep(5)

if st and st["status"] == "completed":
    result = call("GET", f"/api/v2/analyses/{aid}/result")
    print("drugs", len(result.get("antibiogram") or []))
    print("summary", (result.get("interpretation") or {}).get("summary", "")[:300])
else:
    print("FAILED", (st or {}).get("error"))
