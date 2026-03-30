# v_agent/config.py
import json
from pathlib import Path
from anthropic import Anthropic

CONFIG_DIR = Path(".agent")
CONFIG_PATH = CONFIG_DIR / "config.json"

# 服务商预设
PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base_url": None,
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6"]
    },
    "openai_compatible": {
        "name": "OpenAI Compatible",
        "base_url": None,
        "models": []
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"]
    },
    "glm": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-5"]
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-M1-80k"]
    },
    "kimi": {
        "name": "Kimi (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2.5"]
    },
}


class ModelManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config = self._load_or_create()
        self.current_model = self.config.get("default_model")
        self._client = None

    def _load_or_create(self) -> dict:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
        print("\033[36m检测到首次运行，请配置模型...\033[0m\n")
        return self._interactive_setup()

    def _interactive_setup(self) -> dict:
        config = {"default_model": None, "models": {}, "rag": {"enabled": False, "endpoint": ""}}

        providers = list(PROVIDERS.items())
        print("可选服务商:")
        for i, (key, p) in enumerate(providers, 1):
            print(f"  {i}. {p['name']}")

        while True:
            try:
                choice = int(input("\n选择服务商 (数字): ")) - 1
                if 0 <= choice < len(providers):
                    break
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            print("无效选择，请重试")

        provider_key, provider = providers[choice]

        api_key = input(f"\n请输入 {provider['name']} 的 API Key: ").strip()

        if provider["models"]:
            print(f"\n推荐模型:")
            for i, m in enumerate(provider["models"], 1):
                print(f"  {i}. {m}")
            print(f"  {len(provider['models']) + 1}. 自定义输入")
            try:
                mc = int(input("选择模型 (数字): ")) - 1
                if 0 <= mc < len(provider["models"]):
                    model_id = provider["models"][mc]
                else:
                    model_id = input("输入模型 ID: ").strip()
            except (ValueError, EOFError, KeyboardInterrupt):
                model_id = provider["models"][0]
        else:
            model_id = input("输入模型 ID: ").strip()

        base_url = provider.get("base_url")
        if provider_key == "openai_compatible":
            base_url = input("输入 Base URL: ").strip()

        config["default_model"] = model_id
        config["models"][model_id] = {
            "provider": provider_key,
            "api_key": api_key,
            "base_url": base_url
        }

        self._save(config)
        print(f"\n\033[32m配置完成! 默认模型: {model_id}\033[0m\n")
        return config

    def _save(self, config: dict = None):
        if config is None:
            config = self.config
        CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))

    def switch_model(self, model_id: str):
        if model_id not in self.config["models"]:
            print(f"\n模型 '{model_id}' 未配置。")
            api_key = input("请输入 API Key: ").strip()
            base_url = input("请输入 Base URL (留空使用默认): ").strip() or None
            self.config["models"][model_id] = {
                "provider": "openai_compatible",
                "api_key": api_key,
                "base_url": base_url
            }
            self._save()

        self.current_model = model_id
        self.config["default_model"] = model_id
        self._save()
        self._client = None
        print(f"\033[32m已切换到 {model_id}\033[0m")

    def list_models(self):
        print("\n已配置的模型:")
        for model_id, info in self.config["models"].items():
            marker = " (当前)" if model_id == self.current_model else ""
            print(f"  - {model_id} [{info['provider']}]{marker}")

    def get_client(self) -> Anthropic:
        if self._client:
            return self._client
        model_config = self.config["models"].get(self.current_model, {})
        kwargs = {"api_key": model_config.get("api_key")}
        if model_config.get("base_url"):
            kwargs["base_url"] = model_config["base_url"]
        self._client = Anthropic(**kwargs)
        return self._client

    def get_model_id(self) -> str:
        return self.current_model

    def get_rag_config(self) -> dict:
        return self.config.get("rag", {"enabled": False, "endpoint": ""})
