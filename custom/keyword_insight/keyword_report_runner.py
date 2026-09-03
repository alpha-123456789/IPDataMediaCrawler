"""从线上任务表领取关键词报告任务，并在本机执行 custom_report。"""

import argparse
import ctypes
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from custom.db import get_conn
from custom.keyword_insight.notify_client import get_notify_url, send_keyword_task_completion


PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env")

CLIENT_NAME = os.getenv("KEYWORD_REPORT_RUNNER_NAME") or f"{socket.gethostname()}-{os.getpid()}"
POLL_SECONDS = max(int(os.getenv("KEYWORD_REPORT_POLL_SECONDS", "3")), 1)
LOG_LIMIT = 16000
PID_FILE = PROJECT_DIR / "logs" / "keyword_report_runner.pid"
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9
_PROCESS_JOB_HANDLE = None


def trim_log(value):
    value = value or ""
    if len(value) <= LOG_LIMIT:
        return value
    return value[-LOG_LIMIT:]


def register_runner_pid():
    PID_FILE.write_text(str(os.getpid()), encoding="ascii")


def unregister_runner_pid():
    try:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


def create_process_job():
    """结束执行器进程时，同时结束其启动的报告子进程。"""
    global _PROCESS_JOB_HANDLE
    if os.name != "nt":
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.GetCurrentProcess.argtypes = ()
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise ctypes.WinError(ctypes.get_last_error())

    # JOBOBJECT_EXTENDED_LIMIT_INFORMATION 的 LimitFlags 偏移为 16。
    info = (ctypes.c_byte * 144)()
    ctypes.c_uint32.from_buffer(info, 16).value = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        job_handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        kernel32.CloseHandle(job_handle)
        raise ctypes.WinError(ctypes.get_last_error())

    process_handle = kernel32.GetCurrentProcess()
    if not kernel32.AssignProcessToJobObject(job_handle, process_handle):
        kernel32.CloseHandle(job_handle)
        raise ctypes.WinError(ctypes.get_last_error())

    _PROCESS_JOB_HANDLE = job_handle


def close_process_job():
    global _PROCESS_JOB_HANDLE
    if _PROCESS_JOB_HANDLE:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle(_PROCESS_JOB_HANDLE)
        _PROCESS_JOB_HANDLE = None


def claim_task():
    """通过事务和行锁领取一条待执行任务。"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, report_name, prompt, source_keyword, start_date, end_date,
                       platform, post_ids, modify_user_id
                FROM keyword_report_task
                WHERE status = 0
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE
                """
            )
            task = cur.fetchone()
            if not task:
                conn.commit()
                return None

            cur.execute(
                """
                UPDATE keyword_report_task
                SET status = 1,
                    client_name = %s,
                    start_time = UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000,
                    retry_count = retry_count + 1,
                    error_message = ''
                WHERE id = %s AND status = 0
                """,
                (CLIENT_NAME, task["id"]),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None

            conn.commit()
            return task
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_task(task_id, success, execute_log="", error_message=""):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE keyword_report_task
                SET status = %s,
                    client_name = %s,
                    execute_log = %s,
                    error_message = %s,
                    finish_time = UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000
                WHERE id = %s AND status = 1
                """,
                (
                    2 if success else 3,
                    CLIENT_NAME,
                    trim_log(execute_log),
                    trim_log(error_message),
                    task_id,
                ),
            )
        updated = cur.rowcount == 1
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_task(task, use_llm=True):
    command = [
        sys.executable,
        "-m",
        "custom.keyword_insight.custom_report",
        "--prompt",
        str(task["prompt"]),
        "--report-name",
        str(task["report_name"]),
        "--keyword",
        str(task["source_keyword"]),
        "--start-date",
        task["start_date"].strftime("%Y-%m-%d"),
        "--end-date",
        task["end_date"].strftime("%Y-%m-%d"),
        "--platform",
        str(task["platform"]),
        "--post-ids",
        str(task["post_ids"]),
    ]
    command.append("--llm")
    print(
        f"[任务 {task['id']}] 开始生成报告：{task['report_name']} "
        f"（执行器：{CLIENT_NAME}）",
        flush=True,
    )
    process = subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    output_lines = []
    for line in process.stdout:
        line = line.rstrip("\r\n")
        if not line:
            continue
        output_lines.append(line)

    return_code = process.wait()
    execute_log = trim_log("\n".join(output_lines))
    if return_code != 0:
        raise RuntimeError(execute_log or f"custom_report 退出码：{return_code}")
    print(f"[任务 {task['id']}] 报告生成完成：{task['report_name']}", flush=True)
    return execute_log


def validate_settings():
    required = ("MYSQL_DB_HOST", "MYSQL_DB_USER", "MYSQL_DB_PWD", "MYSQL_DB_NAME")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(".env 缺少数据库配置：" + ", ".join(missing))


def main():
    parser = argparse.ArgumentParser(description="关键词报告本地任务执行器")
    parser.add_argument("--llm", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        create_process_job()
    except OSError as exc:
        print(f"[警告] 无法启用子进程自动清理：{exc}", file=sys.stderr, flush=True)
    register_runner_pid()
    try:
        validate_settings()
        print(
            f"关键词报告本地执行器已启动：{CLIENT_NAME}，"
            f"每 {POLL_SECONDS} 秒检查一次任务表，启用大模型；"
            f"通知回调地址：{get_notify_url()}"
        , flush=True)
        while True:
            try:
                task = claim_task()
                if not task:
                    time.sleep(POLL_SECONDS)
                    continue

                task_id = task["id"]
                try:
                    execute_log = run_task(task, use_llm=True)
                    completed = complete_task(task_id, True, execute_log=execute_log)
                    if completed:
                        send_keyword_task_completion(
                            {
                                "kind": "report",
                                "dedupe_key": f"report-{task_id}",
                                "task_id": task_id,
                                "modify_user_id": task["modify_user_id"],
                                "report_name": task["report_name"],
                                "source_keyword": task["source_keyword"],
                                "platform": task["platform"],
                                "executor_name": CLIENT_NAME,
                            }
                        )
                except Exception as exc:
                    error_message = str(exc)
                    print(f"[任务 {task_id}] 执行失败：{error_message}", file=sys.stderr, flush=True)
                    try:
                        complete_task(task_id, False, error_message=error_message)
                    except Exception as complete_exc:
                        print(f"[任务 {task_id}] 状态回写失败：{complete_exc}", file=sys.stderr, flush=True)
            except KeyboardInterrupt:
                print("关键词报告本地执行器已停止", flush=True)
                return
            except Exception as exc:
                print(f"领取任务失败：{exc}", file=sys.stderr, flush=True)
                time.sleep(POLL_SECONDS)
    finally:
        unregister_runner_pid()
        close_process_job()


if __name__ == "__main__":
    main()
