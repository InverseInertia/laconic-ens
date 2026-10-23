"""Runs solver blocks in a worker process, so that a slow or frozen one can be stopped.

A thread cannot be killed, and a solver may sit inside one scipy or CoolProp call for as long as it
likes; a process can always be. One worker is kept warm (importing scipy and building the unit
registry takes about a second) and is replaced whenever a job has to be killed. Jobs run one at a
time. The page starts a job, polls it for new log lines, and may interrupt it; a job that outlives
its block's `timeout:` is stopped the same way.

The worker only computes: it returns the result record and the page decides whether to write it
into the worksheet (the text may have changed in the meantime)."""
import multiprocessing
import os
import threading
import time
import uuid

from . import solver

STARTUP_SLACK = 30.0     # seconds allowed on top of a block's timeout for the worker to start up
MAX_LOG_LINES = 5000
KEEP_JOBS = 20


class Busy(Exception):
    pass


def _worker(conn):
    """Worker process: take a job, send log lines as they happen, send the outcome."""
    parent = os.getppid()

    def orphaned():
        while True:
            time.sleep(2)
            if os.getppid() != parent:     # the server is gone: do not keep computing for nobody
                os._exit(0)
    threading.Thread(target=orphaned, daemon=True).start()
    from .evaluator import registry
    from .sheet import solve_block
    registry()
    while True:
        try:
            job = conn.recv()
        except (EOFError, OSError):
            return
        if job is None:
            return
        try:
            out = solve_block(job["text"], job["line"], job["units"], log=lambda m: conn.send(("log", m)),
                              mode=job["mode"])
            conn.send(("done", out))
        except BaseException as e:   # reported to the page; the worker stays up for the next job
            conn.send(("error", f"{type(e).__name__}: {e}"))


class Job:
    def __init__(self, line, mode, timeout):
        self.id = uuid.uuid4().hex[:12]
        self.line, self.mode, self.timeout = line, mode, timeout
        self.state = "running"      # running, done, failed, interrupted, timeout
        self.log, self.outcome, self.error = [], None, ""
        self.started, self.finished = time.monotonic(), None

    def add(self, line):
        if len(self.log) < MAX_LOG_LINES:
            self.log.append(line)
        elif len(self.log) == MAX_LOG_LINES:
            self.log.append("... (log truncated)")

    def view(self, since=0):
        end = self.finished or time.monotonic()
        out = {"id": self.id, "line": self.line, "mode": self.mode, "state": self.state,
               "log": self.log[since:], "next": len(self.log), "elapsed": round(end - self.started, 2)}
        if self.state != "running":
            out["outcome"], out["error"] = self.outcome, self.error
        return out


class Jobs:
    def __init__(self, target=_worker):
        self._target = target
        self._lock = threading.RLock()
        self._jobs = {}
        self._proc = self._conn = None
        self.current = None

    # -- worker process
    def _spawn(self):
        ctx = multiprocessing.get_context("spawn")
        mine, theirs = ctx.Pipe()
        proc = ctx.Process(target=self._target, args=(theirs,), daemon=True)
        proc.start()
        theirs.close()
        self._proc, self._conn = proc, mine

    def _discard_worker(self):
        proc, conn = self._proc, self._conn
        self._proc = self._conn = None
        if proc is not None:
            try:
                proc.kill()
                proc.join(2)
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def warm(self):
        """Start the worker now so the first run does not wait for it."""
        with self._lock:
            if self._proc is None or not self._proc.is_alive():
                self._spawn()

    def shutdown(self):
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.send(None)
                except Exception:
                    pass
            self._discard_worker()

    # -- jobs
    def start(self, text, line, mode, units):
        """Begin solving the block on `line`. Raises Busy if a job is already running and
        SolverError if the line is not a runnable block."""
        lines = text.splitlines()
        if not 1 <= line <= len(lines) or not solver.is_solver_line(lines[line - 1]):
            raise solver.SolverError(f"Line {line} is not a !root, !minimize or !maximize line")
        timeout = solver.parse_block(lines, line - 1).timeout
        with self._lock:
            if self.current is not None and self.current.state == "running":
                raise Busy("Another solver is still running. Interrupt it or wait for it to finish")
            self.warm()
            job = Job(line, mode, timeout)
            self._conn.send({"text": text, "line": line, "units": list(units), "mode": mode})
            self.current = job
            self._jobs[job.id] = job
            for old in list(self._jobs)[:-KEEP_JOBS]:
                del self._jobs[old]
            threading.Thread(target=self._pump, args=(job, self._proc, self._conn), daemon=True).start()
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def _finish(self, job, state, **fields):
        with self._lock:
            if job.state != "running":
                return False
            job.state, job.finished = state, time.monotonic()
            for k, v in fields.items():
                setattr(job, k, v)
            return True

    def _kill(self, job, state, message):
        """Stop a running job by killing the worker, and start a fresh one for the next job."""
        with self._lock:
            if not self._finish(job, state):
                return False
            job.add(message)
            self._discard_worker()
            self._spawn()
            return True

    def interrupt(self, job_id):
        job = self._jobs.get(job_id)
        if job is None:
            return None
        self._kill(job, "interrupted", f"Interrupted after {time.monotonic() - job.started:.1f} s. "
                                       "Nothing was stored; the starting values are unchanged.")
        return job

    def _pump(self, job, proc, conn):
        """Move messages from the worker into the job until it finishes, is killed or runs out of time."""
        deadline = job.started + job.timeout + STARTUP_SLACK
        while job.state == "running":
            try:
                if conn.poll(0.1):
                    kind, payload = conn.recv()
                    if kind == "log":
                        job.add(payload)
                    elif kind == "done":
                        ok = bool(payload.get("ok"))
                        self._finish(job, "done" if ok else "failed", outcome=payload,
                                     error="" if ok else payload.get("message", ""))
                    else:
                        job.add(payload)
                        self._finish(job, "failed", error=payload)
                    continue
                if not proc.is_alive():
                    self._finish(job, "failed", error="The solver process stopped unexpectedly")
                    job.add(job.error)
                    self._after_death(proc)
                    return
            except (EOFError, OSError):
                if job.state == "running":
                    self._finish(job, "failed", error="The solver process stopped unexpectedly")
                    job.add(job.error)
                    self._after_death(proc)
                return
            if time.monotonic() > deadline:
                self._kill(job, "timeout", f"Stopped: still running after the {job.timeout:g} s limit "
                                           "(raise it with `timeout: seconds` in the block).")
                return

    def _after_death(self, proc):
        with self._lock:
            if self._proc is proc:
                self._discard_worker()


jobs = Jobs()
