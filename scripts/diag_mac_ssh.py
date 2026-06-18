#!/usr/bin/env python3
import os
import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -x
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
ls -la ~/.ssh/
cat ~/.ssh/config 2>/dev/null || true
eval "$(ssh-agent -s)"
ssh-add "$HOME/.ssh/id_ed25519" 2>&1
ssh -v -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 | tail -20
echo SSH_EXIT=$?
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
_, stdout, stderr = client.exec_command("bash -s", timeout=60)
stdin = client.get_transport().open_session()
# simpler approach
_, stdout, stderr = client.exec_command(REMOTE, timeout=60)
print(stdout.read().decode())
print(stderr.read().decode())
client.close()
