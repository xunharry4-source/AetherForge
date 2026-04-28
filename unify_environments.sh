#!/bin/bash
# 万象星际 - 强制型环境大一统运维脚本 (Nuclear env Edition)
# 目标：强制统一所有环境名为 'env'，并自动修复 Makefile 和 .gitignore

BASE_DIR="/Users/harry/Documents/git"
EXCLUDE=("claude-code-source-code" "novel_agent")

echo "🚀 启动 Nuclear env 大一统行动..."

for PROJ in "$BASE_DIR"/*; do
    if [ ! -d "$PROJ" ]; then continue; fi
    DIR_NAME=$(basename "$PROJ")
    
    IS_EXCLUDED=0
    for EX in "${EXCLUDE[@]}"; do
        if [[ "$DIR_NAME" == "$EX" ]]; then IS_EXCLUDED=1; break; fi
    done
    if [ $IS_EXCLUDED -eq 1 ]; then continue; fi

    # 识别 Python 项目
    if [ -f "$PROJ/requirements.txt" ] || [ -f "$PROJ/Makefile" ] || [ -f "$PROJ/setup.py" ] || [ -f "$PROJ/pyproject.toml" ]; then
        echo "------------------------------------------------"
        echo "📂 处理项目: $DIR_NAME"
        cd "$PROJ" || continue
        
        # 1. 物理清理所有异构环境
        echo "🧹 清除所有旧环境..."
        rm -rf .venv venv test_venv .venv_zentex_stable .venv_zentex_311
        
        # 2. 统一重构为 env (3.12)
        CUR_VER=$("./env/bin/python3" --version 2>/dev/null)
        if [[ "$CUR_VER" == *"3.12"* ]]; then
            echo "✅ 'env' 已经是 Python 3.12，跳过重构。"
        else
            echo "🔨 正在物理重构为 'env' (Python 3.12)..."
            rm -rf env
            python3.12 -m venv env
            
            echo "📦 安装依赖..."
            ./env/bin/python3 -m pip install --upgrade pip -q
            if [ -f "requirements.txt" ]; then
                ./env/bin/python3 -m pip install -r requirements.txt -q
            fi
        fi

        # 3. 自动修正 Makefile
        if [ -f "Makefile" ]; then
            echo "📝 修正 Makefile 中的环境路径..."
            sed -i '' 's/\.venv/env/g' Makefile 2>/dev/null || true
            # 避免重复替换，只在必要时处理 venv -> env
            sed -i '' 's/venv/env/g' Makefile 2>/dev/null || true
        fi

        # 4. 自动加固 .gitignore
        if [ -d ".git" ]; then
            if ! grep -q "^env/" .gitignore 2>/dev/null; then
                echo "🛡️ 将 'env/' 加入 .gitignore..."
                echo -e "\n# Unified env\nenv/" >> .gitignore
            fi
        fi
        
        echo "🎉 $DIR_NAME 已达成 'env' 物理大一统。"
    fi
done

echo "------------------------------------------------"
echo "🏁 终极行动结束。所有项目已强制对齐至 'env' 并配置了 Git 忽略。"
