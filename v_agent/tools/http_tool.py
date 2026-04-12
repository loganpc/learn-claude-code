"""HTTP 请求工具"""

from typing import Optional

from .base_new import BaseTool, ToolContext, ToolResult


class HttpRequestTool(BaseTool):
    """HTTP 请求工具"""

    name = "http_request"
    description = "Make an HTTP request."

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                },
                "url": {"type": "string"},
                "headers": {
                    "type": "object",
                    "description": "Request headers"
                },
                "body": {
                    "type": "string",
                    "description": "Request body"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds, default 30"
                }
            },
            "required": ["method", "url"]
        }

    def is_read_only(self, arguments: dict) -> bool:
        """GET 请求视为只读"""
        return arguments.get("method") == "GET"

    def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        try:
            import requests

            method = arguments.get("method", "GET")
            url = arguments.get("url", "")
            headers = arguments.get("headers") or {}
            body = arguments.get("body")
            timeout = arguments.get("timeout", 30)

            if method == "GET":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, headers=headers, data=body, timeout=timeout)
            elif method == "PUT":
                response = requests.put(url, headers=headers, data=body, timeout=timeout)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=timeout)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, data=body, timeout=timeout)
            else:
                return ToolResult(content=f"Error: Unsupported method {method}", is_error=True)

            content = f"Status: {response.status_code}\n{response.text[:10000]}"
            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
