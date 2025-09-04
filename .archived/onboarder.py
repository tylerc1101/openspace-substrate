#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Footer, Header, Label, ListItem, ListView, Log, Rule, TabPane, TabbedContent, Checkbox, Pretty

@dataclass
class Env:
    name: str
    path: Path
    vars_file: Path
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def discover(cls, home: Path) -> List["Env"]:
        envs: List[Env] = []
        if not home.exists():
            return envs
        for child in sorted(home.iterdir()):
            if child.is_dir():
                vars_file = None
                for candidate in ("env.yml", "environment.yml", "variables.yml"):
                    if (child / candidate).exists():
                        vars_file = child / candidate
                        break
                if vars_file:
                    envs.append(Env(name=child.name, path=child, vars_file=vars_file))
        return envs

    def load(self) -> None:
        with open(self.vars_file, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or {}

@dataclass
class Task:
    id: str
    label: str
    command: List[str] | str
    cwd: Optional[Path] = None
    env: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    shell: bool = False

@dataclass
class TaskStatus:
    id: str
    state: str = "pending"
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    rc: Optional[int] = None
    message: str = ""

class TaskRegistry:
    def __init__(self, env: Env) -> None:
        self.env = env
        self.vars = env.data

    def _e(self, key: str, default: str = "") -> str:
        node: Any = self.vars
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return str(node)

    def build(self) -> List[Task]:
        base_env = {
            "ENVIRONMENT": self.env.name,
            "ONBOARDER_HOME": str(self.env.path),
        }
        repo_root = Path.cwd()
        tasks: List[Task] = [
            Task(
                id="preflight",
                label="Preflight checks",
                command=[
                    "bash",
                    "-lc",
                    "echo 'Checking tools...' && which ansible || true; which terraform || true; which tofu || true",
                ],
                cwd=repo_root,
                env=base_env,
            ),
            Task(
                id="ansible_rke2",
                label="Deploy RKE2 cluster (Ansible)",
                command=[
                    "bash",
                    "-lc",
                    textwrap.dedent(
                        f"""
                        set -euo pipefail
                        export ANSIBLE_STDOUT_CALLBACK=yaml
                        ansible-playbook -i ansible/rke2/inventory/{self.env.name}/hosts.yml \
                          ansible/rke2/site.yml -e @'{self.env.vars_file}'
                        """
                    ).strip(),
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["preflight"],
            ),
            Task(
                id="load_darksite",
                label="Load darksite bundles (images)",
                command=[
                    "bash",
                    "-lc",
                    f"make load-darksite-bundles ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["ansible_rke2"],
            ),
            Task(
                id="helm_harbor",
                label="Install Harbor (Helmfile)",
                command=[
                    "bash",
                    "-lc",
                    f"make helmfile-install HELMFILE_CHART=harbor ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["load_darksite"],
            ),
            Task(
                id="helm_rancher",
                label="Install Rancher (Helmfile)",
                command=[
                    "bash",
                    "-lc",
                    f"make helmfile-install HELMFILE_CHART=rancher ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["helm_harbor"],
            ),
            Task(
                id="tf_rancher_bootstrap",
                label="Terraform: Rancher Bootstrap",
                command=[
                    "bash",
                    "-lc",
                    f"make terraform-rancher-bootstrap-apply ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["helm_rancher"],
            ),
            Task(
                id="install_gitea",
                label="Install Gitea",
                command=[
                    "bash",
                    "-lc",
                    f"make install-gitea ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["tf_rancher_bootstrap"],
            ),
            Task(
                id="install_argocd",
                label="Install ArgoCD",
                command=[
                    "bash",
                    "-lc",
                    f"make install-argocd ENVIRONMENT={self.env.name}",
                ],
                cwd=repo_root,
                env=base_env,
                depends_on=["install_gitea"],
            ),
        ]
        return tasks

class TaskRunner:
    def __init__(self, *, log_sink: "LogView") -> None:
        self.status: Dict[str, TaskStatus] = {}
        self.log_sink = log_sink
        self.cancel_event = asyncio.Event()

    async def run(self, tasks: List[Task], selected: Optional[Iterable[str]] = None, dry_run: bool = False) -> None:
        id_to_task = {t.id: t for t in tasks}
        to_run = list(selected) if selected else [t.id for t in tasks]
        ordered: List[str] = []
        seen: set[str] = set()

        def dfs(tid: str) -> None:
            if tid in seen:
                return
            seen.add(tid)
            for dep in id_to_task[tid].depends_on:
                if dep in id_to_task:
                    dfs(dep)
            ordered.append(tid)

        for tid in to_run:
            if tid in id_to_task:
                dfs(tid)

        final_order: List[str] = []
        added: set[str] = set()
        for tid in ordered:
            if tid not in added:
                final_order.append(tid)
                added.add(tid)

        for tid in final_order:
            if self.cancel_event.is_set():
                self._set_status(tid, state="canceled", message="Canceled before start")
                continue
            task = id_to_task[tid]
            failed_dep = next((d for d in task.depends_on if self.status.get(d, TaskStatus(d)).state in {"failed", "canceled"}), None)
            if failed_dep:
                self._set_status(tid, state="skipped", message=f"Skipped due to failed dependency: {failed_dep}")
                continue
            if dry_run:
                self._set_status(tid, state="skipped", message="Dry-run (skipped execution)")
                await self.log_sink.write(f"[dry-run] {task.id}: {task.label}\n  {task.command}\n")
                continue
            await self._execute(task)

    def _set_status(self, tid: str, **kwargs: Any) -> None:
        st = self.status.get(tid) or TaskStatus(id=tid)
        for k, v in kwargs.items():
            setattr(st, k, v)
        self.status[tid] = st

    async def _execute(self, task: Task) -> None:
        self._set_status(task.id, state="running", start_ts=time.time(), message="")
        await self.log_sink.write(f"\n=== ▶ {task.label} [{task.id}] ===\n")
        cmd = task.command if isinstance(task.command, list) else ["bash", "-lc", task.command]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(task.cwd) if task.cwd else None,
                env={**os.environ, **task.env},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout
            async for line in proc.stdout:  # type: ignore[assignment]
                await self.log_sink.write(line.decode(errors="replace"))
            rc = await proc.wait()
            if rc == 0:
                self._set_status(task.id, state="ok", end_ts=time.time(), rc=rc)
                await self.log_sink.write(f"=== ✓ {task.label} completed (rc=0) ===\n")
            else:
                self._set_status(task.id, state="failed", end_ts=time.time(), rc=rc, message=f"rc={rc}")
                await self.log_sink.write(f"=== ✗ {task.label} FAILED (rc={rc}) ===\n")
        except Exception as e:
            self._set_status(task.id, state="failed", end_ts=time.time(), message=str(e))
            await self.log_sink.write(f"*** Exception running {task.id}: {e}\n")

    def cancel(self) -> None:
        self.cancel_event.set()

class EnvPicker(Widget):
    class Changed(Message):
        def __init__(self, env: Env) -> None:
            self.env = env
            super().__init__()

    def __init__(self, envs: List[Env]):
        super().__init__()
        self.envs = envs
        self.list = ListView()

    def compose(self) -> ComposeResult:
        yield Label("Environments", id="picker-title")
        self.list.clear()
        for env in self.envs:
            self.list.append(ListItem(Label(env.name)))
        yield self.list

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.index
        if 0 <= idx < len(self.envs):
            self.post_message(self.Changed(self.envs[idx]))

class LogView(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.log = Log(auto_scroll=True)

    def compose(self) -> ComposeResult:
        yield self.log

    async def write(self, text: str) -> None:
        self.log.write(text.rstrip("\n"))

class Overview(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.table = DataTable(zebra_stripes=True)

    def compose(self) -> ComposeResult:
        self.table.add_columns("ID", "Task", "State", "Message", "Start", "End")
        yield self.table

    def update_statuses(self, statuses: Dict[str, TaskStatus], tasks: Dict[str, Task]) -> None:
        self.table.clear()
        for tid, task in tasks.items():
            st = statuses.get(tid, TaskStatus(tid))
            start = time.strftime("%H:%M:%S", time.localtime(st.start_ts)) if st.start_ts else ""
            end = time.strftime("%H:%M:%S", time.localtime(st.end_ts)) if st.end_ts else ""
            self.table.add_row(tid, task.label, st.state, st.message, start, end)

class VariablesView(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.pretty = Pretty({})
        self.path_label = Label("")

    def compose(self) -> ComposeResult:
        yield Horizontal(Label("Variables"), Button("Open in $EDITOR", id="edit"), id="vars-header")
        yield self.path_label
        yield Rule()
        yield VerticalScroll(self.pretty)

    def set_env(self, env: Env) -> None:
        self.path_label.update(f"File: {env.vars_file}")
        self.pretty.update(env.data)

class TasksView(Widget):
    class RunRequested(Message):
        def __init__(self, selection: List[str], dry_run: bool) -> None:
            self.selection = selection
            self.dry_run = dry_run
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.table = DataTable(zebra_stripes=True)
        self.checkboxes: Dict[str, Checkbox] = {}
        self._tasks: Dict[str, Task] = {}

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Button("Run Selected", id="run"),
            Button("Run All", id="run_all"),
            Button("Dry-Run", id="dry_run"),
            Button("Cancel", id="cancel"),
            id="task-actions",
        )
        self.table.add_columns("Select", "ID", "Task", "Depends")
        yield self.table

    def set_tasks(self, tasks: List[Task]) -> None:
        self._tasks = {t.id: t for t in tasks}
        self.table.clear()
        self.checkboxes.clear()
        for t in tasks:
            cb = Checkbox()
            self.checkboxes[t.id] = cb
            self.table.add_row(cb, t.id, t.label, ",".join(t.depends_on))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self.post_message(self.RunRequested(self._selected_ids(), dry_run=False))
        elif event.button.id == "run_all":
            self.post_message(self.RunRequested(list(self._tasks.keys()), dry_run=False))
        elif event.button.id == "dry_run":
            self.post_message(self.RunRequested(self._selected_ids() or list(self._tasks.keys()), dry_run=True))
        elif event.button.id == "cancel":
            self.app.runner.cancel()  

    def _selected_ids(self) -> List[str]:
        return [tid for tid, cb in self.checkboxes.items() if cb.value]

class MainApp(App):
    CSS = """
    Screen { layout: vertical; }
    #top { height: 3; }
    #main { height: 1fr; }
    #left { width: 32; border: tall $accent; }
    #right { border: tall $accent; }
    #vars-header { height: 3; content-align: center middle; }
    #task-actions { height: 3; content-align: left middle; padding: 0 1; }
    #picker-title { content-align: center middle; height: 3; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "run_selected", "Run"),
        Binding("a", "run_all", "Run All"),
        Binding("l", "focus_logs", "Logs"),
        Binding("o", "open_editor", "Edit Vars"),
    ]

    def __init__(self, home: Path) -> None:
        super().__init__()
        self.home = home
        self.envs: List[Env] = Env.discover(home)
        if not self.envs:
            sample = home / "sample_environment"
            sample.mkdir(parents=True, exist_ok=True)
            (sample / "env.yml").write_text(
                textwrap.dedent(
                    """
                    # Sample environment variables
                    cluster_name: "test.local"
                    dns: ["10.0.0.52", "10.0.0.53"]
                    ntp: ["time.nist.gov"]
                    """
                ).strip()
            )
            self.envs = Env.discover(home)
        for e in self.envs:
            e.load()
        self.current_env: Env = self.envs[0]
        self.registry = TaskRegistry(self.current_env)
        self.tasks: List[Task] = self.registry.build()
        self.runner = TaskRunner(log_sink=LogView())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main"):
            with Horizontal():
                with Vertical(id="left"):
                    picker = EnvPicker(self.envs)
                    yield picker
                    yield Rule()
                    yield Label("Tips:\n - Press A to run all\n - Press L for logs\n - Press O to edit vars", id="tips")
                with Vertical(id="right"):
                    with TabbedContent():
                        with TabPane("Overview"):
                            self.overview = Overview()
                            yield self.overview
                        with TabPane("Variables"):
                            self.vars_view = VariablesView()
                            self.vars_view.set_env(self.current_env)
                            yield self.vars_view
                        with TabPane("Tasks"):
                            self.tasks_view = TasksView()
                            self.tasks_view.set_tasks(self.tasks)
                            yield self.tasks_view
                        with TabPane("Logs"):
                            self.log_view = self.runner.log_sink
                            yield self.log_view
        yield Footer()
        self.overview.update_statuses(self.runner.status, {t.id: t for t in self.tasks})

    def on_env_picker_changed(self, msg: EnvPicker.Changed) -> None:
        self.current_env = msg.env
        self.current_env.load()
        self.registry = TaskRegistry(self.current_env)
        self.tasks = self.registry.build()
        self.vars_view.set_env(self.current_env)
        self.tasks_view.set_tasks(self.tasks)
        self.overview.update_statuses(self.runner.status, {t.id: t for t in self.tasks})

    def on_tasks_view_run_requested(self, msg: TasksView.RunRequested) -> None:
        asyncio.create_task(self._run(msg.selection, msg.dry_run))

    async def _run(self, selection: List[str], dry_run: bool) -> None:
        await self.runner.run(self.tasks, selected=selection, dry_run=dry_run)
        self.overview.update_statuses(self.runner.status, {t.id: t for t in self.tasks})

    def action_run_selected(self) -> None:
        selection = self.tasks_view._selected_ids() or [t.id for t in self.tasks]
        asyncio.create_task(self._run(selection, dry_run=False))

    def action_run_all(self) -> None:
        asyncio.create_task(self._run([t.id for t in self.tasks], dry_run=False))

    def action_focus_logs(self) -> None:
        self.set_focus(self.log_view)

    def action_open_editor(self) -> None:
        editor = os.environ.get("EDITOR", "vi")
        path = str(self.current_env.vars_file)
        asyncio.create_task(self._open_editor(editor, path))

    async def _open_editor(self, editor: str, path: str) -> None:
        await self.log_view.write(f"Opening editor: {editor} {path}\n")
        proc = await asyncio.create_subprocess_exec(editor, path)
        await proc.wait()
        self.current_env.load()
        self.vars_view.set_env(self.current_env)
        await self.log_view.write("Variables reloaded.\n")


def main(argv: List[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Onboarder TUI")
    parser.add_argument("--home", default="./usr_home", help="Path to environments home directory")
    args = parser.parse_args(argv)
    home = Path(args.home).resolve()
    app = MainApp(home)
    app.run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
