#!/bin/bash
# 万象星际 - 终极物理对齐脚本 (Nuclear .venv V6)
# 目标：强制统一环境名为 '.venv'，并物理修正 Makefile 和 .gitignore

CURRENT_DIR=$(pwd)
BASE_DIR=$(dirname "$CURRENT_DIR")
EXCLUDE="claude-code-source-code novel_agent"

echo "🚀 启动 .venv 物理大一统行动..."
echo "📍 目标根目录: $BASE_DIR"

cd "$BASE_DIR" || { echo "❌ 无法访问父目录"; exit 1; }

for PROJ in *; do
    [ -d "$PROJ" ] || continue
    DIR_NAME=$(basename "$PROJ")
    
    if [[ " $EXCLUDE " =~ " $DIR_NAME " ]]; then continue; fi

    if [ -f "$PROJ/requirements.txt" ] || [ -f "$PROJ/Makefile" ] || [ -f "$PROJ/setup.py" ] || [ -f "$PROJ/pyproject.toml" ]; then
        echo "------------------------------------------------"
        echo "📂 正在对齐: $DIR_NAME"
        
        (
            cd "$PROJ" || exit
            
            # 1. 物理清理所有异构环境 (包括之前的 env)
            rm -rf env venv test_venv .venv_zentex_stable .venv_zentex_311
            
            # 2. 统一重塑为 .venv (3.12)
            NEED_REBUILD=1
            if [ -d ".venv" ]; then
                CUR_VER=$(./.venv/bin/python3 --version 2>/dev/null)
                if [[ "$CUR_VER" == *"3.12"* ]]; then
                    echo "  ✅ '.venv' 已达标 (3.12)，跳过重构。"
                    NEED_REBUILD=0
                fi
            fi
            
            if [ $NEED_REBUILD -eq 1 ]; then
                echo "  🔨 物理重塑 '.venv' (Python 3.12)..."
                rm -rf .venv
                python3.12 -m venv .venv
                ./.venv/bin/python3 -m pip install --upgrade pip -q
                if [ -f "requirements.txt" ]; then
                    echo "  📦 安装依赖..."
                    ./.venv/bin/python3 -m pip install -r requirements.txt -q
                fi
            fi

            # 3. 修正 Makefile (env/venv -> .venv)
            if [ -f "Makefile" ]; then
                echo "  📝 修正 Makefile -> .venv..."
                sed -i '' 's/env\//.venv\//g' Makefile 2>/dev/null
                sed -i '' 's/venv\//.venv\//g' Makefile 2>/dev/null
                # 处理可能不带斜杠的变量定义
                sed -i '' 's/= env/= .venv/g' Makefile 2>/dev/null
                sed -i '' 's/= venv/= .venv/g' Makefile 2>/dev/null
            fi

            # 4. 修正 .gitignore
            if [ -d ".git" ]; then
                if ! grep -q "^\.venv/" .gitignore 2>/dev/null; then
                    echo "  🛡️ 锁定 .gitignore -> .venv/"
                    echo -e "\n# Unified .venv\n.venv/" >> .gitignore
                fi
            fi
            echo "  ✨ $DIR_NAME 物理对齐完成。"
        )
    fi
done

echo "------------------------------------------------"
echo "🏁 .venv 大一统行动结束。"
