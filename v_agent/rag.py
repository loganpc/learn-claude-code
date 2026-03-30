# v_agent/rag.py
import requests


class RAG:
    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint

    def query(self, question: str, top_k: int = 3) -> str:
        """调用外部 RAG 服务"""
        if not self.endpoint:
            return "RAG 未配置。请在 .agent/config.json 中设置 rag.endpoint"

        try:
            resp = requests.post(
                self.endpoint,
                json={"question": question, "top_k": top_k},
                timeout=30
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return "RAG 未找到相关内容"
            return "\n\n---\n\n".join(str(r) for r in results)
        except requests.Timeout:
            return "Error: RAG 服务超时"
        except Exception as e:
            return f"Error: RAG 查询失败 - {e}"
