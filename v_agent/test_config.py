#!/usr/bin/env python3
"""测试智谱 GLM API 配置"""

import json
from pathlib import Path
from anthropic import Anthropic

CONFIG_PATH = Path(".agent/config.json")

def test_config():
    # 读取配置
    config = json.loads(CONFIG_PATH.read_text())
    model_config = config["models"]["glm-4.7"]
    
    print("=" * 50)
    print("配置检查")
    print("=" * 50)
    print(f"API Key: {model_config['api_key']}")
    print(f"Base URL: {model_config['base_url']}")
    print(f"Model: glm-4.7")
    print()
    
    api_key = model_config['api_key']
    
    # 检查 API Key 格式
    print("=" * 50)
    print("API Key 格式检查")
    print("=" * 50)
    if api_key.startswith("[REDACTED"):
        print("❌ 错误: API Key 是占位符，需要填写真实密钥")
        print()
        print("请前往 https://open.bigmodel.cn/ 获取 API Key")
        print("获取后，执行以下命令更新配置:")
        print()
        print('  python3 -c "')
        print('  import json')
        print('  p = \".agent/config.json\"')
        print('  c = json.loads(open(p).read())')
        print('  c[\"models\"][\"glm-4.7\"][\"api_key\"] = \"你的真实API_KEY\"')
        print('  open(p, \"w\").write(json.dumps(c, indent=2, ensure_ascii=False))')
        print('  "')
        return False
    
    if not api_key.startswith("sk-"):
        print("⚠️  警告: 智谱 API Key 通常以 'sk-' 开头")
    else:
        print("✓ API Key 格式看起来正确")
    print()
    
    # 测试 API 连接
    print("=" * 50)
    print("API 连接测试")
    print("=" * 50)
    
    try:
        client = Anthropic(
            api_key=api_key,
            base_url=model_config['base_url']
        )
        
        print("发送测试请求...")
        response = client.messages.create(
            model="glm-4.7",
            max_tokens=50,
            messages=[{"role": "user", "content": "你好"}]
        )
        
        print("✓ 连接成功!")
        print(f"响应: {response.content[0].text}")
        return True
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print()
        print("常见问题:")
        print("1. API Key 错误或已过期")
        print("2. Base URL 不正确")
        print("3. 网络连接问题")
        print("4. 账户余额不足")
        return False

if __name__ == "__main__":
    test_config()
