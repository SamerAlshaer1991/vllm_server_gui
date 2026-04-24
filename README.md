# VLLM_Engine

`VLLM_Engine` is a Python GUI for building, saving, syncing, and running `vllm serve` commands.

This project is intentionally scoped to one command:

- `vllm serve`

The GUI does not invent its own argument list. Instead, it generates the page from the locally installed CLI by running:

```bash
vllm serve --help=all
```

That gives you a serve builder that follows the exact vLLM version installed on the machine.

## What This Project Does

The GUI provides:

- one serve-focused page
- grouped argument sections matching `vllm serve --help=all`
- a checkbox on every argument
- `true` / `false` selectors for boolean flags
- text inputs for simple values
- textareas for JSON, repeated flags, and multi-value inputs
- saved profiles in the left sidebar
- a live shell-safe command preview
- `Copy command`, `Run command`, and `Stop process`
- `Sync arguments` to rebuild the schema from the installed CLI
- `Clear logs` to remove files from the runtime logs directory
- backend-only `.env` loading for paths, binaries, cache locations, and secrets

## Environment This README Targets

This README is written around the server profile that was documented in the previous setup notes:

- OS: Ubuntu 24.04
- Architecture: `aarch64`
- GPU: NVIDIA GB10
- Driver: `580.126.09`
- CUDA toolkit: `13.0`
- Python: `3.12`
- Working root: `/opt/ai`
- Python virtual environment: `/opt/ai/.venv`
- Project directory: `/opt/ai/VLLM_Engine`

If you move this project to another machine, especially one that is not ARM64 or not CUDA 13, you may need to adjust the vLLM and PyTorch installation section and the pinned runtime packages in `requirements.txt`.

## How The App Is Built

The app is intentionally simple and modular.

- `vllm_engine/server.py`
  HTTP server and JSON API routes.
- `vllm_engine/pages.py`
  Single-page routing for the serve builder.
- `vllm_engine/schema.py`
  Loads the generated serve schema and renders markdown hints.
- `vllm_engine/commands.py`
  Turns UI state into a final `vllm serve` command.
- `vllm_engine/runtime.py`
  Starts and stops backend serve processes and tracks logs, PID files, and launch scripts.
- `vllm_engine/profiles.py`
  Stores saved serve profiles.
- `vllm_engine/maintenance.py`
  Clears log files and re-syncs serve arguments.
- `vllm_engine/envfiles.py`
  Loads `.env`, expands variables, and ensures runtime directories exist.
- `tools/sync_engine_args.py`
  Runs `vllm serve --help=all`, parses the output, and rebuilds the GUI schema.

## Source Of Truth For Arguments

The GUI reads from:

```text
/opt/ai/VLLM_Engine/vllm_engine/data/serve_builder_schema.json
```

That file is generated, not hand-maintained.

Best practice:

1. install or upgrade `vllm`
2. run `python tools/sync_engine_args.py`
3. reload the GUI

Manual edits to `serve_builder_schema.json` are possible, but they will be overwritten the next time the sync script runs.

## Server Prerequisites

Use these steps before building the Python environment.

### 1. Update Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install required system packages

```bash
sudo apt install -y \
  python3.12 \
  python3.12-venv \
  python3.12-dev \
  python3-pip \
  build-essential \
  gcc \
  g++ \
  git \
  curl \
  wget \
  ca-certificates \
  pkg-config
```

Why these matter:

- `python3.12-venv` is required for `python3.12 -m venv`
- `python3.12-dev` provides `Python.h`
- `build-essential`, `gcc`, and `g++` help with native builds used by parts of the ML stack

If `python3.12-dev` is missing, one common failure is:

```text
fatal error: Python.h: No such file or directory
```

### 3. Verify Python and compilers

```bash
python3.12 --version
which python3.12
gcc --version
g++ --version
ls /usr/include/python3.12/Python.h
```

### 4. Prepare `/opt/ai`

```bash
sudo mkdir -p /opt/ai
sudo chown -R q2web:q2web /opt/ai
chmod 755 /opt/ai
cd /opt/ai
```

### 5. Verify NVIDIA driver and GPU

```bash
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader
```

Expected values on the documented server:

