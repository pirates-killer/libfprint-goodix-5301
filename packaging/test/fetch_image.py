#!/usr/bin/env python3
"""Download a Docker Hub image's amd64 layers (no docker needed).
usage: fetch_image.py library/debian 12 OUTDIR   -> OUTDIR/layer-N.tar.gz + manifest.json"""
import json, os, sys, urllib.request

repo, tag, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
tok = json.load(urllib.request.urlopen(
    f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"))["token"]
H = {"Authorization": f"Bearer {tok}"}
ACC = ("application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,"
       "application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json")

def get(path, accept=ACC):
    r = urllib.request.Request(f"https://registry-1.docker.io/v2/{repo}/{path}", headers={**H, "Accept": accept})
    return urllib.request.urlopen(r)

m = json.load(get(f"manifests/{tag}"))
if "manifests" in m:
    d = next(x for x in m["manifests"] if x["platform"]["architecture"] == "amd64"
             and x["platform"]["os"] == "linux")
    m = json.load(get(f"manifests/{d['digest']}"))
json.dump(m, open(os.path.join(out, "manifest.json"), "w"), indent=1)
for i, l in enumerate(m["layers"]):
    p = os.path.join(out, f"layer-{i}.tar.gz")
    with get(f"blobs/{l['digest']}", "*/*") as r, open(p, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"{repo}:{tag} layer {i}: {os.path.getsize(p)} B")
