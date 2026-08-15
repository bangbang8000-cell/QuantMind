#!/usr/bin/env python3
"""Push docker v2s2 (schema 2) manifest for quantmind-public:gpu to ACR.

ACR personal rejects OCI manifests containing application/vnd.oci.empty.v1+json
layers (BuildKit empty layers). All blobs were already uploaded by `docker push`;
this script reconstructs a docker-format manifest from `docker save` output and
uploads it (plus any missing blobs) directly via the registry HTTP API.
"""
import base64
import hashlib
import http.client
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request

REG = "crpi-uyfb721x5vbg2abh.cn-shanghai.personal.cr.aliyuncs.com"
REPO = "quant-mind/quantmind"
TAG = "gpu"
TAR = "/tmp/qm-gpu.tar"
OUTDIR = "/tmp/qm-layers"
MANIFEST_MT = "application/vnd.docker.distribution.manifest.v2+json"
CONFIG_MT = "application/vnd.docker.container.image.v1+json"
GZIP_MT = "application/vnd.docker.image.rootfs.diff.tar.gzip"
TAR_MT = "application/vnd.docker.image.rootfs.diff.tar"


def http_req(method, url, headers=None, data=None, timeout=300):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def get_token(basic):
    st, hdrs, _ = http_req("GET", f"https://{REG}/v2/")
    www = hdrs.get("Www-Authenticate") or hdrs.get("WWW-Authenticate") or ""
    m_realm = re.search(r'realm="([^"]+)"', www)
    m_svc = re.search(r'service="([^"]+)"', www)
    if not m_realm:
        raise RuntimeError(f"no realm in WWW-Authenticate: {www}")
    url = m_realm.group(1) + "?" + urllib.parse.urlencode({
        "service": m_svc.group(1) if m_svc else "",
        "scope": f"repository:{REPO}:pull,push",
    })
    st, hdrs, body = http_req("GET", url, {"Authorization": "Basic " + basic})
    if st != 200:
        raise RuntimeError(f"token request {st}: {body[:200]}")
    return json.loads(body)["token"]


def blob_exists(bearer, digest):
    st, _, _ = http_req("HEAD", f"https://{REG}/v2/{REPO}/blobs/{digest}",
                        {"Authorization": bearer})
    return st == 200


def stream_upload(bearer, digest, path, size):
    """POST upload session + PUT blob streamed from file (http.client)."""
    st, hdrs, _ = http_req("POST", f"https://{REG}/v2/{REPO}/blobs/uploads/",
                           {"Authorization": bearer})
    if st not in (201, 202):
        raise RuntimeError(f"upload init {st}")
    loc = hdrs["Location"]
    if loc.startswith("http"):
        parts = urllib.parse.urlparse(loc)
        path_only = parts.path + ("?" + parts.query if parts.query else "")
    else:
        path_only = loc
    conn = http.client.HTTPSConnection(REG, timeout=600)
    with open(path, "rb") as f:
        conn.request(
            "PUT",
            path_only + ("&" if "?" in path_only else "?") + "digest=" + digest,
            body=f,
            headers={
                "Authorization": bearer,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(size),
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if resp.status not in (200, 201):
            raise RuntimeError(f"blob PUT {resp.status}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    d = json.load(open(os.path.expanduser("~/.docker/config.json")))
    auth = d["auths"][REG]["auth"]  # base64 user:pass
    bearer = "Bearer " + get_token(auth)
    print("token OK")

    t = tarfile.open(TAR)
    mj = json.load(t.extractfile("manifest.json"))[0]

    # config blob
    cfg_path = mj["Config"]
    cfg_bytes = t.extractfile(cfg_path).read()
    cfg_digest = "sha256:" + hashlib.sha256(cfg_bytes).hexdigest()
    print(f"config {cfg_digest} ({len(cfg_bytes)} bytes)")

    os.makedirs(OUTDIR, exist_ok=True)
    layers = []
    for i, lp in enumerate(mj["Layers"]):
        out_path = os.path.join(OUTDIR, f"layer-{i:02d}")
        src = t.extractfile(lp)
        with open(out_path, "wb") as f:
            for chunk in iter(lambda: src.read(8 * 1024 * 1024), b""):
                f.write(chunk)
        size = os.path.getsize(out_path)
        digest = "sha256:" + sha256_file(out_path)
        with open(out_path, "rb") as f:
            is_gz = f.read(2) == b"\x1f\x8b"
        mt = GZIP_MT if is_gz else TAR_MT
        layers.append({"mediaType": mt, "size": size, "digest": digest})
        print(f"layer[{i}] {mt.rsplit('.', 1)[-1]:>8} {digest[:24]} {size/1e9:.2f}GB")

    # upload missing blobs (most were already pushed by docker push)
    for i, L in enumerate(layers):
        if blob_exists(bearer, L["digest"]):
            print(f"layer[{i}] already on registry, skip")
        else:
            print(f"layer[{i}] missing, uploading {L['size']/1e9:.2f}GB ...")
            stream_upload(bearer, L["digest"],
                          os.path.join(OUTDIR, f"layer-{i:02d}"), L["size"])
    if blob_exists(bearer, cfg_digest):
        print("config already on registry, skip")
    else:
        print("config missing, uploading ...")
        st, hdrs, body = http_req(
            "POST", f"https://{REG}/v2/{REPO}/blobs/uploads/",
            {"Authorization": bearer})
        loc = hdrs["Location"]
        if not loc.startswith("http"):
            loc = "https://" + REG + loc
        sep = "&" if "?" in loc else "?"
        st, hdrs, body = http_req(
            "PUT", loc + sep + "digest=" + cfg_digest,
            {"Authorization": bearer, "Content-Type": "application/octet-stream"},
            cfg_bytes)
        if st not in (200, 201):
            raise RuntimeError(f"config PUT {st}: {body[:200]}")

    # docker v2s2 manifest (no OCI empty layers)
    manifest = {
        "schemaVersion": 2,
        "mediaType": MANIFEST_MT,
        "config": {"mediaType": CONFIG_MT, "size": len(cfg_bytes),
                   "digest": cfg_digest},
        "layers": layers,
    }
    mb = json.dumps(manifest, separators=(",", ":")).encode()
    st, hdrs, body = http_req(
        "PUT", f"https://{REG}/v2/{REPO}/manifests/{TAG}",
        {"Authorization": bearer, "Content-Type": MANIFEST_MT}, mb)
    print(f"manifest PUT: {st}")
    if st not in (200, 201):
        print(body[:500].decode(errors="replace"))
        sys.exit(1)
    print("SUCCESS: docker v2s2 manifest pushed for tag", TAG)


if __name__ == "__main__":
    main()