```text
NVIDIA GB10, 580.126.09, 12.1
```

### 6. Verify CUDA toolkit and runtime libraries

```bash
which nvcc || true
nvcc --version || true
ls -ld /usr/local/cuda* || true
ldconfig -p | grep libcudart || true
find /usr/local -name 'libcudart.so*' 2>/dev/null
```

Expected important values on this server:

```text
/usr/local/cuda/bin/nvcc
Cuda compilation tools, release 13.0
libcudart.so.13
```

### 7. Optional shell CUDA path exports

Use this only if `nvcc` or CUDA libraries are not visible automatically:

```bash
echo 'export CUDA_HOME=/usr/local/cuda' >> ~/.bashrc
echo 'export PATH=$CUDA_HOME/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$CUDA_HOME/targets/sbsa-linux/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

## Python Environment Setup

### 1. Create the root venv

```bash
cd /opt/ai
python3.12 -m venv .venv
source .venv/bin/activate
python --version
which python
```

Expected:

```text
/opt/ai/.venv/bin/python
```

### 2. Upgrade base packaging tools

```bash
cd /opt/ai
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --upgrade uv packaging
```

### 3. Install the full pinned stack

This project now ships a fuller `requirements.txt` for the documented CUDA 13 / ARM64 machine profile.

Install it from the activated venv:

```bash
cd /opt/ai
source .venv/bin/activate
python -m pip install -r /opt/ai/VLLM_Engine/requirements.txt
```

That file includes:

- GUI dependencies
- Ray
- CUDA 13 PyTorch packages
- the pinned CUDA 13 ARM64 vLLM wheel

### 4. Verify the installed stack

```bash
python - <<'PY'
import ray
import torch
import vllm
print("ray:", ray.__version__)
print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
print("vllm:", vllm.__version__)
PY
```

On the documented server the expected versions are:

```text
ray: 2.55.1
torch: 2.10.0+cu130
torch cuda: 13.0
cuda available: True
vllm: 0.19.1+cu130
```

### Why The CUDA 13 vLLM Wheel Matters

Using a generic `pip install vllm` can install a CUDA 12 build. On this server that caused:

```text
ImportError: libcudart.so.12: cannot open shared object file: No such file or directory
```

The pinned wheel in `requirements.txt` avoids that mismatch for this machine profile.

## Backend `.env`

Create the backend environment file from the template:

```bash
cd /opt/ai/VLLM_Engine
cp .env.example .env
```

Current example content:

```bash
# Runtime paths
PROJECT_ROOT=/opt/ai/VLLM_Engine
SCRIPTS_DIR=${PROJECT_ROOT}/scripts
LOGS_DIR=${PROJECT_ROOT}/logs
PIDS_DIR=${PROJECT_ROOT}/pids

# Cache paths
XDG_CACHE_HOME=${PROJECT_ROOT}/.cache
XDG_CONFIG_HOME=${XDG_CACHE_HOME}/config
XDG_DATA_HOME=${XDG_CACHE_HOME}/data
HF_HOME=${XDG_CACHE_HOME}/huggingface
HF_HUB_CACHE=${HF_HOME}/hub
TORCH_HOME=${XDG_CACHE_HOME}/torch
# VLLM_CACHE_DIR=${XDG_CACHE_HOME}/vllm

