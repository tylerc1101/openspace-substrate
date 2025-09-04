# Onboarder Environment Template

This folder is a **template environment**.  
You should **never edit this folder directly**. Instead, run:

```bash
./onboarder-run.sh init --env <name>
```

That will copy this template into usr_home/<name>/ (e.g. usr_home/prod/), and you will work only inside your new environment folder.

# 📌 Quick Start

## Initialize

```bash
./onboarder-run.sh init --env test
```

This creates usr_home/test/ with a copy of this template.

## Edit Config

Open usr_home/test/config.toml and update:

- profile → which profile you want (e.g. rancher-harbor, eks-ecr, etc.)

- infrastructure → baremetal, vmware, or aws

- DNS, NTP, cluster node IPs

## Set up Secrets

```bash
./onboarder-run.sh secrets init --env test
```

This creates an encrypted secrets.sops.yaml

You’ll be prompted to edit plaintext once, then it will be sealed

### To verify:

```bash
./onboarder-run.sh secrets check --env test
```

## Check Plan

```bash
./onboarder-run.sh plan --env test
```

Generates plan.yaml from your config

Prints the list of tasks that will run

## Apply

```bash
./onboarder-run.sh apply --env test
```

Runs all tasks in order, streaming output live

Logs are saved under usr_home/test/logs/<run_id>/

# 📂 Folder Layout

config.toml
Main configuration for this environment (profile, infra, DNS, NTP, cluster nodes, addons).

secrets.sops.yaml
Encrypted file storing credentials (managed with SOPS + age).
Never edit directly — use onboarder-run.sh secrets init.

.sops.yaml / keys/
SOPS encryption policy + age key (sealed). Created automatically.

ansible/inventory.ini
Hosts grouped by cluster. Used by Ansible tasks.

terraform/
Place Terraform stacks if needed for this environment.
State is local in this folder.

helmfile/helmfile.yaml
Example Helmfile. Onboarder profiles may generate their own.

custom/pre/tasks.yaml
Optional tasks to run before the onboarder plan.
Define tasks in the same schema as plan tasks.

custom/post/tasks.yaml
Optional tasks to run after the onboarder plan.

logs/
Auto-created. Each run stores its logs here.

artifacts/
Place where generated kubeconfig, reports, or exported bundles can be saved.

🛠️ Example Commands

Run preflight + plan:

./onboarder-run.sh plan --env prod


Apply with no pauses and auto-confirm:

./onboarder-run.sh apply --env prod --yes --no-pause


Resume after a failure:

./onboarder-run.sh apply --env prod --resume --yes


Run only specific tasks:

./onboarder-run.sh apply --env prod --only rke2,addons --yes

# ⚠️ Notes

Always run inside the container via onboarder-run.sh — do not execute scripts directly.

Do not check secrets into Git. Only config.toml and plan.yaml are safe to version.

Custom tasks should be idempotent — failures will stop the entire run.

All outputs are logged in usr_home/<env>/logs/<run_id>/.

