"""端到端冒烟测试（需要后端已启动）。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\smoke.py
    .\\.venv\\Scripts\\python.exe scripts\\smoke.py --prompt "你好"

依次验证：健康检查 → 真实模型探测 → 普通对话 → SSE 流式对话。

注意：本机若配置了系统代理，httpx 默认会走代理，导致访问 127.0.0.1 返回 502，
因此这里固定 trust_env=False。
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx


def _print(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOrch 端到端冒烟测试")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt", default="用一句话介绍 AgentOrch 是什么")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with httpx.Client(base_url=args.base_url, timeout=120, trust_env=False) as client:
        _print("health")
        health = client.get("/api/v1/health")
        print(health.status_code, json.dumps(health.json(), ensure_ascii=False))
        health.raise_for_status()

        _print("llm ping")
        ping = client.post("/api/v1/llm/ping")
        print(ping.status_code, json.dumps(ping.json(), ensure_ascii=False))
        ping.raise_for_status()
        if not ping.json()["ok"]:
            print("模型探测失败")
            return 1

        _print("chat")
        chat = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": args.prompt}]})
        chat.raise_for_status()
        data = chat.json()
        print(f"model={data['model']} latency={data['latency_ms']}ms tokens={data['usage']['total_tokens']}")
        print("reply:", data["content"])

        _print("chat/stream")
        collected = ""
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "数到三，只输出数字"}]},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "delta":
                    collected += event["delta"]
                elif event["type"] == "error":
                    print("流式错误:", event)
                    return 1
                elif event["type"] == "done":
                    print(f"done: {json.dumps(event, ensure_ascii=False)}")
                    break
        print("stream text:", collected.replace("\n", " "))

    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