# Runtime environment
ENV_PREFIX=/opt/ai/.venv
PATH=${ENV_PREFIX}/bin:${PATH}
PYTHON_BIN=${ENV_PREFIX}/bin/python
VLLM_BIN=${ENV_PREFIX}/bin/vllm
RAY_BIN=${ENV_PREFIX}/bin/ray
HF_TOKEN=""
```

Notes:

- `.env` is used only by the backend
- it is not exposed by the web server
- `HF_TOKEN` is the place to store your Hugging Face token if needed
- `VLLM_BIN` should point to the `vllm` binary inside `/opt/ai/.venv`

## Sync The Serve Arguments

To regenerate the GUI schema from the installed CLI:

```bash
cd /opt/ai
source .venv/bin/activate
cd /opt/ai/VLLM_Engine
python tools/sync_engine_args.py
```

This command runs:

```bash
vllm serve --help=all
```

and writes:

```text
/opt/ai/VLLM_Engine/vllm_engine/data/serve_builder_schema.json
```

You can also do this from the GUI with the `Sync arguments` button.

What the button does:

1. runs the sync script in the backend
2. clears the schema cache in the web app
3. reloads the page so the new arguments appear

## Serve The GUI

Run the GUI on all interfaces:

```bash
cd /opt/ai
source .venv/bin/activate
cd /opt/ai/VLLM_Engine
python -m vllm_engine --host 0.0.0.0 --port 8088
```

Open:

```text
http://YOUR_HOST:8088/
```

Port conventions:

- GUI: `8088`
- vLLM API server: usually `8000`

Using `8088` for the GUI avoids colliding with the vLLM serve port.

## How To Use The GUI

### 1. Choose the model

For the normal model field, the recommended input is the positional `model_tag`.

In the GUI:

- open `Positional Arguments`
- enable `model_tag`
- enter something like `Qwen/Qwen3-0.6B`

That becomes:

```bash
vllm serve Qwen/Qwen3-0.6B
```

There is also a `--model` flag in `ModelConfig`, but for normal serve usage the positional `model_tag` is the cleaner choice.

### 2. Save a profile

Profiles store:

- the enabled arguments
- each entered value
- the generated command preview
- the number of selected arguments
- the save timestamp

### 3. Run a command

When you click `Run command`, the backend:

1. loads `.env`
2. creates runtime directories if needed
3. writes a launch script in `scripts/`
4. writes logs in `logs/`
5. writes the PID file in `pids/`
6. starts the process in its own process group

### 4. Stop a command

`Stop process` sends `SIGTERM`, waits briefly, and escalates to `SIGKILL` only if needed.

### 5. Clear old logs

`Clear logs` deletes files in the logs directory.

Behavior details:

- if no vLLM process is running, all log files are removed
- if a vLLM process is running, its active current log file is kept and other log files are removed

## Test Presets

### Safe smoke test

Enable only:

- `-h, --help` = `true`

That checks the GUI, backend run path, script creation, and log writing without trying to load a model.

### Small real serve test

Set:

- `model_tag` = `Qwen/Qwen3-0.6B`
- `--host` = `0.0.0.0`
- `--port` = `8000`
- `--max-model-len` = `1024`
- `--gpu-memory-utilization` = `0.5`
- `--max-num-seqs` = `4`
- `--max-num-batched-tokens` = `512`

That gives:

```bash
vllm serve Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000 --max-model-len 1024 --gpu-memory-utilization 0.5 --max-num-seqs 4 --max-num-batched-tokens 512
```

## Troubleshooting

### `libcudart.so.12` missing

This usually means a CUDA 12 vLLM build was installed on a CUDA 13 machine. Reinstall the pinned CUDA 13 wheel from `requirements.txt`.

### `cuda available: False`

Check:

- `nvidia-smi`
- `nvcc --version`
- `ldconfig -p | grep libcudart`
- the installed torch build is `+cu130`

### `Python.h` missing

Install:

```bash
sudo apt install -y python3.12-dev
```

### GUI starts but sync fails

Check:

- `/opt/ai/.venv/bin/vllm` exists
- `.env` points `VLLM_BIN` to the right path
- `vllm serve --help=all` works in the venv

## Current Important Files

- [README.md](/opt/ai/VLLM_Engine/README.md)
- [requirements.txt](/opt/ai/VLLM_Engine/requirements.txt)
- [.env.example](/opt/ai/VLLM_Engine/.env.example)
- [.env](/opt/ai/VLLM_Engine/.env)
- [tools/sync_engine_args.py](/opt/ai/VLLM_Engine/tools/sync_engine_args.py)
- [serve_builder_schema.json](/opt/ai/VLLM_Engine/vllm_engine/data/serve_builder_schema.json)
- [server.py](/opt/ai/VLLM_Engine/vllm_engine/server.py)
- [maintenance.py](/opt/ai/VLLM_Engine/vllm_engine/maintenance.py)

## Sources

- local CLI output from `vllm serve --help=all`
- `https://docs.vllm.ai/en/latest/configuration/serve_args/#cli-arguments`
- `https://docs.vllm.ai/en/latest/configuration/engine_args/`
