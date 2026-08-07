#!/bin/bash
# Install rd-agent if the source was copied into the image (optional for OSS builds)
set -e

RD_DIR="${RD_AGENT_SRC:-/app/rd-agent}"

if [ -f "$RD_DIR/pyproject.toml" ] || [ -f "$RD_DIR/setup.py" ]; then
    echo "rd-agent found at $RD_DIR, installing..."
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_RDAGENT=0.1.dev1 \
        python -m pip install --no-cache-dir --root-user-action=ignore "$RD_DIR"
    rm -rf "$RD_DIR"
    echo "rd-agent installed successfully."
else
    echo "rd-agent not found at $RD_DIR, skipping installation."
    echo "To enable Alpha Agent factor evolution, clone rd-agent into the project root."
fi
