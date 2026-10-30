"""Run the whole studio offline: a pretend website, a pretend model and the real application.

    python -m demo.run            # then open http://127.0.0.1:8000
"""
import os
import sys
import threading

import uvicorn

from demo import llm, site


def main() -> int:
    web, model = site.make_server(), llm.make_server()
    for server in (web, model):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(
        COMPANY="example_company",
        WEBSITE_BASE_URL=f"http://127.0.0.1:{web.server_address[1]}/",
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL=f"http://127.0.0.1:{model.server_address[1]}",
        OLLAMA_MODEL="demo-model",
        RATE_LIMIT_PER_MINUTE="0",
        HUMANIZE_ENABLED="true",
    )
    print("\nDEMO MODE: the website and the AI model are pretend. The answers are canned text, so nothing here shows real writing quality.")
    print("Open http://127.0.0.1:8000\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
