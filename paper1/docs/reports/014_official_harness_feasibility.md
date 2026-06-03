# 014 — Official SWE-bench Harness Feasibility

Date: 2026-06-03

## Summary

Current HPC container cannot directly run the official SWE-bench Docker harness.

This is not a Python/package problem. The official SWE-bench code is present and importable, but the runtime Docker layer is missing from the current container.

Decision: keep the current local harness as the fast inner-loop evaluator, and add official SWE-bench Docker evaluation as an outer-loop audit on a Docker-capable environment. Do not replace the local harness inside this container right now.

## Environment Findings

Observed in `/Lishun/_archive/.local_env_bak/research/AgentOS`:

- Running as `root` inside a Kubernetes/Docker container.
- `/Lishun` is NFS; persistent but slow for small files.
- `/tmp` is local and fast, but ephemeral.
- `docker` CLI is not installed.
- `/var/run/docker.sock` is absent.
- No `dockerd`, `containerd`, `podman`, `nerdctl`, `singularity`, or `apptainer` runtime is available in the container.
- Container capabilities do not include `CAP_SYS_ADMIN`, so starting Docker-in-Docker/rootless container stacks is not a safe assumption.
- Local SWE-bench repo exists at `paper1/data/SWE-bench`.
- `swebench` Python package is importable; local version reports `4.1.0`.
- `python -m swebench.harness.run_evaluation --help` works.

Implication: official harness code is available, but official evaluation cannot actually run because it requires Docker image build/run.

## Official Harness Requirements

SWE-bench official evaluation is Docker-based. It builds and runs:

1. base image;
2. environment image;
3. instance image;
4. test container per evaluated task.

Official docs require:

- Docker installed;
- Docker daemon/socket available;
- large local disk, usually 120GB+ minimum;
- enough CPU/RAM;
- network for image/dependency build unless images are prebuilt/cached.

Current container fails the first two requirements.

## Why We Should Not Force It Here

Trying to force official harness in this container would create more risk than value:

- No Docker daemon or socket exists.
- Installing Docker CLI alone would not help.
- Starting `dockerd` inside this pod likely requires privileged container permissions not currently present.
- Building SWE-bench images on `/Lishun` would be slow and NFS-hostile.
- The root filesystem has about 171GB free but is already 91% used; official instance image caching can grow quickly.
- Long Docker builds would compete with current model experiments and increase failure noise.

## Accuracy Implication

Local harness is useful but not final paper-grade evidence.

It gives fast iteration and diagnosis:

- gold sanity gate;
- patch apply;
- fail-before / fail-after;
- pass-to-pass;
- repo-specific compatibility patches;
- trace and failure attribution.

But local harness differs from official SWE-bench in environment isolation, dependency resolution, Docker images, grading scripts, and sometimes test semantics. Therefore:

- Local harness results can support engineering iteration and relative debugging.
- Paper headline resolved numbers should eventually be audited by official SWE-bench harness.
- Any result should be labeled `local harness` until official Docker evaluation confirms it.

## Recommended Plan

### Near Term

Keep current workflow:

1. local harness for fast gold sanity and model experiments;
2. strict clean-row rules: no duplicate, no missing row, no worktree crash, no harness compatibility mixed into model patch;
3. export official prediction JSONL for selected clean rows.

### Official Audit Lane

Add a separate official-eval lane outside this current container:

Option A: Docker-capable HPC node or login node

- Ask for a Docker-enabled or privileged evaluation node.
- Mount `/Lishun` for input/output only.
- Put Docker image storage on local scratch, not NFS.
- Run only a small audit first: 3-5 predictions, `max_workers=1-2`, `cache_level=base/env`.

Option B: Dedicated VM/cloud

- Use a VM with Docker and enough local SSD.
- Copy prediction JSONL and needed reports from `/Lishun`.
- Run official SWE-bench evaluation there.

Option C: Modal / sb-cli

- SWE-bench docs mention cloud evaluation through Modal and sb-cli.
- This may be viable if credentials and network are available.
- Treat it as an official-audit path, not the main inner-loop.

## Minimal Official Evaluation Command

Once Docker is available:

```bash
cd /Lishun/_archive/.local_env_bak/research/AgentOS/paper1
export TMPDIR=/tmp
export PIP_CACHE_DIR=/Lishun/.cache/pip
PYTHONPATH=data/SWE-bench python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path data/runs/<official_predictions>.jsonl \
  --instance_ids sympy__sympy-14774 django__django-10924 \
  --max_workers 1 \
  --cache_level base \
  --clean True \
  --run_id official_audit_smoke_001 \
  --report_dir logs/run_evaluation
```

Do not start with a large matrix. First prove one SymPy and one Django known-local-PASS task can evaluate officially.

## Integration Work Needed

Before official audit, verify prediction export contains:

```json
{
  "instance_id": "...",
  "model_name_or_path": "BudgetFlow/<strategy>",
  "model_patch": "diff --git ..."
}
```

Required checks:

- `model_patch` is only the submitted/generated patch;
- no harness compatibility edit is included;
- instance ids match SWE-bench Lite/Verified dataset ids;
- local clean rows are traceable to official prediction rows;
- official result is stored separately from local-harness result.

## Paper Positioning

Use two-tier evidence language:

- Inner loop: `local harness resolved` for development and failure attribution.
- Outer loop: `official SWE-bench resolved` for paper headline or final audit.

If official audit disagrees with local harness:

- treat official as the final outcome;
- use local trace to diagnose why;
- do not tune local harness to force agreement unless gold sanity proves the official semantics.

## Answer

Should we move the whole system to official harness now?

No. Not in the current container.

Should we eventually run official harness?

Yes. It is necessary for paper-grade accuracy, but it should be a separate audit lane on a Docker-capable environment.
